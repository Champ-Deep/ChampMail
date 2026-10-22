"""
InboxKit webhook ingress — the 4-event handler with re-fetch pattern.

Verified events (docs.inboxkit.com, 2026-07-28):
- domain.status_changed
- mailbox.status_changed
- consent_request.status_changed
- client_id_request.status_changed

Security model (verified, see INBOXKIT_AUDIT_AND_PLAN.md §2.3):
- The X-InboxKit-Signature is a STATIC SHA-256 of the team API key, NOT an
  HMAC. The body is not part of the hash. An intercepted signature can be
  replayed with any body.
- Therefore: HTTPS is mandatory, every webhook is a HINT only, and we
  re-fetch authoritative state via the authenticated REST API before
  mutating anything.
- Credentials (password/app_password/secret) arriving in the webhook body
  are DISCARDED. Only GET /v1/api/mailboxes/show-credentials is trusted.

Idempotency: key = event + entity_uid + new_status, in a short-TTL Redis
value (24h), written only AFTER the local write landed — an event whose
handler crashed is not "processed", so InboxKit's next delivery retries it.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel

from app.config import get_settings
from app.crypto import encrypt_secret
from app.db.redis import redis_client
from app.services.inboxkit.provider import InboxKitProvider
from app.services.inboxkit.states import to_logical_state, LogicalState

settings = get_settings()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/inboxkit", tags=["InboxKit Webhooks"])

_IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60   # 24h — InboxKit retries up to 3x within minutes
_FRESHNESS_WINDOW_SECONDS = 300            # reject webhooks older than 5 min (replay defence)


# ---------------------------------------------------------------------------
# Payload models (envelope + per-event data)
# ---------------------------------------------------------------------------

class _Metadata(BaseModel):
    updated_at: Optional[str] = None
    workspace_id: Optional[str] = None


class _Envelope(BaseModel):
    event: str
    timestamp: str
    team_id: Optional[str] = None
    team_name: Optional[str] = None
    data: dict[str, Any]


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------

def _expected_signature() -> Optional[str]:
    """sha256=<lowercase hex SHA-256(team_api_key)> — static per team."""
    if not settings.inboxkit_api_key:
        return None
    digest = hashlib.sha256(settings.inboxkit_api_key.encode()).hexdigest()
    return f"sha256={digest}"


def _verify_signature(received: Optional[str], expected: Optional[str]) -> bool:
    """Constant-time comparison. Dev mode allows missing signature if no key set."""
    if expected is None:
        # No API key configured — allow in development only (mirrors webhooks.py).
        if settings.champmail_env.strip().lower() == "development":
            return True
        return False
    if not received:
        return False
    try:
        return hmac.compare_digest(received, expected)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

async def _already_seen(key: str) -> bool:
    """True if this event+entity+status was already PROCESSED (not merely seen).

    Read-only on purpose: the key is written by _mark_seen only once the
    local write has committed, so a handler that dies mid-way leaves the
    event retryable instead of swallowing it.
    """
    try:
        client = await redis_client._get_client()
        return await client.get(key) is not None
    except Exception as e:
        # Redis down — fail OPEN (process the event) but log loudly. The
        # re-fetch pattern keeps us safe against most double-processing;
        # the idempotency value is defence-in-depth, not the only guard.
        logger.warning("inboxkit idempotency check failed (redis down?): %s", e)
        return False


async def _mark_seen(key: str) -> None:
    """Record completion AFTER a durable write. Never raises: losing the
    dedupe value costs a duplicate re-fetch, not a lost event."""
    try:
        client = await redis_client._get_client()
        await client.set(key, "1", ex=_IDEMPOTENCY_TTL_SECONDS)
    except Exception as e:
        logger.warning("inboxkit idempotency mark failed (redis down?): %s", e)


def _idem_key(event: str, entity_uid: str, new_status: str) -> str:
    return f"inboxkit:processed:{event}:{entity_uid}:{new_status}"


# ---------------------------------------------------------------------------
# Freshness check (replay defence — signature is static)
# ---------------------------------------------------------------------------

def _is_fresh(timestamp_str: str) -> bool:
    try:
        ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except Exception:
        return False
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    return abs(age) <= _FRESHNESS_WINDOW_SECONDS


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------

@router.post("")
async def inboxkit_webhook(
    request: Request,
    response: Response,
    x_inboxkit_signature: Optional[str] = Header(default=None, alias="X-InboxKit-Signature"),
    x_inboxkit_event: Optional[str] = Header(default=None, alias="X-InboxKit-Event"),
    x_inboxkit_timestamp: Optional[str] = Header(default=None, alias="X-InboxKit-Timestamp"),
) -> dict:
    """Receive any of the 4 InboxKit webhook events.

    Permanent problems (bad signature, malformed or stale body) are 4xx and
    never retried. Anything that failed while re-fetching or persisting is a
    503: InboxKit retries it, and the dedupe value is only written after commit,
    so the retry runs the whole import again.
    """
    raw = await request.body()

    # 1. Signature verification (static SHA-256 of team API key).
    expected = _expected_signature()
    if not _verify_signature(x_inboxkit_signature, expected):
        logger.warning("inboxkit webhook: signature mismatch (got %r)", x_inboxkit_signature)
        # 401 is permanent (no retry) per InboxKit's contract — correct for bad sig.
        raise HTTPException(status_code=401, detail="invalid signature")

    # 2. Parse envelope.
    try:
        import json
        envelope = _Envelope(**json.loads(raw))
    except Exception as e:
        logger.warning("inboxkit webhook: malformed payload: %s", e)
        # 400 is permanent — don't ask InboxKit to retry a malformed body.
        raise HTTPException(status_code=400, detail="malformed payload")

    # 3. Freshness check (replay defence — signature doesn't cover body).
    ts = envelope.timestamp or x_inboxkit_timestamp or ""
    if ts and not _is_fresh(ts):
        logger.warning("inboxkit webhook: stale event (%s) for %s — rejecting",
                       ts, envelope.event)
        # Treat as permanent — a replay won't become fresh.
        raise HTTPException(status_code=400, detail="stale event")

    event = envelope.event or x_inboxkit_event or ""
    if event not in (
        "domain.status_changed",
        "mailbox.status_changed",
        "consent_request.status_changed",
        "client_id_request.status_changed",
    ):
        logger.info("inboxkit webhook: ignoring unknown event %s", event)
        return {"status": "ignored", "event": event}

    logger.info("inboxkit webhook: %s (team=%s)", event, envelope.team_id)

    # 4. Route to the per-event handler. Each one extracts the entity uid +
    #    new status, dedupes via Redis, then RE-FETCHES authoritative state
    #    via the authenticated REST API before mutating the local Domain /
    #    EmailAccount row.
    try:
        result = await _route_event(event, envelope.data)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("inboxkit webhook handler failed for %s", event)
        raise HTTPException(status_code=503, detail="temporary failure, retry") from e

    response.status_code = 200
    return {"status": "processed", "event": event, "result": result}


# ---------------------------------------------------------------------------
# Per-event handlers
# ---------------------------------------------------------------------------

async def _route_event(event: str, data: dict[str, Any]) -> dict[str, Any]:
    if event == "domain.status_changed":
        return await _on_domain_status_changed(data)
    if event == "mailbox.status_changed":
        return await _on_mailbox_status_changed(data)
    if event == "consent_request.status_changed":
        return await _on_consent_request(data)
    if event == "client_id_request.status_changed":
        return await _on_client_id_request(data)
    return {"status": "ignored"}


def _entity(data: dict[str, Any], name: str) -> Optional[dict[str, Any]]:
    e = data.get(name)
    return e if isinstance(e, dict) else None


async def _on_domain_status_changed(data: dict[str, Any]) -> dict[str, Any]:
    domain = _entity(data, "domain")
    if not domain:
        return {"status": "no_domain_in_payload"}
    uid = domain.get("uid", "")
    new_status = domain.get("status", "")
    if not uid or not new_status:
        return {"status": "missing_uid_or_status"}

    key = _idem_key("domain.status_changed", uid, new_status)
    if await _already_seen(key):
        return {"status": "duplicate", "uid": uid}

    # RE-FETCH authoritative state — never trust the webhook body.
    provider = InboxKitProvider()
    record = await provider.get_domain(uid, strict=True)  # API failure raises -> 503 -> InboxKit retries
    if record is None:
        logger.warning("inboxkit has no domain %s; webhook ignored", uid)
        return {"status": "not_found", "uid": uid}

    # Persist the logical state onto the local Domain row.
    await _persist_domain_state(record)
    await _mark_seen(key)
    return {"status": "updated", "uid": uid, "logical_state": record.status,
            "native_status": record.native_status}


async def _on_mailbox_status_changed(data: dict[str, Any]) -> dict[str, Any]:
    mailbox = _entity(data, "mailbox")
    if not mailbox:
        return {"status": "no_mailbox_in_payload"}
    uid = mailbox.get("uid", "")
    new_status = mailbox.get("status", "")
    if not uid or not new_status:
        return {"status": "missing_uid_or_status"}

    # CRITICAL: discard any credentials in the webhook payload.
    # Only GET /mailboxes/show-credentials is trusted.
    sanitized = {k: v for k, v in mailbox.items()
                 if k not in ("password", "app_password", "secret")}
    if sanitized != mailbox:
        logger.info("inboxkit webhook: discarded plaintext creds from mailbox payload (uid=%s)", uid)

    key = _idem_key("mailbox.status_changed", uid, new_status)
    if await _already_seen(key):
        return {"status": "duplicate", "uid": uid}

    provider = InboxKitProvider()
    record = await provider.get_mailbox(uid, strict=True)
    if record is None:
        logger.warning("inboxkit has no mailbox %s; webhook ignored", uid)
        return {"status": "not_found", "uid": uid}

    logical = to_logical_state(record.native_status)

    # If the mailbox just became Ready (active), pull creds via the
    # authenticated call and write them with the row, in one transaction.
    creds = None
    if logical == LogicalState.READY:
        creds = await provider.get_credentials(uid)  # failure raises -> 503; never imported without them

    await _persist_mailbox(record, creds)
    await _mark_seen(key)
    return {"status": "updated", "uid": uid, "logical_state": record.status,
            "native_status": record.native_status}


async def _on_consent_request(data: dict[str, Any]) -> dict[str, Any]:
    cr = _entity(data, "consent_request")
    if not cr:
        return {"status": "no_consent_request_in_payload"}
    uid = cr.get("uid", "")
    new_status = cr.get("status", "")
    if not uid or not new_status:
        return {"status": "missing_uid_or_status"}
    key = _idem_key("consent_request.status_changed", uid, new_status)
    if await _already_seen(key):
        return {"status": "duplicate", "uid": uid}
    # Consent requests are OAuth onboarding state; we log them for now. The
    # mailbox.status_changed event is what actually drives the local row.
    logger.info("inboxkit consent_request %s -> %s (url=%s)", uid, new_status,
                cr.get("consent_url", ""))
    await _mark_seen(key)
    return {"status": "logged", "uid": uid, "consent_status": new_status}


async def _on_client_id_request(data: dict[str, Any]) -> dict[str, Any]:
    cr = _entity(data, "client_id_request")
    if not cr:
        return {"status": "no_client_id_request_in_payload"}
    uid = cr.get("uid", "")
    new_status = cr.get("status", "")
    if not uid or not new_status:
        return {"status": "missing_uid_or_status"}
    key = _idem_key("client_id_request.status_changed", uid, new_status)
    if await _already_seen(key):
        return {"status": "duplicate", "uid": uid}
    logger.info("inboxkit client_id_request %s -> %s (domain=%s)", uid, new_status,
                cr.get("domain_name", ""))
    await _mark_seen(key)
    return {"status": "logged", "uid": uid, "client_id_status": new_status}


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

async def _persist_domain_state(record) -> None:
    """Update the local Domain row's status from the provider's record.

    Raises on failure: the caller only marks the event processed after this
    returns, so a failed write stays retryable.
    """
    from app.db.postgres import async_session_maker
    from app.models.domain import Domain
    from sqlalchemy import select, update

    async with async_session_maker() as session:
        stmt = select(Domain).where(Domain.inboxkit_domain_uid == record.uid)
        result = await session.execute(stmt)
        d = result.scalar_one_or_none()
        if d is None and record.name:
            # POST /api/v1/domains may not know the uid yet (order response
            # without one): adopt the row by name and backfill it.
            d = (await session.execute(
                select(Domain).where(Domain.domain_name == record.name)
            )).scalar_one_or_none()
        if d is None:
            logger.info("inboxkit: domain %s not in local DB (foreign workspace?) — skipping",
                        record.uid)
            return
        await session.execute(
            update(Domain).where(Domain.id == d.id).values(
                status=record.status,
                inboxkit_native_status=record.native_status,
                inboxkit_domain_uid=record.uid,
            )
        )
        await session.commit()


async def _resolve_domain_id(session, domain_uid, domain_name=None) -> Optional[Any]:
    """Look up the local Domain.id for an InboxKit-native domain uid.

    Returns None if the domain isn't in the local DB yet (foreign
    workspace, or the domain webhook hasn't landed before this mailbox
    one) — the caller leaves domain_id NULL rather than guessing.
    """
    from app.models.domain import Domain
    from sqlalchemy import select

    if domain_uid:
        found = (await session.execute(
            select(Domain.id).where(Domain.inboxkit_domain_uid == domain_uid)
        )).scalar_one_or_none()
        if found is not None:
            return found
    if not domain_name:
        return None
    # Name fallback: the mailbox event can land before the domain uid is known.
    return (await session.execute(
        select(Domain.id).where(Domain.domain_name == domain_name)
    )).scalar_one_or_none()


async def _persist_mailbox(record, creds) -> None:
    """Upsert the local EmailAccount row and its credentials in ONE transaction.

    Mailbox row first, credentials second, single commit: creds must never
    land on a row that was not committed, and any failure propagates so the
    caller leaves the dedupe value unset and the event stays retryable.

    inboxkit_uid is unique (0006). A concurrent first import loses the insert
    inside a savepoint and falls through to the update path, so there is
    exactly one row. A partial provider record never blanks stored values.

    The password is encrypted with app.crypto.encrypt_secret (key from env
    only) into smtp_password_encrypted / imap_password_encrypted — never
    stored in plaintext at rest.
    """
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from app.db.postgres import async_session_maker
    from app.models.domain import Domain
    from app.models.email_account import EmailAccount

    async def existing(session):
        return (await session.execute(
            select(EmailAccount).where(EmailAccount.inboxkit_uid == record.uid)
        )).scalar_one_or_none()

    async with async_session_maker() as session:
        domain_id = await _resolve_domain_id(session, record.domain_uid, record.domain_name)
        acc = await existing(session)
        created = acc is None
        if created:
            if not record.email:
                raise ValueError(f"provider record for mailbox {record.uid} has no email")
            # New mailbox. `name` is NOT NULL and the provider record carries
            # no display name, so the address doubles as one.
            fresh = EmailAccount(
                email=record.email,
                name=record.email,
                inboxkit_uid=record.uid,
                inboxkit_workspace_uid=record.workspace_uid,
                platform=record.platform,
                domain_id=domain_id,
                is_active=(record.status == "ready"),
            )
            if domain_id is not None:
                # A mailbox imported onto a paused/retired domain must not start sending.
                gate = (await session.execute(
                    select(Domain.send_status, Domain.send_status_reason).where(Domain.id == domain_id)
                )).one()
                if gate.send_status != "active":
                    fresh.status, fresh.status_reason = gate.send_status, gate.send_status_reason
            try:
                async with session.begin_nested():
                    session.add(fresh)
                    await session.flush()
                acc = fresh
            except IntegrityError:  # a concurrent import of the same mailbox committed first
                acc, created = await existing(session), False
                if acc is None:
                    raise
        if not created:
            acc.is_active = (record.status == "ready")
            if domain_id is not None:
                acc.domain_id = domain_id

        if creds is not None:
            if creds.password:
                token = encrypt_secret(creds.password)
                acc.smtp_password_encrypted = token
                acc.imap_password_encrypted = token
                acc.credentials_persisted = True
            elif not acc.smtp_password_encrypted:
                raise ValueError(f"provider returned no password for mailbox {record.uid}")
            # Blank fields from a partial provider record keep what is stored.
            if creds.smtp_host:
                acc.smtp_host, acc.smtp_port = creds.smtp_host, creds.smtp_port
            if creds.imap_host:
                acc.imap_host, acc.imap_port = creds.imap_host, creds.imap_port
            if creds.username:
                acc.smtp_username = acc.imap_username = creds.username

        await session.commit()

    if creds is not None:
        logger.info("inboxkit: creds fetched + encrypted for %s", record.email)
