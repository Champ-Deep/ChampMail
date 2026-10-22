"""IMAP DSN poller: classify hard (5.x.x) vs soft (4.x.x), store both, emit `bounced` for hard only.

A 2.x.x DSN with Action: delivered is a real delivery receipt and emits `delivered` (never stored as
a bounce). An IMAP authentication failure pauses that one mailbox's sending (spec 3.12); the worker
never sets a mailbox back to active, and skips polling the mailboxes it paused until an operator
PATCHes them active.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import email
from email import policy
import hashlib
import imaplib
import logging
import re

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.crypto import decrypt_secret
from app.models.bounce import Bounce
from app.models.email_account import EmailAccount
from app.services.outbound_events import UnknownDispatch, emit

log = logging.getLogger("champmail.bounces")

_STATUS = re.compile(r"([245])\.\d{1,3}\.\d{1,3}")
# Server-side filter so non-DSN mail is never downloaded or marked read.
_SEARCH = '(UNSEEN HEADER Content-Type "report-type=delivery-status")'
IMAP_TIMEOUT_S = 20  # socket timeout per IMAP operation: a hung server cannot stall the whole poll
IMAP_AUTH_REASON = "imap_auth_failed"


@dataclass
class Dsn:
    status: str
    kind: str  # hard | soft | delivered
    message_id: str | None
    recipient: str | None
    diagnostic: str | None


def _bare(mid) -> str | None:
    # services/send.py returns (and clients store) the id without angle brackets.
    return str(mid or "").strip().strip("<>") or None


def parse_dsn(raw: bytes) -> Dsn | None:
    """Parse an RFC 3464 DSN. Returns None for anything that is not a failed/delayed DSN."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    status = recipient = diagnostic = message_id = action = None
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype == "message/delivery-status" and status is None:
            for block in part.get_payload():  # first block is per-message, the rest per-recipient
                m = _STATUS.match(str(block.get("Status", "")).strip())
                if m:
                    status = m.group(0)
                    recipient = str(block.get("Final-Recipient", "")).split(";")[-1].strip() or None
                    diagnostic = str(block.get("Diagnostic-Code", "")).strip() or None
                    action = str(block.get("Action", "")).strip().lower()
                    break
        elif ctype == "message/rfc822" and message_id is None:
            message_id = _bare(part.get_payload()[0].get("Message-ID"))
        elif ctype == "text/rfc822-headers" and message_id is None:
            message_id = _bare(email.message_from_string(part.get_payload()).get("Message-ID"))
    if status is None:
        return None
    if status[0] == "2":  # a receipt, never a bounce; only Action: delivered says the recipient's server took it
        return Dsn(status, "delivered", message_id, recipient, diagnostic) if action == "delivered" else None
    return Dsn(status, "hard" if status[0] == "5" else "soft", message_id, recipient, diagnostic)


@dataclass(frozen=True)
class Mailbox:
    """Plain copy of the IMAP fields: ORM rows expire on rollback and can't be read after it."""
    id: object
    email: str
    host: str
    port: int
    ssl: bool
    username: str
    password: str
    folder: str


def _snapshot(acc: EmailAccount) -> Mailbox:
    ssl = bool(acc.imap_use_ssl)
    return Mailbox(acc.id, acc.email, acc.imap_host, acc.imap_port or (993 if ssl else 143), ssl,
                   acc.imap_username or acc.email, decrypt_secret(acc.imap_password_encrypted),
                   acc.imap_mailbox or "INBOX")


class ImapAuthError(Exception):
    """The server refused this mailbox's credentials (as opposed to being unreachable or slow)."""


def _connect(mb: Mailbox) -> imaplib.IMAP4:
    conn = (imaplib.IMAP4_SSL if mb.ssl else imaplib.IMAP4)(mb.host, mb.port, timeout=IMAP_TIMEOUT_S)
    try:
        conn.login(mb.username, mb.password)
    except imaplib.IMAP4.error as e:  # raised only for a NO/BAD reply to LOGIN; network faults are OSError
        conn.shutdown()
        raise ImapAuthError(str(e)) from e
    conn.select(mb.folder)
    return conn


