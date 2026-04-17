"""
Celery tasks for sequence execution, reply detection, and IMAP unsubscribe processing.

Each task follows Single Responsibility:
- execute_pending_steps: send one due step per prospect per run (cadence-aware)
- check_replies_and_pause: IMAP scan for replies -> pause sequences
- process_imap_unsubscribes: IMAP scan for unsubscribe emails -> mark prospects
- pause_sequence / resume_sequence: manual control
"""

from celery import shared_task
from app.db.postgres import async_session_maker as async_session
from datetime import datetime, timedelta
import asyncio
import imaplib
import email as email_lib
import logging
import re
import ssl

logger = logging.getLogger(__name__)

# Max steps to send per single Celery Beat tick (prevents runaway sends)
MAX_STEPS_PER_TICK = 5


@shared_task(bind=True, queue="sequences")
def execute_pending_steps(self):
    """Send pending sequence steps, respecting cadence.

    Only processes steps whose scheduled time has passed (next_step_at <= now).
    Caps at MAX_STEPS_PER_TICK per run to enforce natural cadence via the
    5-minute Celery Beat interval.
    """

    async def _execute():
        from app.services.sequence_service import sequence_service
        from app.services.mail_engine_client import mail_engine_client
        from app.services.domain_rotation import domain_rotator
        from app.db.champgraph import graph_db

        async with async_session() as session:
            pending_steps = await sequence_service.get_pending_steps(session)

            sent_count = 0
            for step in pending_steps:
                if sent_count >= MAX_STEPS_PER_TICK:
                    logger.info("Cadence cap reached (%d), deferring remaining steps", MAX_STEPS_PER_TICK)
                    break

                try:
                    domain_id = await domain_rotator.select_domain(step.get("team_id"))

                    result = await mail_engine_client.send_email(
                        recipient=step.get("prospect_email"),
                        recipient_name=step.get("prospect_name"),
                        subject=step.get("subject"),
                        html_body=step.get("body"),
                        domain_id=domain_id or "",
                        track_opens=True,
                        track_clicks=True,
                    )

                    await sequence_service.mark_step_sent(session, step.get("id"), result.message_id)
                    sent_count += 1

                    # Record in ChampGraph for relationship intelligence
                    await graph_db.record_email_sent(
                        prospect_email=step.get("prospect_email", ""),
                        sequence_id=int(step.get("sequence_id", 0)) if str(step.get("sequence_id", "")).isdigit() else 0,
                        step_number=step.get("step_order", 0),
                        subject=step.get("subject", ""),
                        body_hash=str(hash(step.get("body", ""))),
                    )

                    await sequence_service.schedule_next_step(
                        session,
                        step.get("sequence_id"),
                        step.get("prospect_id"),
                        step.get("step_order") + 1,
                    )

                except Exception as e:
                    await sequence_service.mark_step_failed(session, step.get("id"), str(e))

    asyncio.run(_execute())


@shared_task(bind=True, queue="sequences")
def pause_sequence(self, sequence_id: str, prospect_id: str = None, reason: str = "manual"):
    async def _pause():
        from app.services.sequence_service import sequence_service

        async with async_session() as session:
            await sequence_service.pause(session, sequence_id, prospect_id, reason)

    asyncio.run(_pause())


@shared_task(bind=True, queue="sequences")
def resume_sequence(self, sequence_id: str, prospect_id: str = None):
    async def _resume():
        from app.services.sequence_service import sequence_service

        async with async_session() as session:
            await sequence_service.resume(session, sequence_id, prospect_id)

    asyncio.run(_resume())


@shared_task(bind=True, queue="sequences")
def check_replies_and_pause(self):
    """Scan for replies via mail-engine and pause sequences for responders."""

    async def _check():
        from app.services.sequence_service import sequence_service
        from app.services.mail_engine_client import mail_engine_client

        async with async_session() as session:
            active_sequences = await sequence_service.get_active_sequences(session)

            for seq in active_sequences:
                prospect_ids = await sequence_service.get_enrolled_prospect_ids(session, seq.get("id"))

                for prospect_id in prospect_ids:
                    try:
                        has_replied = await mail_engine_client.check_for_replies(
                            prospect_email=seq.get("prospect_email", "")
                        )

                        if has_replied:
                            await sequence_service.pause(
                                session, seq.get("id"), prospect_id, reason="reply_detected"
                            )
                    except Exception:
                        pass  # Best effort reply detection

    asyncio.run(_check())


