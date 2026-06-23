"""Reply-ingestion Celery task — IMAP poll → classify → prospect-level auto-pause.

Wraps the pure cores in `services/reply_ingest.py` with a real imaplib mailbox
adapter and DB-bound callbacks: a genuine reply pauses that prospect's remaining
sequence steps; a free-text opt-out suppresses the address. The classification +
thread-matching logic is unit-tested offline; this is the I/O wiring.
"""
from __future__ import annotations

import email
import imaplib
import logging
from email.header import decode_header, make_header

from celery import shared_task
from sqlalchemy import select

from app.db.postgres import async_session
from app.models.sequence import SequenceEnrollment
from app.models.send_log import SendLog
from app.services.reply_ingest import InboundMessage, ReplyIngestService
from app.services.suppression_service import suppression_service

logger = logging.getLogger(__name__)


def _hdr(msg, name: str) -> str:
    raw = msg.get(name, "")
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return raw or ""


def _body_text(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", "replace")
        return ""
    payload = msg.get_payload(decode=True)
    return payload.decode("utf-8", "replace") if payload else (msg.get_payload() or "")


class IMAPMailbox:
    """Adapts an IMAP mailbox to the MailboxClient protocol (fetch_unseen)."""

    def __init__(self, host: str, user: str, password: str, port: int = 993):
        self.host, self.user, self.password, self.port = host, user, password, port

    def fetch_unseen(self):
        out = []
        conn = imaplib.IMAP4_SSL(self.host, self.port)
        try:
            conn.login(self.user, self.password)
            conn.select("INBOX")
            _, data = conn.search(None, "UNSEEN")
            for num in (data[0].split() if data and data[0] else []):
                _, msg_data = conn.fetch(num, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                out.append(InboundMessage(
                    return_path=_hdr(msg, "Return-Path"),
                    auto_submitted=_hdr(msg, "Auto-Submitted"),
                    precedence=_hdr(msg, "Precedence"),
                    subject=_hdr(msg, "Subject"),
                    in_reply_to=_hdr(msg, "In-Reply-To"),
                    references=_hdr(msg, "References"),
                    from_addr=email.utils.parseaddr(_hdr(msg, "From"))[1].lower(),
                    body=_body_text(msg),
                ))
        finally:
            try:
                conn.logout()
            except Exception:
                pass
        return out


@shared_task(bind=True, queue="sending")
def ingest_replies(self, host: str, user: str, password: str, port: int = 993):
    import asyncio

    async def _run():
        async with async_session() as session:
            # Known outbound Message-IDs to match replies against (recent window).
            rows = await session.execute(
                select(SendLog.message_id).order_by(SendLog.sent_at.desc()).limit(5000)
            )
            known = {f"<{r[0]}>" for r in rows.all() if r[0]}

            async def pause_enrollment(message_id: str, from_addr: str):
                # Find the send → its enrollment → pause that prospect's steps.
                sl = (await session.execute(
                    select(SendLog).where(SendLog.message_id == message_id)
                )).scalar_one_or_none()
                if sl and getattr(sl, "sequence_enrollment_id", None):
                    enr = await session.get(SequenceEnrollment, sl.sequence_enrollment_id)
                    if enr:
                        enr.status = "paused"
                        enr.pause_reason = "reply_detected"
                logger.info("paused enrollment for reply %s from %s", message_id, from_addr)

            async def suppress(from_addr: str):
                await suppression_service.add(session, None, from_addr,
                                              reason="reply_optout", source="imap")
                logger.info("suppressed %s (free-text opt-out)", from_addr)

            # The service core is sync; run callbacks via a small bridge.
            pending: list = []
            svc = ReplyIngestService(
                IMAPMailbox(host, user, password, port),
                resolve_message_ids=lambda: known,
                on_reply=lambda mid, frm: pending.append(("reply", mid, frm)),
                on_optout=lambda frm: pending.append(("optout", frm)),
            )
            outcomes = svc.run_once()
            for item in pending:
                if item[0] == "reply":
                    await pause_enrollment(item[1], item[2])
                else:
                    await suppress(item[1])
            await session.commit()
            logger.info("reply ingest: %d messages processed", len(outcomes))

    asyncio.run(_run())
