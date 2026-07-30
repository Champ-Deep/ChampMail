from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.postgres import get_db
from app.services.mail_engine_client import mail_engine_client
from app.services.domain_rotation import domain_rotator
from app.services.tracking_service import tracking_service
import asyncio
import logging

logger = logging.getLogger(__name__)


async def _emit_sent(result, *, to_email: str, subject: str, body: str,
                     campaign_id: str | None = None,
                     prospect_id: str | None = None) -> None:
    """Publish one `email.sent` event for a send made from a Celery task.

    Fire-and-forget by contract (see champiq_emit): a down or unset ChampIQ must
    never fail a send that already went out. The `extra` fields carry the
    identifiers the orchestrator needs to correlate the event back to a campaign
    and a specific mailbox — without them a ledger row cannot be attributed.
    """
    from app.services.champiq_emit import emit_email_event

    extra: dict = {}
    if campaign_id:
        extra["campaign_id"] = str(campaign_id)
    if prospect_id:
        extra["prospect_id"] = str(prospect_id)
    for attr in ("domain_id", "mailbox_id"):
        value = getattr(result, attr, None)
        if value:
            extra[attr] = str(value)

    try:
        await emit_email_event(
            "email.sent",
            to_email=to_email,
            from_email=getattr(result, "from_email", "") or "",
            subject=subject,
            body=body,
            message_id=getattr(result, "message_id", None),
            occurred_at=getattr(result, "sent_at", None),
            extra=extra or None,
        )
    except Exception:
        # ! emit_email_event already swallows its own transport errors; this is
        # ! the belt-and-braces guard so a shape/attribute surprise in `result`
        # ! cannot turn a delivered email into a retried Celery task.
        logger.exception("champiq emit failed for send to %s", to_email)


async def _inject_tracking(html_body: str, campaign_id: str, prospect_id: str) -> str:
    """Inject tracking pixel, click wrappers, and unsubscribe URL into HTML."""
    tracking_urls = await tracking_service.generate_tracking_urls(campaign_id, prospect_id)
    html = tracking_service.wrap_links_in_html(
        html_body,
        tracking_urls["click_base_url"],
        tracking_urls["signature"],
    )
    html = html.replace("{{tracking_url}}", tracking_urls.get("pixel_url", ""))
    html = html.replace("{{unsubscribe_url}}", tracking_urls.get("unsubscribe_url", ""))
    return html


async def _domain_uses_inboxkit(session, domain_id: str) -> bool:
    """True if the selected domain is InboxKit-provisioned.

    For InboxKit domains the send agent pulls SMTP creds from the IAL
    (decrypt at send time only) and sends directly, bypassing the Go
    mail-engine which is Stalwart-only.
    """
    if not domain_id:
        return False
    from app.models.domain import Domain
    from sqlalchemy import select
    stmt = select(Domain).where(Domain.id == domain_id)
    result = await session.execute(stmt)
    d = result.scalar_one_or_none()
    if d is None:
        return False
    return (getattr(d, "infra_provider", "stalwart") or "stalwart") == "inboxkit"


