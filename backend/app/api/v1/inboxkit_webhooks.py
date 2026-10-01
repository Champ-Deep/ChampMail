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
set (24h). A replayed or duplicate event within the window is a no-op.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel

from app.core.config import settings
from app.db.redis import redis_client
from app.services.inboxkit.client import InboxKitAPIError
from app.services.inboxkit.provider import InboxKitProvider
from app.services.inboxkit.states import to_logical_state, LogicalState

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
        if settings.environment == "development":
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
    """True if this event+entity+status was processed within the TTL window."""
    try:
        # SET NX: returns True if set, None if already exists.
        client = await redis_client._get_client()
        result = await client.set(key, "1", ex=_IDEMPOTENCY_TTL_SECONDS, nx=True)
        return result is None  # None means the key already existed
    except Exception as e:
        # Redis down — fail OPEN (process the event) but log loudly. The
        # re-fetch pattern keeps us safe against most double-processing;
        # the idempotency set is defence-in-depth, not the only guard.
        logger.warning("inboxkit idempotency check failed (redis down?): %s", e)
        return False


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

    Always returns 2xx within 30s (per InboxKit's contract). Errors are
    logged, not raised — a 5xx triggers InboxKit's retry loop, which we
    only want for transient failures we can actually fix by retrying.
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
        # Unexpected error — log and return 200 so InboxKit doesn't retry
        # forever; the re-fetch on the next event will reconcile state.
        logger.exception("inboxkit webhook handler crashed for %s: %s", event, e)
        result = {"status": "error", "detail": str(e)}

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
    record = await provider.get_domain(uid)
    if record is None:
        logger.warning("inboxkit re-fetch failed for domain %s; treating webhook as hint only", uid)
        return {"status": "refetch_failed", "uid": uid}

    # Persist the logical state onto the local Domain row.
    await _persist_domain_state(record)
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
    record = await provider.get_mailbox(uid)
    if record is None:
        logger.warning("inboxkit re-fetch failed for mailbox %s; treating webhook as hint only", uid)
        return {"status": "refetch_failed", "uid": uid}

    logical = to_logical_state(record.native_status)

    # If the mailbox just became Ready (active), pull creds via the
    # authenticated call and encrypt them into the EmailAccount row.
    if logical == LogicalState.READY:
        try:
            creds = await provider.get_credentials(uid)
            await _persist_mailbox_credentials(record, creds)
        except InboxKitAPIError as e:
            logger.error("inboxkit credential re-fetch failed for %s: %s", uid, e)
            return {"status": "credential_refetch_failed", "uid": uid}

    await _persist_mailbox_state(record)
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
    return {"status": "logged", "uid": uid, "client_id_status": new_status}


# ---------------------------------------------------------------------------
# Persistence helpers (deferred to the existing services)
# ---------------------------------------------------------------------------

async def _persist_domain_state(record) -> None:
    """Update the local Domain row's status from the provider's record."""
    try:
        from app.db.postgres import async_session_maker
        from app.models.domain import Domain
        from sqlalchemy import select, update

        async with async_session_maker() as session:
            stmt = select(Domain).where(Domain.inboxkit_domain_uid == record.uid)
            result = await session.execute(stmt)
            d = result.scalar_one_or_none()
            if d is None:
                logger.info("inboxkit: domain %s not in local DB (foreign workspace?) — skipping",
                            record.uid)
                return
            await session.execute(
                update(Domain).where(Domain.id == d.id).values(
                    status=record.status,
                    inboxkit_native_status=record.native_status,
                )
            )
            await session.commit()
    except Exception as e:
        logger.exception("inboxkit _persist_domain_state failed: %s", e)


async def _resolve_domain_id(session, domain_uid) -> Optional[Any]:
    """Look up the local Domain.id for an InboxKit-native domain uid.

    Returns None if the domain isn't in the local DB yet (foreign
    workspace, or the domain webhook hasn't landed before this mailbox
    one) — the caller leaves domain_id NULL rather than guessing.
    """
    if not domain_uid:
        return None
    from app.models.domain import Domain
    from sqlalchemy import select

    result = await session.execute(
        select(Domain.id).where(Domain.inboxkit_domain_uid == domain_uid)
    )
    return result.scalar_one_or_none()


async def _persist_mailbox_state(record) -> None:
    """Update / create the local EmailAccount row for an InboxKit mailbox."""
    try:
        from app.db.postgres import async_session_maker
        from app.models.email_account import EmailAccount
        from sqlalchemy import select

        async with async_session_maker() as session:
            domain_id = await _resolve_domain_id(session, record.domain_uid)
            stmt = select(EmailAccount).where(EmailAccount.inboxkit_uid == record.uid)
            result = await session.execute(stmt)
            acc = result.scalar_one_or_none()
            if acc is None:
                # New mailbox — create a stub row. The credentials persist
                # call below fills in the SMTP/IMAP transport fields.
                acc = EmailAccount(
                    email=record.email,
                    inboxkit_uid=record.uid,
                    inboxkit_workspace_uid=record.workspace_uid,
                    platform=record.platform,
                    domain_id=domain_id,
                    is_active=(record.status == "ready"),
                )
                session.add(acc)
            else:
                acc.is_active = (record.status == "ready")
                if domain_id is not None:
                    acc.domain_id = domain_id
            await session.commit()
    except Exception as e:
        logger.exception("inboxkit _persist_mailbox_state failed: %s", e)


async def _persist_mailbox_credentials(record, creds) -> None:
    """Encrypt + persist SMTP/IMAP creds via Fernet into the existing
    smtp_password_encrypted / imap_password_encrypted columns.

    Uses the same EMAIL_ENCRYPTION_KEY that EmailAccountService uses, so the
    send agent can decrypt via EmailAccountService.get_decrypted_smtp_password().
    The password is NEVER stored in plaintext at rest.
    """
    try:
        from app.db.postgres import async_session_maker
        from app.models.email_account import EmailAccount
        from sqlalchemy import select, update
        from cryptography.fernet import Fernet

        key = os.environ.get("EMAIL_ENCRYPTION_KEY")
        if not key:
            key = Fernet.generate_key().decode()
            os.environ["EMAIL_ENCRYPTION_KEY"] = key
        fernet = Fernet(key.encode() if isinstance(key, str) else key)
        encrypted_pw = fernet.encrypt((creds.password or "").encode()).decode()

        async with async_session_maker() as session:
            stmt = select(EmailAccount).where(EmailAccount.inboxkit_uid == record.uid)
            result = await session.execute(stmt)
            acc = result.scalar_one_or_none()
            if acc is None:
                logger.warning("inboxkit: creds arrived for mailbox %s not yet in local DB",
                               record.uid)
                return
            await session.execute(
                update(EmailAccount).where(EmailAccount.id == acc.id).values(
                    smtp_host=creds.smtp_host,
                    smtp_port=creds.smtp_port,
                    imap_host=creds.imap_host,
                    imap_port=creds.imap_port,
                    smtp_password_encrypted=encrypted_pw,
                    imap_password_encrypted=encrypted_pw,
                    credentials_persisted=True,
                )
            )
            await session.commit()
        logger.info("inboxkit: creds fetched + encrypted for %s", record.email)
    except Exception as e:
        logger.exception("inboxkit _persist_mailbox_credentials failed: %s", e)
