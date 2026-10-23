"""Send path: atomic mailbox claim, message build, SMTP submission.

Harbinger guardrails.ts values: 30/day per mailbox (column default), 45s floor
plus up to 90s jitter between sends from one mailbox.
"""
from __future__ import annotations

import hashlib
import html as htmllib
import json
import random
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Callable, Optional
from uuid import UUID

import aiosmtplib
from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import decrypt_secret
from app.models import Domain, EmailAccount, SendDispatch
from app.services import tracking

MIN_GAP_S = 45
JITTER_S = 90
CANARY_DAILY_CAP = 6  # per domain per UTC day, separate from every mailbox's campaign cap
CANARY_DOMAIN_OK = ("active", "paused")  # never retired


class SendRefused(Exception):
    """A send the caller must not retry as-is. `status` is the HTTP status."""

    def __init__(self, status: int, code: str, detail: str, retry_after: Optional[int] = None):
        super().__init__(detail)
        self.status, self.code, self.detail, self.retry_after = status, code, detail, retry_after


class DuplicateKey(Exception):
    """The idempotency key (or the failed row being retried) was taken by another request first."""


class NotAttempted(Exception):
    """Failed before any network I/O (e.g. credential decryption), so nothing was submitted."""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # columns are naive UTC


def random_gap_s() -> float:
    return MIN_GAP_S + random.random() * JITTER_S


@dataclass
class Claimed:
    mailbox: EmailAccount
    domain: Domain
    message_id: str = ""
    dispatch_id: Optional[UUID] = None


def _eligible(now: datetime, today: date):
    """Everything a mailbox must satisfy to send, evaluated inside the claim itself."""
    under_cap = or_(
        EmailAccount.sent_today_date.is_(None),
        EmailAccount.sent_today_date != today,
        EmailAccount.sent_today < EmailAccount.daily_send_limit,
    )
    return and_(
        EmailAccount.is_active.is_(True),
        EmailAccount.status == "active",
        EmailAccount.smtp_host.is_not(None),
        EmailAccount.smtp_password_encrypted.is_not(None),
        under_cap,
        or_(EmailAccount.next_send_at.is_(None), EmailAccount.next_send_at <= now),
        Domain.paused.is_not(True),
        Domain.blacklisted.is_not(True),
        Domain.send_status == "active",
        Domain.status.not_in(("paused", "retired")),
        func.coalesce(Domain.tracking_subdomain, "") != "",
    )


def _canary_eligible(today: date):
    """A canary may use a paused domain, but not a retired or blacklisted one, nor an inactive,
    paused or retired mailbox. No mailbox cap and no send gap: those belong to campaign sends."""
    return and_(
        EmailAccount.is_active.is_(True),
        EmailAccount.status == "active",
        EmailAccount.smtp_host.is_not(None),
        EmailAccount.smtp_password_encrypted.is_not(None),
        Domain.blacklisted.is_not(True),
        Domain.send_status.in_(CANARY_DOMAIN_OK),
        func.coalesce(Domain.status, "") != "retired",
        func.coalesce(Domain.tracking_subdomain, "") != "",
        or_(Domain.canary_sends_date.is_(None), Domain.canary_sends_date != today,
            Domain.canary_sends_today < CANARY_DAILY_CAP),
    )


def _selector(mailbox_id, email, brand_id, domain_id):
    conds = []
    if mailbox_id:
        conds.append(EmailAccount.id == mailbox_id)
    if email:
        conds.append(func.lower(EmailAccount.email) == email.lower())
    if brand_id:
        conds.append(Domain.brand_id == brand_id)
    if domain_id:
        conds.append(Domain.id == domain_id)
    return conds