# ---------------------------------------------------------------------------
# IMAP Unsubscribe Processing (Phase 2)
# ---------------------------------------------------------------------------

# Pattern to extract tracking_id from unsubscribe subject lines.
# The List-Unsubscribe mailto header sets: subject=unsubscribe-{tracking_id}
_UNSUB_SUBJECT_RE = re.compile(r"unsubscribe-(\S+)", re.IGNORECASE)


@shared_task(bind=True, queue="sequences")
def process_imap_unsubscribes(self):
    """Scan all active email accounts' IMAP inboxes for unsubscribe emails.

    Flow:
    1. For each active EmailAccount with IMAP configured, connect via IMAP
    2. SEARCH for subjects containing "unsubscribe-"
    3. Extract tracking_id from subject
    4. Delegate to tracking_service.handle_unsubscribe() (already marks
       prospect as unsubscribed, updates CampaignProspect, increments counters)
    5. Mark the unsubscribe email as seen + move to Trash (housekeeping)

    Runs every 5 minutes via Celery Beat. Honors unsubscribes well within
    the 48-hour window required by Gmail, Yahoo, and Microsoft.
    """

    async def _process():
        from app.services.email_account_service import email_account_service
        from app.services.tracking_service import tracking_service
        from sqlalchemy import select
        from app.models.email_account import EmailAccount

        async with async_session() as session:
            # Get all active email accounts with IMAP configured
            result = await session.execute(
                select(EmailAccount).where(
                    EmailAccount.is_active == True,  # noqa: E712
                    EmailAccount.imap_host.isnot(None),
                    EmailAccount.imap_host != "",
                )
            )
            accounts = result.scalars().all()

        for account in accounts:
            try:
                imap_password = email_account_service.get_decrypted_imap_password(account)
                if not imap_password or not account.imap_host:
                    continue

                processed = _scan_imap_for_unsubscribes(
                    host=account.imap_host,
                    port=account.imap_port or 993,
                    username=account.imap_username or account.email,
                    password=imap_password,
                    use_ssl=account.imap_use_ssl if account.imap_use_ssl is not None else True,
                )

                # Process each unsubscribe via the tracking service
                for tracking_id in processed:
                    try:
                        await tracking_service.handle_unsubscribe(tracking_id)
                        logger.info("IMAP unsubscribe processed: tracking_id=%s account=%s", tracking_id, account.email)
                    except Exception:
                        logger.warning("Failed to process unsubscribe for tracking_id=%s", tracking_id, exc_info=True)

            except Exception:
                logger.warning("IMAP unsubscribe scan failed for account %s", account.email, exc_info=True)

    asyncio.run(_process())


def _scan_imap_for_unsubscribes(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    use_ssl: bool,
) -> list[str]:
    """Connect to IMAP, find unsubscribe emails, extract tracking IDs, clean up.

    Returns a list of tracking_id strings extracted from matching subjects.
    This is a synchronous function (IMAP is inherently synchronous).
    """
    tracking_ids: list[str] = []

    try:
        ctx = ssl.create_default_context()
        if use_ssl:
            server = imaplib.IMAP4_SSL(host, port, ssl_context=ctx)
        else:
            server = imaplib.IMAP4(host, port)

        server.login(username, password)
        server.select("INBOX")

        # Search for unsubscribe emails by subject
        _, msg_nums = server.search(None, '(SUBJECT "unsubscribe-")')
        if not msg_nums or not msg_nums[0]:
            server.logout()
            return tracking_ids

        for msg_num in msg_nums[0].split():
            try:
                _, msg_data = server.fetch(msg_num, "(RFC822.HEADER)")
                if not msg_data or msg_data[0] is None:
                    continue

                header_bytes = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
                msg = email_lib.message_from_bytes(header_bytes)
                subject = msg.get("Subject", "")

                match = _UNSUB_SUBJECT_RE.search(subject)
                if match:
                    tracking_ids.append(match.group(1))
                    # Mark as seen and flag for deletion
                    server.store(msg_num, "+FLAGS", "\\Seen")
                    server.store(msg_num, "+FLAGS", "\\Deleted")

            except Exception:
                logger.debug("Failed to parse IMAP message %s", msg_num, exc_info=True)

        # Expunge deleted messages
        server.expunge()
        server.logout()

    except Exception:
        logger.warning("IMAP connection failed: %s@%s:%d", username, host, port, exc_info=True)

    return tracking_ids
