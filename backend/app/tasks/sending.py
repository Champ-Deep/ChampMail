"""
Email sending tasks — uses local Postfix directly (no mail_engine_client).

Every send goes through:
  1. Pre-send validation (format, MX, role address, suppression list)
  2. Warmup-gated domain selection
  3. VERP bounce envelope injection
  4. Postfix submission (port 587, unauthenticated from internal network)
  5. Sent-count increment + send log
"""

import logging
import smtplib
import os
import asyncio
import random
from email.utils import formataddr, formatdate, make_msgid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from celery import shared_task
from app.db.postgres import async_session_maker as async_session
from app.services.domain_rotation import domain_rotator
from app.services.tracking_service import tracking_service

logger = logging.getLogger(__name__)

_SMTP_HOST = os.getenv("SMTP_HOST", "smtp")
_SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))


def _build_message(
    *,
    from_email: str,
    from_name: str,
    to_email: str,
    subject: str,
    body_text: str,
    html_body: str,
    bounce_address: str,
    tracking_id: str = None,
    unsubscribe_url: str = None,
) -> MIMEMultipart:
    """Build a fully-compliant multipart MIME message."""
    msg = MIMEMultipart("alternative")
    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    sender_domain = from_email.split("@")[1] if "@" in from_email else "localhost"
    msg["Message-ID"] = make_msgid(domain=sender_domain)
    msg["Date"] = formatdate(localtime=False)
    msg["MIME-Version"] = "1.0"
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = to_email

    if tracking_id and unsubscribe_url:
        mailto_unsub = f"mailto:{from_email}?subject=unsubscribe-{tracking_id}"
        msg["List-Unsubscribe"] = f"<{mailto_unsub}>, <{unsubscribe_url}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    return msg


def _submit_to_postfix(
    from_email: str,
    to_email: str,
    bounce_address: str,
    msg: MIMEMultipart,
) -> str:
    """Submit message to local Postfix via unauthenticated SMTP. Returns message-id."""
    server = smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=30)
    server.ehlo()
    # Use VERP bounce address as MAIL FROM envelope
    server.mail(bounce_address)
    server.rcpt(to_email)
    server.data(msg.as_string().encode())
    server.quit()
    return msg["Message-ID"]


def _jitter(base_seconds: int) -> int:
    """Apply ±30% jitter to a cadence interval."""
    delta = int(base_seconds * 0.30)
    return base_seconds + random.randint(-delta, delta)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_task(
    self,
    prospect_id: str,
    template_id: str,
    subject: str,
    html_body: str,
    domain_id: str = None,
    campaign_id: str = None,
):
    async def _send():
        from app.services.prospect_service import prospect_service
        from app.services.domain_service import domain_service
        from app.services.email_validator import email_validator
        from app.core.config import settings

        async with async_session() as session:
            prospect = await prospect_service.get_by_id(session, prospect_id)
            if not prospect:
                raise ValueError(f"Prospect {prospect_id} not found")

            to_email = prospect.get("email", "")
            to_name = prospect.get("name") or prospect.get("full_name") or ""

            # ── 1. Pre-send validation ────────────────────────────────────
            check = await email_validator.validate(to_email, session)
            if not check["valid"]:
                logger.warning("Skipping %s: %s", to_email, check["reason"])
                return {"skipped": True, "reason": check["reason"]}

            # ── 1b. Per-destination throttle ──────────────────────────────
            from app.services.destination_throttle import can_send as _throttle_ok
            if not await _throttle_ok(to_email):
                raise self.retry(
                    exc=ValueError(f"Throttle limit reached for {to_email.split('@')[1]}"),
                    countdown=_jitter(3600),  # retry in ~1 hour
                )

            # ── 2. Warmup-gated domain selection ─────────────────────────
            selected_domain_id = domain_id or await domain_rotator.select_domain(
                prospect.get("team_id")
            )
            if not selected_domain_id:
                raise ValueError("No available sending domain — all at warmup limit or paused")

            domain = await domain_service.get_by_id(session, selected_domain_id)
            if not domain:
                raise ValueError(f"Domain {selected_domain_id} not found")

            domain_name = domain["domain_name"]
            from_email = f"outreach@{domain_name}"
            from_name = settings.app_name

            # ── 3. VERP bounce envelope ───────────────────────────────────
            bounce_host = settings.bounce_domain or settings.mail_hostname
            bounce_address = f"bounce+{prospect_id}@{bounce_host}"

            # ── 4. Tracking injection ─────────────────────────────────────
            tracking_id = None
            unsubscribe_url = None
            final_html = html_body
            if campaign_id:
                try:
                    tracking_urls = await tracking_service.generate_tracking_urls(
                        campaign_id, prospect_id
                    )
                    tracking_id = tracking_urls.get("tracking_id")
                    unsubscribe_url = tracking_urls.get("unsubscribe_url")
                    final_html = tracking_service.wrap_links_in_html(
                        html_body,
                        tracking_urls["click_base_url"],
                        tracking_urls["signature"],
                    )
                    final_html = final_html.replace(
                        "{{tracking_url}}", tracking_urls.get("pixel_url", "")
                    )
                    final_html = final_html.replace(
                        "{{unsubscribe_url}}", unsubscribe_url or ""
                    )
                except Exception:
                    logger.debug("Tracking setup failed, sending without tracking", exc_info=True)

            # ── 5. Build + submit ─────────────────────────────────────────
            # Strip HTML tags for plain-text fallback
            import re
            body_text = re.sub(r"<[^>]+>", "", final_html).strip() or subject

            msg = _build_message(
                from_email=from_email,
                from_name=from_name,
                to_email=to_email,
                subject=subject,
                body_text=body_text,
                html_body=final_html,
                bounce_address=bounce_address,
                tracking_id=tracking_id,
                unsubscribe_url=unsubscribe_url,
            )
            message_id = _submit_to_postfix(from_email, to_email, bounce_address, msg)

            # ── 6. Post-send accounting ───────────────────────────────────
            await domain_service.increment_sent_count(session, selected_domain_id)
            await prospect_service.update_send_status(session, prospect_id, message_id)

            logger.info("Sent to %s via %s (msg=%s)", to_email, domain_name, message_id)
            return {"success": True, "message_id": message_id, "domain": domain_name}

    try:
        return asyncio.run(_send())
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_batch_task(
    self,
    campaign_id: str,
    prospect_ids: list,
    template_id: str,
    domain_id: str = None,
):
    """Queue individual send tasks for each prospect with ±30% jitter spacing."""
    from app.celery_app import celery_app
    from datetime import datetime, timedelta

    base_cadence = int(os.getenv("CAMPAIGN_CADENCE_SECONDS", "3600"))
    now = datetime.utcnow()

    for i, prospect_id in enumerate(prospect_ids):
        delay = _jitter(base_cadence) * i
        eta = now + timedelta(seconds=delay)
        send_email_task.apply_async(
            kwargs={
                "prospect_id": prospect_id,
                "template_id": template_id,
                "subject": "",  # fetched from prospect.personalized_subject in task
                "html_body": "",  # fetched from prospect.personalized_body in task
                "domain_id": domain_id,
                "campaign_id": campaign_id,
            },
            eta=eta,
            queue="sending",
        )

    logger.info("Queued %d sends for campaign %s with ±30%% jitter", len(prospect_ids), campaign_id)
    return {"queued": len(prospect_ids)}