async def _send_via_inboxkit(session, domain_id: str, *, to_email: str, to_name: str,
                             subject: str, html_body: str, text_body: str = "",
                             from_name: str = "ChampMail") -> dict:
    """Send one email through an InboxKit-provisioned mailbox.

    Rotates across the domain's mailboxes (least-recently-used, under daily
    cap), pulls that mailbox's SMTP creds via the authenticated IAL call
    (re-fetch, never cached plaintext), and sends via SMTP. The Go mail-engine
    is bypassed for these domains.

    Returns the mailbox identifiers alongside the result so the caller can
    record the send against the right mailbox and emit an event carrying the
    real from-address.
    """
    from app.services.mail_infra import get_provider
    from app.services.mailbox_rotation import mailbox_rotator
    from app.models.domain import Domain
    from sqlalchemy import select

    stmt = select(Domain).where(Domain.id == domain_id)
    result = await session.execute(stmt)
    domain = result.scalar_one_or_none()
    if domain is None or not domain.inboxkit_domain_uid:
        raise RuntimeError(f"domain {domain_id} is not InboxKit-provisioned")

    # * Rotation, not `.limit(1)`. The old unordered single-row select returned
    # * the same mailbox on every call, so provisioning N mailboxes still sent
    # * everything through one of them.
    mailbox = await mailbox_rotator.select_mailbox(session, domain.id)

    provider = get_provider("inboxkit")
    creds = await provider.get_credentials(mailbox.inboxkit_uid)

    # SMTP send (synchronous — wrap in executor).
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.utils import make_msgid

    # * Set the Message-ID ourselves. This used to read `msg["Message-ID"]`
    # * *after* handing the message to smtplib — but the receiving server
    # * assigns that header, so the key was always None and the code fell back
    # * to a synthetic `<subject@champmail>` string. Nothing could then match a
    # * bounce or a reply back to the send, which breaks both reply threading
    # * and bounce correlation. Generating it up front makes the id we store
    # * the same one that goes out on the wire.
    message_id = make_msgid(domain=creds.email.split("@")[-1])

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{creds.email}>"
    msg["To"] = to_email
    msg["Message-ID"] = message_id
    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    loop = asyncio.get_event_loop()

    def _send_sync():
        with smtplib.SMTP(creds.smtp_host, creds.smtp_port, timeout=30) as server:
            server.starttls()
            server.login(creds.email, creds.password)
            server.send_message(msg)

    await loop.run_in_executor(None, _send_sync)

    # Count it before returning, so a caller that forgets cannot leave the
    # daily cap unenforced the way the previous code path did.
    await mailbox_rotator.record_send(session, mailbox.id, domain_id=domain.id)

    return {
        "message_id": message_id,
        "status": "sent",
        "domain_id": str(domain.id),
        "mailbox_id": str(mailbox.id),
        "from_email": creds.email,
        "sent_at": __import__("datetime").datetime.utcnow(),
    }


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_task(self, prospect_id: str, template_id: str, subject: str, html_body: str, domain_id: str = None, campaign_id: str = None):
    try:
        from app.db.postgres import async_session_maker
        from app.services.prospect_service import prospect_service

        async def _send():
            async with async_session_maker() as session:
                prospect = await prospect_service.get_by_id(session, prospect_id)
                if not prospect:
                    raise ValueError(f"Prospect {prospect_id} not found")

                to_email = prospect.get("email")
                to_name = prospect.get("name", "")

                selected_domain = domain_id
                if not selected_domain:
                    selected_domain = await domain_rotator.select_domain(prospect.get("team_id"))

                # Inject tracking: wrap links, add pixel, add unsubscribe
                final_html = html_body
                if campaign_id:
                    try:
                        final_html = await _inject_tracking(final_html, campaign_id, prospect_id)
                    except Exception:
                        pass  # Send even if tracking setup fails

                # Branch: InboxKit-provisioned domains send directly via the
                # IAL (creds pulled at send time, never cached plaintext);
                # Stalwart domains keep using the proven Go mail-engine.
                if await _domain_uses_inboxkit(session, selected_domain):
                    result_dict = await _send_via_inboxkit(
                        session, selected_domain,
                        to_email=to_email, to_name=to_name,
                        subject=subject, html_body=final_html,
                    )
                    class _R:
                        def __init__(self, d): self.__dict__.update(d)
                    result = _R(result_dict)
                else:
                    result = await mail_engine_client.send_email(
                        recipient=to_email,
                        recipient_name=to_name,
                        subject=subject,
                        html_body=final_html,
                        domain_id=selected_domain,
                        track_opens=True,
                        track_clicks=True,
                    )

                await prospect_service.update_send_status(session, prospect_id, result.message_id)

                # * Emit to ChampIQ. app/api/v1/send.py already did this; this
                # * task path did not, so every campaign/bulk send — the actual
                # * product — was invisible to the event bus, and therefore to
                # * Cham_Graph, the run ledger, and any event-triggered
                # * follow-up. Same class of bug as the documented 2026-07-23
                # * "finding #7", fixed in the sibling file but not here.
                await _emit_sent(
                    result,
                    to_email=to_email,
                    subject=subject,
                    body=final_html,
                    campaign_id=campaign_id,
                    prospect_id=prospect_id,
                )

                return result.__dict__

        return asyncio.run(_send())

    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_batch_task(self, campaign_id: str, prospect_ids: list[str], template_id: str, domain_id: str = None):
    try:
        from app.db.postgres import async_session_maker
        from app.services.prospect_service import prospect_service
        from app.services.campaigns import campaign_service

        async def _send():
            async with async_session_maker() as session:
                prospects = await prospect_service.get_by_ids(session, prospect_ids)
                if not prospects:
                    raise ValueError("No prospects found")

                selected_domain = domain_id
                if not selected_domain:
                    team_id = prospects[0].get("team_id") if prospects else None
                    selected_domain = await domain_rotator.select_domain(team_id)

                emails = []
                for prospect in prospects:
                    p_id = prospect.get("id", "")
                    html_body = prospect.get("personalized_body", "")

                    # Inject tracking per prospect
                    if campaign_id and html_body:
                        try:
                            html_body = await _inject_tracking(html_body, campaign_id, p_id)
                        except Exception:
                            pass  # Send even if tracking setup fails

                    emails.append({
                        "to": prospect.get("email"),
                        "to_name": prospect.get("name", ""),
                        "subject": prospect.get("personalized_subject", ""),
                        "html_body": html_body,
                        "track_opens": True,
                        "track_clicks": True,
                    })

                # ! KNOWN GAP (not fixed here): this path always uses the Go
                # ! mail-engine, even when `selected_domain` is InboxKit-
                # ! provisioned. send_email_task branches on
                # ! _domain_uses_inboxkit(); this one never does, so a batch on
                # ! an InboxKit domain is handed to an engine that holds no
                # ! credentials for it. Fixing it means looping per-prospect
                # ! through _send_via_inboxkit (losing the batch API) or adding
                # ! a batch path to the IAL — a design call, not a patch.
                if await _domain_uses_inboxkit(session, selected_domain):
                    logger.warning(
                        "send_batch_task: domain %s is InboxKit-provisioned but "
                        "the batch path only supports the Go mail-engine; sends "
                        "will likely fail. Use send_email_task per prospect.",
                        selected_domain,
                    )

                result = await mail_engine_client.send_batch(emails=emails, domain_id=selected_domain)

                await campaign_service.update_stats(session, campaign_id, result.successful, result.failed)

                # * Emit one event per successful send. Batch volume was
                # * entirely invisible to the bus before this.
                for sent, r in zip(emails, getattr(result, "results", []) or []):
                    if getattr(r, "status", None) in ("failed", "suppressed"):
                        continue
                    await _emit_sent(
                        r,
                        to_email=sent.get("to") or "",
                        subject=sent.get("subject") or "",
                        body=sent.get("html_body") or "",
                        campaign_id=campaign_id,
                    )

                return result.__dict__

        return asyncio.run(_send())

    except Exception as exc:
        raise self.retry(exc=exc)