def _fetch_dsns(acc: Mailbox) -> list[tuple[bytes, bytes]]:
    """Return (uid, raw message) for each unseen DSN. BODY.PEEK leaves them unseen until stored."""
    conn = _connect(acc)
    try:
        _, data = conn.uid("SEARCH", None, _SEARCH)
        out = []
        for uid in data[0].split():
            _, msgs = conn.uid("FETCH", uid, "(BODY.PEEK[])")
            out.append((uid, msgs[0][1]))
        return out
    finally:
        conn.logout()


def _mark_seen(acc: Mailbox, uids: list[bytes]) -> None:
    conn = _connect(acc)
    try:
        for uid in uids:
            conn.uid("STORE", uid, "+FLAGS", "(\\Seen)")
    finally:
        conn.logout()


async def process_dsn(session, account_id, raw: bytes) -> str | None:
    """Store one DSN and queue its event in ONE transaction. Safe to run twice on the same DSN."""
    dsn = parse_dsn(raw)
    if dsn is None:
        return None
    if dsn.kind != "delivered":
        # ON CONFLICT instead of catching IntegrityError: a rollback would expire the
        # caller's EmailAccount and break the async lazy-load that follows.
        await session.execute(pg_insert(Bounce).values(
            email_account_id=account_id, dsn_hash=hashlib.sha256(raw).hexdigest(),
            message_id=dsn.message_id, recipient=dsn.recipient, status_code=dsn.status,
            kind=dsn.kind, diagnostic=dsn.diagnostic,
        ).on_conflict_do_nothing(index_elements=["dsn_hash"]))
    event = {"hard": "bounced", "delivered": "delivered"}.get(dsn.kind)
    if event and dsn.message_id:
        try:
            await emit(session, event, dsn.message_id)
        except UnknownDispatch:  # a DSN is not proof we sent it: no event for a message we never dispatched
            log.warning("%s DSN %s for %s quotes unknown Message-ID %s, not emitted", dsn.kind, dsn.status, dsn.recipient, dsn.message_id)
    elif event:
        log.warning("%s DSN %s for %s has no original Message-ID, not emitted", dsn.kind, dsn.status, dsn.recipient)
    await session.commit()
    return dsn.kind


async def poll_account(session, acc: Mailbox) -> int:
    dsns = await asyncio.to_thread(_fetch_dsns, acc)
    for _, raw in dsns:
        await process_dsn(session, acc.id, raw)
    if dsns:
        await asyncio.to_thread(_mark_seen, acc, [uid for uid, _ in dsns])
    return len(dsns)


async def _pause_for_auth_failure(session, acc: Mailbox, err: Exception) -> None:
    """Pause only this mailbox's sending. WHERE status='active' so a manual pause/retire keeps its own reason."""
    await session.rollback()
    res = await session.execute(
        update(EmailAccount).where(EmailAccount.id == acc.id, EmailAccount.status == "active")
        .values(status="paused", status_reason=f"{IMAP_AUTH_REASON}: {err}"[:500])
    )
    await session.commit()
    log.error("IMAP authentication failed for %s: %s", acc.email, "sending paused" if res.rowcount else "already not active, left as is")


async def poll_all(session) -> int:
    accounts = (await session.execute(
        select(EmailAccount).where(
            EmailAccount.is_active.is_(True),
            EmailAccount.imap_host.is_not(None),
            EmailAccount.imap_password_encrypted.is_not(None),
            # Paused by an earlier auth failure: do not hammer the login until an operator resumes it.
            ~((EmailAccount.status == "paused") & func.coalesce(EmailAccount.status_reason, "").startswith(IMAP_AUTH_REASON)),
        )
    )).scalars().all()
    boxes = []
    for acc in accounts:
        try:
            boxes.append(_snapshot(acc))
        except Exception:  # e.g. an undecryptable password: skip that mailbox only
            log.exception("bounce poll skipped %s", acc.email)
    total = 0
    for acc in boxes:
        try:
            total += await poll_account(session, acc)
        except ImapAuthError as e:
            await _pause_for_auth_failure(session, acc, e)
        except Exception:  # one broken mailbox must not stop the others
            log.exception("bounce poll failed for %s", acc.email)
            await session.rollback()
    return total