async def claim_mailbox(
    session: AsyncSession,
    *,
    mailbox_id: Optional[UUID] = None,
    email: Optional[str] = None,
    brand_id: Optional[str] = None,
    domain_id: Optional[UUID] = None,
    gap_s: Callable[[], float] = random_gap_s,
    idempotency_key: Optional[str] = None,
    payload_hash: str = "",
    retry_dispatch_id: Optional[UUID] = None,
    canary: bool = False,
) -> Claimed:
    """Claim one send slot in a single UPDATE ... WHERE under-cap RETURNING.

    The subquery picks the least-recently-used eligible row and locks it. Pooled
    picks use SKIP LOCKED so concurrent claimers fan out over different mailboxes;
    a named mailbox waits for the lock and is re-checked, so the cap stays exact. The
    outer UPDATE repeats the eligibility test, so a row that stopped being
    eligible between pick and write is not claimed.

    The slot and the send_dispatches row (message identity, mailbox, domain, key) commit in ONE
    transaction, before SMTP. A concurrent request with the same idempotency_key loses on the
    unique index, rolls its slot back and raises DuplicateKey; `retry_dispatch_id` re-uses a
    `failed` row instead of inserting (DuplicateKey if someone else already retried it).
    """
    now = _now()
    today = now.date()
    if canary:
        claimed_id = await _claim_canary_slot(session, today, mailbox_id, email, brand_id, domain_id)
        if claimed_id is None:
            await session.rollback()
            raise await _diagnose(session, mailbox_id, email, brand_id, domain_id, now, today, canary=True)
    else:
        claimed_id = await _claim_campaign_slot(session, now, today, gap_s, mailbox_id, email, brand_id, domain_id)
        if claimed_id is None:
            await session.rollback()
            raise await _diagnose(session, mailbox_id, email, brand_id, domain_id, now, today)
    return await _record_dispatch(session, claimed_id, now, idempotency_key, payload_hash, retry_dispatch_id, canary)


async def _claim_canary_slot(session, today, mailbox_id, email, brand_id, domain_id) -> Optional[UUID]:
    """Pick any eligible mailbox (shared row lock, so a concurrent retire waits) and take one slot of the
    domain's canary counter in a single guarded UPDATE: the domain row lock makes the cap exact."""
    elig = _canary_eligible(today)
    pick = (
        select(EmailAccount.id, EmailAccount.domain_id)
        .join(Domain, Domain.id == EmailAccount.domain_id)
        .where(elig, *_selector(mailbox_id, email, brand_id, domain_id))
        .order_by(func.random())
        .limit(1)
        .with_for_update(read=True, of=EmailAccount)
    )
    picked = (await session.execute(pick)).first()
    if picked is None:
        return None
    took = await session.execute(
        update(Domain)
        .where(Domain.id == picked.domain_id, Domain.send_status.in_(CANARY_DOMAIN_OK),
               func.coalesce(Domain.status, "") != "retired", Domain.blacklisted.is_not(True),
               or_(Domain.canary_sends_date.is_(None), Domain.canary_sends_date != today,
                   Domain.canary_sends_today < CANARY_DAILY_CAP))
        .values(canary_sends_today=case((Domain.canary_sends_date == today, Domain.canary_sends_today + 1), else_=1),
                canary_sends_date=today)
        .returning(Domain.id)
        .execution_options(synchronize_session=False)
    )
    return picked.id if took.scalar_one_or_none() is not None else None


