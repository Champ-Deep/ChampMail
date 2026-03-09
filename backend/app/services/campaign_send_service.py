"""
Campaign Send Service.

Orchestrates the full campaign send pipeline. Takes a campaign and makes emails flow.
Connects: template resolution, scheduling, tracking injection, UTM injection, email delivery.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
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

    async def execute_single_send(
        self,
        campaign_id: str,
        prospect_id: str,
    ) -> Dict[str, Any]:
        """Send one email from a scheduled campaign.

        Called by Celery Beat when a scheduled send is due.
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

        # Test mode warning
        if is_test_mode_enabled():
            logger.warning("⚠️  TEST MODE: Sending email with DNS verification bypassed")

        logger.info("Sending email to %s for campaign %s (send_mode: %s)",
                   email_data["prospect_email"], campaign_id, send_mode)

        try:
            if send_mode == "server" and domain_id:
                result = await mail_engine_client.send_email(
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
            else:
                from app.db.postgres import async_session_maker

                async with async_session_maker() as email_session:
                    result = await email_service.send_email(
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

            await self._record_send(
                campaign_id=campaign_id,
                prospect_id=prospect_id,
                campaign_prospect_id=email_data["campaign_prospect_id"],
                message_id=result.message_id,
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
                "✓ Email sent successfully to %s for campaign %s (message_id: %s)",
                email_data["prospect_email"],
                campaign_id,
                result.message_id,
            )

            return {"status": "sent", "message_id": result.message_id}

        except Exception as e:
            logger.error(
                "✗ Failed to send email to %s for campaign %s: %s",
                email_data["prospect_email"],
                campaign_id,
                str(e),
            )
            await self._record_failure(
                campaign_id=campaign_id,
                prospect_id=prospect_id,
                error=str(e),
                recipient_email=email_data.get("prospect_email", ""),
                subject=email_data.get("subject", ""),
                team_id=campaign.team_id,
            )
            raise

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

            return {
                "status": "sent",
                "message_id": result.message_id,
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
