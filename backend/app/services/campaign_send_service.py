"""
Campaign Send Service.

Orchestrates the full campaign send pipeline. Takes a campaign and makes emails flow.
Connects: template resolution, scheduling, tracking injection, UTM injection, email delivery.

Hardened with:
- Exponential backoff retry for transient SMTP failures
- Real-time progress tracking via Redis
- Batch executor with throttling and pause support
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignProspect, Prospect
from app.services.templates import template_service, substitute_variables
from app.services.send_scheduler import send_scheduler
from app.services.tracking_service import tracking_service
from app.services.utm_service import utm_service
from app.services.mail_engine_client import mail_engine_client
from app.services.email_service import email_service
from app.services.email_validation import email_validator
from app.db.redis import redis_client
from app.utils.test_mode import is_test_mode_enabled

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds — doubles each retry: 2, 4, 8

# SMTP errors that are transient and worth retrying
TRANSIENT_SMTP_CODES = {421, 450, 451, 452}

# Circuit breaker: pause batch after N consecutive transient failures
CIRCUIT_BREAKER_THRESHOLD = 5
CIRCUIT_BREAKER_COOLDOWN = 60  # seconds to wait before resuming
CIRCUIT_BREAKER_MAX_TRIPS = 3  # abort after this many trips

def _is_transient_error(exc: Exception) -> bool:
    """Determine if an SMTP error is transient (worth retrying)."""
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return True
    if isinstance(exc, smtplib.SMTPResponseException):
        return exc.smtp_code in TRANSIENT_SMTP_CODES
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    err_msg = str(exc).lower()
    return any(kw in err_msg for kw in ("timeout", "connection reset", "temporary", "try again"))


class CampaignSendService:
    """Orchestrates campaign email sending.

    Connects existing services: template resolution, scheduling,
    tracking injection, UTM injection, and email delivery.
    """

    def _build_variable_context(self, prospect: Prospect) -> Dict[str, str]:
        """Build variable mapping from prospect data."""
        first_name = prospect.first_name or ""
        last_name = prospect.last_name or ""

        return {
            "first_name": first_name,
            "last_name": last_name,
            "email": prospect.email or "",
            "company": prospect.company_name or "",
            "company_name": prospect.company_name or "",
            "company_domain": prospect.company_domain or "",
            "job_title": prospect.job_title or "",
            "title": prospect.job_title or "",
            "full_name": f"{first_name} {last_name}".strip(),
            "linkedin_url": prospect.linkedin_url or "",
        }

    def _resolve_template_variables(self, content: str, prospect: Prospect) -> str:
        """Resolve {{first_name}}, {{company}}, etc. from prospect data."""
        variables = self._build_variable_context(prospect)
        return substitute_variables(content, variables)

    async def prepare_and_schedule(
        self,
        session: AsyncSession,
        campaign_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """Prepare all emails and compute send schedule.

        1. Load campaign + template
        2. Load enrolled recipients
        3. Resolve template variables per prospect
        4. Compute timezone-aware schedule via SendScheduler
        5. Cache resolved emails in Redis
        6. Return schedule summary
        """
        campaign = await self._get_campaign(session, campaign_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        recipients = await self._get_enrolled_recipients(session, campaign_id)
        if not recipients:
            raise ValueError("No enrolled recipients found")

        template_html = campaign.html_template or ""
        template_subject = campaign.subject_template or "No Subject"

        personalized_emails = []

        for cp, prospect in recipients:
            prospect: Prospect = prospect

            resolved_subject = self._resolve_template_variables(
                template_subject, prospect
            )
            resolved_html = self._resolve_template_variables(template_html, prospect)

            email_data = {
                "campaign_id": campaign_id,
                "campaign_prospect_id": str(cp.id),
                "prospect_id": str(prospect.id),
                "prospect_email": prospect.email,
                "first_name": prospect.first_name or "",
                "company_name": prospect.company_name or "",
                "company_domain": prospect.company_domain or "",
                "subject": resolved_subject,
                "html_body": resolved_html,
            }
            personalized_emails.append(email_data)

            await redis_client.set_json(
                f"campaign:{campaign_id}:emails:{prospect.id}",
                email_data,
                ex=86400 * 7,
            )

        scheduled = await send_scheduler.schedule_campaign_sends(
            campaign_id=campaign_id,
            personalized_emails=personalized_emails,
        )

        await redis_client.set_json(
            f"campaign:{campaign_id}:status",
            {"status": "scheduled", "total": len(scheduled)},
            ex=86400 * 7,
        )

        await self._update_campaign_stats(session, campaign_id, len(recipients))

        logger.info(
            "Prepared campaign %s: %d emails scheduled",
            campaign_id,
            len(scheduled),
        )

        return {
            "campaign_id": campaign_id,
            "total_scheduled": len(scheduled),
            "first_send": scheduled[0]["send_at"] if scheduled else None,
            "last_send": scheduled[-1]["send_at"] if scheduled else None,
        }

    # ------------------------------------------------------------------
    # Progress tracking helpers
    # ------------------------------------------------------------------

    async def _update_progress(
        self,
        campaign_id: str,
        *,
        status: str = "sending",
        sent: int = 0,
        failed: int = 0,
        skipped: int = 0,
        total: int = 0,
        current_email: str = "",
    ) -> None:
        """Write real-time progress to Redis so the UI can poll it."""
        await redis_client.set_json(
            f"campaign:{campaign_id}:progress",
            {
                "status": status,
                "sent": sent,
                "failed": failed,
                "skipped": skipped,
                "total": total,
                "current_email": current_email,
                "updated_at": datetime.utcnow().isoformat(),
            },
            ex=86400 * 7,
        )

    async def get_progress(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        """Read campaign send progress from Redis."""
        return await redis_client.get_json(f"campaign:{campaign_id}:progress")

    # ------------------------------------------------------------------
    # Batch executor
    # ------------------------------------------------------------------

    async def execute_campaign_batch(
        self,
        campaign_id: str,
        throttle_seconds: float = 2.0,
        start_index: int = 0,
    ) -> Dict[str, Any]:
        """Execute all scheduled sends for a campaign with throttling.

        Iterates through every enrolled prospect, sends with retry,
        respects pause requests via Redis, and tracks progress in
        real time.

        Args:
            campaign_id: Campaign UUID string.
            throttle_seconds: Minimum delay between sends (default 2s).
            start_index: Skip the first N recipients (for resume after pause).

        Returns:
            Summary dict with sent / failed / skipped counts.
        """
        from app.db.postgres import async_session_maker

        async with async_session_maker() as session:
            campaign = await self._get_campaign(session, campaign_id)
            if not campaign:
                raise ValueError(f"Campaign {campaign_id} not found")

            all_recipients = await self._get_enrolled_recipients(session, campaign_id)

        # Skip already-processed recipients on resume
        recipients = all_recipients[start_index:] if start_index > 0 else all_recipients
        if start_index > 0:
            logger.info(
                "Campaign %s: resuming from index %d, %d recipients remaining",
                campaign_id, start_index, len(recipients),
            )

        total = len(all_recipients)  # total stays the full count for progress display
        sent = 0
        failed = 0
        skipped = 0

        # Circuit breaker state
        consecutive_failures = 0
        circuit_breaker_trips = 0

        await self._update_progress(
            campaign_id, status="sending", total=total,
        )

        for idx, (cp, prospect) in enumerate(recipients):
            # Check for pause / cancel request
            ctrl = await redis_client.get_json(f"campaign:{campaign_id}:control")
            if ctrl and ctrl.get("action") in ("pause", "cancel"):
                logger.info(
                    "Campaign %s %s requested after %d/%d sends",
                    campaign_id, ctrl["action"], idx, total,
                )
                await self._update_progress(
                    campaign_id,
                    status=ctrl["action"] + "d",  # "paused" or "cancelled"
                    sent=sent, failed=failed, skipped=skipped, total=total,
                )
                # Store absolute resume index so we can pick up later
                await redis_client.set_json(
                    f"campaign:{campaign_id}:last_index",
                    {"index": start_index + idx},
                    ex=86400 * 30,
                )
                break

            prospect_id = str(prospect.id)

            try:
                result = await self.execute_single_send(campaign_id, prospect_id)
                if result.get("status") == "sent":
                    sent += 1
                    consecutive_failures = 0  # reset on success
                else:
                    skipped += 1
            except Exception as exc:
                failed += 1
                if _is_transient_error(exc):
                    consecutive_failures += 1
                else:
                    consecutive_failures = 0  # permanent error, not server issue

            # --- Circuit breaker ---
            if consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
                circuit_breaker_trips += 1
                if circuit_breaker_trips >= CIRCUIT_BREAKER_MAX_TRIPS:
                    logger.error(
                        "Campaign %s: circuit breaker tripped %d times — aborting. "
                        "SMTP server appears unreachable.",
                        campaign_id, circuit_breaker_trips,
                    )
                    await self._update_progress(
                        campaign_id,
                        status="failed_smtp",
                        sent=sent, failed=failed, skipped=skipped, total=total,
                    )
                    await redis_client.set_json(
                        f"campaign:{campaign_id}:last_index",
                        {"index": start_index + idx},
                        ex=86400 * 30,
                    )
                    break

                logger.warning(
                    "Campaign %s: %d consecutive failures — circuit breaker cooling down %ds (trip %d/%d)",
                    campaign_id, consecutive_failures,
                    CIRCUIT_BREAKER_COOLDOWN, circuit_breaker_trips, CIRCUIT_BREAKER_MAX_TRIPS,
                )
                await self._update_progress(
                    campaign_id,
                    status="cooldown",
                    sent=sent, failed=failed, skipped=skipped, total=total,
                    current_email=f"Pausing {CIRCUIT_BREAKER_COOLDOWN}s — SMTP errors",
                )
                await asyncio.sleep(CIRCUIT_BREAKER_COOLDOWN)
                consecutive_failures = 0  # reset after cooldown

            await self._update_progress(
                campaign_id,
                status="sending",
                sent=sent,
                failed=failed,
                skipped=skipped,
                total=total,
                current_email=prospect.email or "",
            )

            # Throttle — don't slam the SMTP server
            if idx < total - 1:
                await asyncio.sleep(throttle_seconds)
        else:
            # Loop completed without break — store final index
            await redis_client.set_json(
                f"campaign:{campaign_id}:last_index",
                {"index": total},
                ex=86400 * 30,
            )

        final_status = "completed" if failed == 0 else "completed_with_errors"
        # Override if circuit breaker aborted
        ctrl_check = await redis_client.get_json(f"campaign:{campaign_id}:control")
        if ctrl_check and ctrl_check.get("action") == "cancel":
            final_status = "cancelled"
        elif ctrl_check and ctrl_check.get("action") == "pause":
            final_status = "paused"

        await self._update_progress(
            campaign_id,
            status=final_status,
            sent=sent, failed=failed, skipped=skipped, total=total,
        )

        # Update campaign model status
        async with async_session_maker() as session:
            await session.execute(
                update(Campaign)
                .where(Campaign.id == UUID(campaign_id))
                .values(
                    status="completed" if failed == 0 else "failed",
                    completed_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
            )
            await session.commit()

        logger.info(
            "Campaign %s batch complete: %d sent, %d failed, %d skipped / %d total",
            campaign_id, sent, failed, skipped, total,
        )

        return {
            "campaign_id": campaign_id,
            "status": final_status,
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
            "total": total,
        }

    # ------------------------------------------------------------------
    # Single send (with retry)
    # ------------------------------------------------------------------

    async def execute_single_send(
        self,
        campaign_id: str,
        prospect_id: str,
    ) -> Dict[str, Any]:
        """Send one email from a scheduled campaign, with retry on transient errors.

        1. Load cached resolved HTML from Redis
        2. Inject UTM params (if campaign has UTM config)
        3. Generate tracking URLs
        4. Inject tracking pixel + wrap links
        5. Send via mail-engine (server) or email_service (user_smtp)
        6. Record SendLog, update CampaignProspect, increment Campaign counts
        """
        email_data = await redis_client.get_json(
            f"campaign:{campaign_id}:emails:{prospect_id}"
        )
        if not email_data:
            raise ValueError(f"No cached email data for prospect {prospect_id}")

        campaign = await self._get_campaign_by_id(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        html_body = email_data["html_body"]

        utm_config = getattr(campaign, "utm_config", None)
        if utm_config:
            html_body = utm_service.inject_utm_into_html(
                html_body,
                source=utm_config.get("source", "champmail"),
                medium=utm_config.get("medium", "email"),
                campaign=utm_config.get("campaign", campaign.name),
            )

        tracking_urls = await tracking_service.generate_tracking_urls(
            campaign_id, prospect_id
        )

        is_valid_email, email_error = email_validator.validate_syntax(
            email_data["prospect_email"]
        )
        if not is_valid_email:
            await self._record_failure(
                campaign_id=campaign_id,
                prospect_id=prospect_id,
                error=f"Invalid email: {email_error}",
                recipient_email=email_data["prospect_email"],
                subject=email_data.get("subject", ""),
                team_id=campaign.team_id,
            )
            return {"status": "skipped", "reason": f"Invalid email: {email_error}"}

        if email_validator.is_disposable_email(email_data["prospect_email"]):
            logger.warning(
                "Skipping disposable email: %s", email_data["prospect_email"]
            )
            await self._record_failure(
                campaign_id=campaign_id,
                prospect_id=prospect_id,
                error="Disposable email not allowed",
                recipient_email=email_data["prospect_email"],
                subject=email_data.get("subject", ""),
                team_id=campaign.team_id,
            )
            return {"status": "skipped", "reason": "Disposable email not allowed"}

        html_body = tracking_service.wrap_links_in_html(
            html_body,
            tracking_urls["click_base_url"],
            tracking_urls["signature"],
        )

        pixel_url = tracking_urls.get("pixel_url", "")
        if pixel_url:
            pixel_tag = f'<img src="{pixel_url}" width="1" height="1" alt="" style="display:block;border:0;outline:none;text-decoration:none;" />'
            html_body_lower = html_body.lower()
            if "</body>" in html_body_lower:
                html_body = html_body.replace("</body>", f"{pixel_tag}</body>")
            else:
                html_body += pixel_tag

        unsubscribe_url = tracking_urls.get("unsubscribe_url", "")
        if unsubscribe_url:
            unsubscribe_footer = f'''
<div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #6b7280; text-align: center;">
    <p>You're receiving this because you signed up for our mailing list.</p>
    <p>
        <a href="{unsubscribe_url}" style="color: #6b7280; text-decoration: underline;">Unsubscribe</a>
        from this list
    </p>
    <p style="margin-top: 10px;">
        ChampMail Inc.<br/>
        123 Email Way, San Francisco, CA 94105
    </p>
</div>'''
            html_body_lower = html_body.lower()
            if "</body>" in html_body_lower:
                html_body = html_body.replace("</body>", f"{unsubscribe_footer}</body>")
            else:
                html_body += unsubscribe_footer

        html_body = html_body.replace("{{unsubscribe_url}}", unsubscribe_url)

        from_address = campaign.from_address or ""
        from_name = campaign.from_name or ""
        user_id = str(campaign.created_by) if campaign.created_by else ""

        send_mode = campaign.send_mode or "user_smtp"
        domain_id = str(campaign.domain_id) if campaign.domain_id else ""

        if is_test_mode_enabled():
            logger.warning("TEST MODE: Sending email with DNS verification bypassed")

        logger.info("Sending email to %s for campaign %s (send_mode: %s)",
                   email_data["prospect_email"], campaign_id, send_mode)

        # --- Retry loop for transient SMTP failures ---
        last_exc: Optional[Exception] = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                result = await self._do_send(
                    campaign=campaign,
                    email_data=email_data,
                    html_body=html_body,
                    from_address=from_address,
                    from_name=from_name,
                    user_id=user_id,
                    send_mode=send_mode,
                    domain_id=domain_id,
                )

                if isinstance(result, dict):
                    if not result.get("success"):
                        raise RuntimeError(result.get("error", "Email send failed"))
                    message_id = result.get("message_id", "")
                else:
                    message_id = result.message_id

                await self._record_send(
                    campaign_id=campaign_id,
                    prospect_id=prospect_id,
                    campaign_prospect_id=email_data["campaign_prospect_id"],
                    message_id=message_id,
                    recipient_email=email_data["prospect_email"],
                    from_address=from_address,
                    subject=email_data["subject"],
                    team_id=campaign.team_id,
                )

                await redis_client.set_json(
                    f"campaign:{campaign_id}:status",
                    {"status": "sending"},
                    ex=86400 * 7,
                )

                logger.info(
                    "Email sent to %s for campaign %s (message_id: %s, attempt %d)",
                    email_data["prospect_email"], campaign_id, message_id, attempt + 1,
                )
                return {"status": "sent", "message_id": message_id}

            except Exception as e:
                last_exc = e
                if attempt < MAX_RETRIES and _is_transient_error(e):
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "Transient error sending to %s (attempt %d/%d), retrying in %ds: %s",
                        email_data["prospect_email"], attempt + 1, MAX_RETRIES + 1, delay, e,
                    )
                    await asyncio.sleep(delay)
                    continue
                # Permanent failure or retries exhausted
                break

        # All retries failed
        logger.error(
            "Failed to send email to %s for campaign %s after %d attempts: %s",
            email_data["prospect_email"], campaign_id, MAX_RETRIES + 1, last_exc,
        )
        await self._record_failure(
            campaign_id=campaign_id,
            prospect_id=prospect_id,
            error=str(last_exc),
            recipient_email=email_data.get("prospect_email", ""),
            subject=email_data.get("subject", ""),
            team_id=campaign.team_id,
        )
        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Internal: actual SMTP send (no retry logic — that lives above)
    # ------------------------------------------------------------------

    async def _do_send(
        self,
        *,
        campaign: Campaign,
        email_data: Dict[str, Any],
        html_body: str,
        from_address: str,
        from_name: str,
        user_id: str,
        send_mode: str,
        domain_id: str,
    ) -> Any:
        """Dispatch to mail-engine or user SMTP. Returns result object."""
        if send_mode == "server" and domain_id:
            return await mail_engine_client.send_email(
                recipient=email_data["prospect_email"],
                recipient_name=email_data.get("first_name", ""),
                subject=email_data["subject"],
                html_body=html_body,
                from_address=from_address,
                reply_to=campaign.reply_to or "",
                domain_id=domain_id,
                track_opens=True,
                track_clicks=True,
                send_mode="server",
            )

        from app.db.postgres import async_session_maker

        async with async_session_maker() as email_session:
            return await email_service.send_email(
                session=email_session,
                user_id=user_id,
                to_email=email_data["prospect_email"],
                subject=email_data["subject"],
                body=html_body,
                from_email=from_address,
                from_name=from_name,
                reply_to=campaign.reply_to or "",
                html_body=html_body,
            )

    async def send_test(
        self,
        session: AsyncSession,
        campaign_id: str,
        to_email: str,
    ) -> Dict[str, Any]:
        """Send a preview email to a specific address (test send).

        Uses first prospect's data for variable resolution.
        Skips scheduling — sends immediately.
        """
        campaign = await self._get_campaign(session, campaign_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")

        recipients = await self._get_enrolled_recipients(session, campaign_id, limit=1)
        if not recipients:
            raise ValueError("No recipients enrolled in campaign")

        cp, prospect = recipients[0]

        resolved_subject = self._resolve_template_variables(
            campaign.subject_template or "Test Subject", prospect
        )
        resolved_html = self._resolve_template_variables(
            campaign.html_template or "<h1>Test Email</h1>", prospect
        )

        tracking_urls = await tracking_service.generate_tracking_urls(
            campaign_id, str(prospect.id)
        )

        resolved_html = tracking_service.wrap_links_in_html(
            resolved_html,
            tracking_urls["click_base_url"],
            tracking_urls["signature"],
        )

        send_mode = campaign.send_mode or "user_smtp"
        user_id = str(campaign.created_by) if campaign.created_by else ""

        try:
            if send_mode == "server" and campaign.domain_id:
                result = await mail_engine_client.send_email(
                    recipient=to_email,
                    recipient_name="Test User",
                    subject=f"[TEST] {resolved_subject}",
                    html_body=resolved_html,
                    from_address=campaign.from_address or "",
                    reply_to=campaign.reply_to or "",
                    domain_id=str(campaign.domain_id),
                    track_opens=True,
                    track_clicks=True,
                )
            else:
                result = await email_service.send_email(
                    session=session,
                    user_id=user_id,
                    to_email=to_email,
                    subject=f"[TEST] {resolved_subject}",
                    body=resolved_html,
                    from_email=campaign.from_address or "",
                    from_name=campaign.from_name or "",
                    reply_to=campaign.reply_to or "",
                    html_body=resolved_html,
                )

            # Handle dict return from email_service vs SendResult from mail_engine
            if isinstance(result, dict):
                if not result.get("success"):
                    raise RuntimeError(result.get("error", "Email send failed"))
                message_id = result.get("message_id", "")
            else:
                message_id = result.message_id

            return {
                "status": "sent",
                "message_id": message_id,
                "to": to_email,
            }
        except Exception as e:
            logger.error("Test send failed: %s", str(e))
            raise

    async def _get_campaign(
        self,
        session: AsyncSession,
        campaign_id: str,
    ) -> Optional[Campaign]:
        """Get campaign by ID."""
        try:
            uid = UUID(campaign_id)
        except ValueError:
            return None
        result = await session.execute(select(Campaign).where(Campaign.id == uid))
        return result.scalar_one_or_none()

    async def _get_campaign_by_id(self, campaign_id: str) -> Optional[Campaign]:
        """Get campaign by ID using a new session."""
        from app.db.postgres import async_session_maker

        async with async_session_maker() as session:
            return await self._get_campaign(session, campaign_id)

    async def _get_enrolled_recipients(
        self,
        session: AsyncSession,
        campaign_id: str,
        limit: Optional[int] = None,
    ) -> list:
        """Get enrolled recipients for a campaign."""
        try:
            uid = UUID(campaign_id)
        except ValueError:
            return []

        query = (
            select(CampaignProspect, Prospect)
            .join(Prospect, CampaignProspect.prospect_id == Prospect.id)
            .where(CampaignProspect.campaign_id == uid)
            .where(CampaignProspect.status == "enrolled")
            .where(Prospect.status == "active")
        )

        if limit:
            query = query.limit(limit)

        result = await session.execute(query)
        return list(result.all())

    async def _update_campaign_stats(
        self,
        session: AsyncSession,
        campaign_id: str,
        total: int,
    ) -> None:
        """Update campaign statistics."""
        try:
            uid = UUID(campaign_id)
        except ValueError:
            return

        await session.execute(
            update(Campaign)
            .where(Campaign.id == uid)
            .values(total_prospects=total, updated_at=datetime.utcnow())
        )
        await session.flush()

    async def _record_send(
        self,
        campaign_id: str,
        prospect_id: str,
        campaign_prospect_id: str,
        message_id: str,
        recipient_email: str,
        from_address: str,
        subject: str,
        team_id: Any = None,
    ) -> None:
        """Record successful send in database including SendLog entry."""
        from app.db.postgres import async_session_maker
        from app.models.send_log import SendLog

        async with async_session_maker() as session:
            send_log = SendLog(
                message_id=message_id,
                campaign_id=UUID(campaign_id) if campaign_id else None,
                prospect_id=UUID(prospect_id) if prospect_id else None,
                recipient_email=recipient_email,
                from_address=from_address,
                subject=subject,
                status="sent",
                sent_at=datetime.utcnow(),
                team_id=team_id,
            )
            session.add(send_log)

            try:
                cp_uid = UUID(campaign_prospect_id)
            except ValueError:
                pass
            else:
                await session.execute(
                    update(CampaignProspect)
                    .where(CampaignProspect.id == cp_uid)
                    .values(
                        email_sent=True,
                        last_message_id=message_id,
                        last_sent_at=datetime.utcnow(),
                        status="active",
                    )
                )

            try:
                campaign_uid = UUID(campaign_id)
            except ValueError:
                pass
            else:
                await session.execute(
                    update(Campaign)
                    .where(Campaign.id == campaign_uid)
                    .values(
                        sent_count=Campaign.sent_count + 1,
                        updated_at=datetime.utcnow(),
                    )
                )

            await session.commit()

    async def _record_failure(
        self,
        campaign_id: str,
        prospect_id: str,
        error: str,
        recipient_email: str = "",
        subject: str = "",
        team_id: Any = None,
    ) -> None:
        """Record send failure in database including SendLog entry."""
        from app.db.postgres import async_session_maker
        from app.models.send_log import SendLog

        logger.error(
            "Send failed for campaign %s, prospect %s: %s",
            campaign_id,
            prospect_id,
            error,
        )

        async with async_session_maker() as session:
            failed_message_id = f"failed-{prospect_id}-{datetime.utcnow().timestamp()}"

            send_log = SendLog(
                message_id=failed_message_id,
                campaign_id=UUID(campaign_id) if campaign_id else None,
                prospect_id=UUID(prospect_id) if prospect_id else None,
                recipient_email=recipient_email,
                from_address="",
                subject=subject,
                status="failed",
                bounce_reason=error,
                sent_at=datetime.utcnow(),
                team_id=team_id,
            )
            session.add(send_log)

            try:
                campaign_uid = UUID(campaign_id)
            except ValueError:
                pass
            else:
                await session.execute(
                    update(Campaign)
                    .where(Campaign.id == campaign_uid)
                    .values(
                        bounced_count=Campaign.bounced_count + 1,
                        updated_at=datetime.utcnow(),
                    )
                )

            await session.commit()


campaign_send_service = CampaignSendService()