async def _claim_campaign_slot(session, now, today, gap_s, mailbox_id, email, brand_id, domain_id) -> Optional[UUID]:
    elig = _eligible(now, today)
    pick = (
        select(EmailAccount.id)
        .join(Domain, Domain.id == EmailAccount.domain_id)
        .where(elig, *_selector(mailbox_id, email, brand_id, domain_id))
        .order_by(EmailAccount.last_send_at.asc().nulls_first())
        .limit(1)
        .with_for_update(of=EmailAccount, skip_locked=not (mailbox_id or email))
        .scalar_subquery()
    )
    stmt = (
        update(EmailAccount)
        .where(EmailAccount.id == pick, EmailAccount.domain_id == Domain.id, elig)
        .values(
            sent_today=case((EmailAccount.sent_today_date == today, EmailAccount.sent_today + 1), else_=1),
            sent_today_date=today,
            last_send_at=now,
            next_send_at=now + timedelta(seconds=gap_s()),
        )
        .returning(EmailAccount.id)
        .execution_options(synchronize_session=False)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _record_dispatch(session, claimed_id, now, idempotency_key, payload_hash, retry_dispatch_id, canary) -> Claimed:
    box = (await session.execute(select(EmailAccount).where(EmailAccount.id == claimed_id))).scalar_one()
    dom = (await session.execute(select(Domain).where(Domain.id == box.domain_id))).scalar_one()
    message_id = make_msgid(domain=(box.from_email or box.email).rsplit("@", 1)[-1]).strip("<>")
    try:
        if retry_dispatch_id:
            reused = await session.execute(
                update(SendDispatch)
                .where(SendDispatch.id == retry_dispatch_id, SendDispatch.status == "failed")
                .values(message_id=message_id, mailbox_id=box.id, domain_id=dom.id, status="sending",
                        response=None, canary=canary, updated_at=now)
                .returning(SendDispatch.id)
            )
            if reused.scalar_one_or_none() is None:
                raise DuplicateKey()
            dispatch_id = retry_dispatch_id
        else:
            row = SendDispatch(message_id=message_id, domain_id=dom.id, mailbox_id=box.id,
                               idempotency_key=idempotency_key, payload_hash=payload_hash, status="sending",
                               canary=canary)
            session.add(row)
            await session.flush()
            dispatch_id = row.id
        await session.commit()
    except (IntegrityError, DuplicateKey) as e:
        await session.rollback()
        if isinstance(e, IntegrityError) and not idempotency_key:
            raise
        raise DuplicateKey() from None
    return Claimed(box, dom, message_id, dispatch_id)


def payload_fingerprint(body: dict) -> str:
    """Hash of the logical request, for idempotency CONFLICT detection only (never a dedupe key)."""
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def find_dispatch(session: AsyncSession, key: str) -> Optional[SendDispatch]:
    # Fresh read: the row may have been written by a request that committed after our transaction began.
    await session.rollback()
    return (await session.execute(select(SendDispatch).where(SendDispatch.idempotency_key == key))).scalar_one_or_none()


async def finish_dispatch(session: AsyncSession, dispatch_id: UUID, status: str, *,
                          response: Optional[dict] = None, release_mailbox: Optional[UUID] = None,
                          release_canary_domain: Optional[UUID] = None) -> None:
    """Record the SMTP outcome. Only a definite refusal (`failed`) gives the cap slot back."""
    await session.execute(
        update(SendDispatch).where(SendDispatch.id == dispatch_id).values(status=status, response=response, updated_at=_now())
    )
    if release_mailbox:
        await session.execute(
            update(EmailAccount)
            .where(EmailAccount.id == release_mailbox, EmailAccount.sent_today_date == _now().date(), EmailAccount.sent_today > 0)
            .values(sent_today=EmailAccount.sent_today - 1)
        )
    if release_canary_domain:
        await session.execute(
            update(Domain)
            .where(Domain.id == release_canary_domain, Domain.canary_sends_date == _now().date(), Domain.canary_sends_today > 0)
            .values(canary_sends_today=Domain.canary_sends_today - 1)
        )
    await session.commit()


def is_definite_refusal(exc: BaseException) -> bool:
    """True only when the message provably was NOT accepted (safe to retry).

    Connect failures, auth/sender/recipient refusals and explicit 4xx/5xx replies qualify.
    Timeouts, disconnects and anything unrecognised may have happened after the server took the
    message, so they are ambiguous: the slot stays spent and nothing is retransmitted.
    """
    return isinstance(exc, (NotAttempted, aiosmtplib.SMTPConnectError, aiosmtplib.SMTPResponseException,
                            aiosmtplib.SMTPRecipientsRefused, aiosmtplib.SMTPNotSupported))


async def _diagnose(session, mailbox_id, email, brand_id, domain_id, now, today, canary=False) -> SendRefused:
    """Why nothing was claimed. Runs only on the failure path, so Python-side is fine."""
    conds = _selector(mailbox_id, email, brand_id, domain_id)
    rows = (
        await session.execute(
            select(EmailAccount, Domain).join(Domain, Domain.id == EmailAccount.domain_id).where(*conds)
        )
    ).all()
    if not rows:
        return SendRefused(404, "no_mailbox", "no mailbox matches the request")
    best: tuple[int, SendRefused] = (-1, SendRefused(404, "no_mailbox", "no mailbox matches the request"))
    for box, dom in rows:
        if box.status in ("paused", "retired") or not box.is_active:
            r = (0, SendRefused(409, f"mailbox_{box.status}", f"mailbox is {box.status if box.is_active else 'inactive'}"))
        elif dom.send_status not in (CANARY_DOMAIN_OK if canary else ("active",)):
            r = (0, SendRefused(409, f"domain_{dom.send_status}", f"domain is {dom.send_status}"))
        elif dom.blacklisted or dom.status == "retired" or (not canary and (dom.paused or dom.status == "paused")):
            why = "blacklisted" if dom.blacklisted else (dom.status if dom.status in ("paused", "retired") else "paused")
            r = (0, SendRefused(409, f"domain_{why}", f"domain is {why}"))
        elif not box.smtp_host or not box.smtp_password_encrypted:
            r = (1, SendRefused(409, "no_smtp_credentials", "mailbox has no SMTP credentials"))
        elif not (dom.tracking_subdomain or "").strip():
            # Hard error by design: never fall back to a shared tracking host.
            r = (2, SendRefused(500, "tracking_subdomain_missing", f"domain {dom.domain_name} has no tracking subdomain"))
        elif canary:
            capped = dom.canary_sends_date == today and dom.canary_sends_today >= CANARY_DAILY_CAP
            r = (3, SendRefused(429, "canary_cap", f"domain at its canary cap of {CANARY_DAILY_CAP} today") if capped
                 else SendRefused(429, "throttled", "canary slot was taken by a concurrent request", retry_after=1))
        elif box.sent_today_date == today and box.sent_today >= box.daily_send_limit:
            r = (3, SendRefused(429, "daily_cap", f"mailbox at daily cap {box.daily_send_limit}"))
        else:
            wait = max(1, int((box.next_send_at - now).total_seconds())) if box.next_send_at else 1
            r = (4, SendRefused(429, "throttled", "mailbox is inside its send gap", retry_after=wait))
        if r[0] > best[0]:
            best = r
    return best[1]


# --- message -----------------------------------------------------------------

_HREF = re.compile(r'href="(https?://[^"]+)"', re.I)


def build_message(
    claimed: Claimed,
    *,
    to: str,
    subject: str,
    html_body: Optional[str],
    text_body: Optional[str],
    from_name: Optional[str],
    reply_to: Optional[str],
    unsubscribe_url: Optional[str],
    track_opens: bool,
    track_clicks: bool,
    extra_headers: Optional[dict[str, str]] = None,
) -> tuple[EmailMessage, str]:
    box, dom = claimed.mailbox, claimed.domain
    host = (dom.tracking_subdomain or "").strip()
    if not host:  # defense in depth; the claim already excludes this
        raise SendRefused(500, "tracking_subdomain_missing", f"domain {dom.domain_name} has no tracking subdomain")
    address = box.from_email or box.email
    message_id = claimed.message_id

    msg = EmailMessage()
    msg["From"] = formataddr((from_name or box.from_name or "", address))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = f"<{message_id}>"
    if reply_to or box.reply_to_email:
        msg["Reply-To"] = reply_to or box.reply_to_email
    for name, value in (extra_headers or {}).items():
        msg[name] = value
    if unsubscribe_url:  # RFC 8058 one-click
        msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    msg.set_content(text_body or "")
    if html_body:
        html = html_body
        if track_clicks:
            # The attribute value is HTML-escaped; sign the real URL. Each link gets its own signed token.
            def wrap(m):
                url = htmllib.unescape(m.group(1))
                return f'href="https://{host}/c/{tracking.sign("c", message_id, dom.id, url)}"' if tracking.is_http_url(url) else m.group(0)
            html = _HREF.sub(wrap, html)
        if track_opens:
            html += f'<img src="https://{host}/o/{tracking.sign("o", message_id, dom.id)}.gif" width="1" height="1" alt="" style="display:none">'
        msg.add_alternative(html, subtype="html")
    return msg, message_id


async def submit_smtp(box: EmailAccount, msg: EmailMessage) -> None:
    try:
        password = decrypt_secret(box.smtp_password_encrypted)
    except Exception as e:
        raise NotAttempted(type(e).__name__) from e
    port = box.smtp_port or 587
    await aiosmtplib.send(
        msg,
        hostname=box.smtp_host,
        port=port,
        username=box.smtp_username or box.email,
        password=password or None,
        use_tls=port == 465,
        start_tls=bool(box.smtp_use_tls) and port != 465,
        timeout=20,
    )
