"""POST /api/v1/send. Request/response shape is fixed by ChampHarbinger src/lib/email/champmail.ts."""
from __future__ import annotations

import hmac
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.postgres import async_session_maker
from app.db.redis import redis_client
from app.models import Seed
from app.services import send as svc

router = APIRouter()
CANARY_HEADER = "X-Sledgehammer-Canary"
log = logging.getLogger(__name__)


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    s = get_settings()
    if not s.champmail_api_key.strip():
        # Settings already refuses to boot in production without a key; re-check so a
        # mutated env can never leave the endpoint open there.
        if s.champmail_env.strip().lower() in ("production", "prod"):
            raise HTTPException(503, "API key not configured")
        return
    if not hmac.compare_digest((x_api_key or "").encode(), s.champmail_api_key.encode()):
        raise HTTPException(401, "invalid API key")


async def get_session():
    async with async_session_maker() as session:
        yield session


class SendRequest(BaseModel):
    to: str
    subject: str
    html_body: Optional[str] = None
    text_body: Optional[str] = None
    from_name: Optional[str] = None
    from_address: Optional[str] = None  # selects the mailbox with this address
    reply_to: Optional[str] = None
    mailbox_id: Optional[UUID] = None
    brand_id: Optional[str] = None
    domain_id: Optional[UUID] = None
    unsubscribe_url: Optional[str] = None
    track_opens: bool = True
    track_clicks: bool = True
    idempotency_key: Optional[str] = None  # same key as the Idempotency-Key header when both are sent
    # canary: seed-only recovery send, allowed through a policy pause. Only CANARY_HEADER of `headers` is ever forwarded.
    canary: bool = False
    headers: Optional[dict[str, str]] = None

    @field_validator("to", "subject", "from_name", "from_address", "reply_to", "unsubscribe_url")
    @classmethod
    def no_header_injection(cls, v):
        if v is not None and ("\r" in v or "\n" in v):
            raise ValueError("line breaks are not allowed in header fields")
        return v

    @field_validator("headers")
    @classmethod
    def headers_are_single_line(cls, v):
        if v and any("\r" in k + x or "\n" in k + x for k, x in v.items()):
            raise ValueError("line breaks are not allowed in headers")
        return v

    @field_validator("to")
    @classmethod
    def to_is_address(cls, v):
        if "@" not in v or "," in v:
            raise ValueError("to must be one email address")
        return v

    @field_validator("unsubscribe_url")
    @classmethod
    def unsub_is_http(cls, v):
        if v is not None and not v.startswith(("https://", "http://")):
            raise ValueError("unsubscribe_url must be http(s)")
        return v


def _resolve_key(header: Optional[str], body: Optional[str]) -> Optional[str]:
    given = [v for v in (header, body) if v is not None]
    if any(not v.strip() or len(v) > 255 for v in given):
        raise HTTPException(422, "idempotency key must be 1-255 non-blank characters")
    if len(set(given)) > 1:
        raise HTTPException(422, "Idempotency-Key header and idempotency_key field differ")
    return given[0] if given else None


def _err(status: int, code: str, detail: str, retry_after: Optional[int] = None, **extra) -> JSONResponse:
    headers = {"Retry-After": str(retry_after)} if retry_after else None
    return JSONResponse({"detail": detail, "code": code, **extra}, status_code=status, headers=headers)


def _replay(row, payload_hash: str) -> Optional[JSONResponse | dict]:
    """Answer a repeated key from its stored row; None when the row is `failed` and may be retried."""
    if row.payload_hash != payload_hash:
        return _err(409, "idempotency_conflict", "idempotency key was used with a different request")
    if row.status == "sent":
        return row.response
    if row.status == "failed":
        return None
    if row.status == "unknown":
        return _err(503, "smtp_outcome_unknown", "SMTP outcome unknown; not retransmitted until an operator reconciles it",
                    300, message_id=row.message_id)
    return _err(503, "dispatch_in_progress", "an earlier request with this key is still being sent",
                30, message_id=row.message_id)


@router.post("/send", dependencies=[Depends(require_api_key)])
async def send(
    req: SendRequest,
    session: AsyncSession = Depends(get_session),
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    if not (req.html_body or req.text_body):
        raise HTTPException(422, "html_body or text_body is required")
    key = _resolve_key(idempotency_key_header, req.idempotency_key)
    to, extra_headers = req.to, None
    if req.canary:  # security gate: a canary reaches a registered seed or nobody
        to = req.to.strip().lower()
        if (await session.execute(select(Seed.id).where(Seed.address == to))).first() is None:
            raise HTTPException(422, "canary recipient is not a registered seed")
        given = {k.lower(): v for k, v in (req.headers or {}).items()}.get(CANARY_HEADER.lower())
        extra_headers = {CANARY_HEADER: given} if given is not None else None
    try:  # Redis down = sending paused (spec 3.12): refuse before any claim or SMTP
        await redis_client.ping()
    except Exception:
        log.exception("redis unreachable, send refused")
        return _err(503, "redis_unavailable", "sending is paused: Redis is unreachable", 30)
    payload_hash = svc.payload_fingerprint(req.model_dump(mode="json", exclude={"idempotency_key"}))

    retry_id = None
    if key and (row := await svc.find_dispatch(session, key)):
        if (answer := _replay(row, payload_hash)) is not None:
            return answer
        retry_id = row.id  # earlier attempt provably never reached SMTP: safe to try again
    try:
        claimed = await svc.claim_mailbox(
            session,
            mailbox_id=req.mailbox_id,
            email=req.from_address,
            brand_id=req.brand_id,
            domain_id=req.domain_id,
            idempotency_key=key,
            payload_hash=payload_hash,
            retry_dispatch_id=retry_id,
            canary=req.canary,
        )
    except svc.DuplicateKey:  # a concurrent request with this key won
        row = await svc.find_dispatch(session, key) if key else None
        return (_replay(row, payload_hash) if row else None) or _err(
            503, "dispatch_in_progress", "an earlier request with this key is still being sent", 30)
    except svc.SendRefused as e:
        # A named mailbox queued behind the winner sees "throttled"; the key's row is the truthful answer.
        if key and (row := await svc.find_dispatch(session, key)) and (answer := _replay(row, payload_hash)) is not None:
            return answer
        return _err(e.status, e.code, e.detail, e.retry_after)

    release = {"release_canary_domain": claimed.domain.id} if req.canary else {"release_mailbox": claimed.mailbox.id}
    try:
        msg, message_id = svc.build_message(
            claimed,
            to=to,
            subject=req.subject,
            html_body=req.html_body,
            text_body=req.text_body,
            from_name=req.from_name,
            reply_to=req.reply_to,
            unsubscribe_url=req.unsubscribe_url,
            track_opens=req.track_opens,
            track_clicks=req.track_clicks,
            extra_headers=extra_headers,
        )
    except Exception as e:  # nothing was submitted: give the slot back and mark the row retryable
        await svc.finish_dispatch(session, claimed.dispatch_id, "failed", **release)
        if isinstance(e, svc.SendRefused):
            return _err(e.status, e.code, e.detail, e.retry_after)
        raise
    try:
        await svc.submit_smtp(claimed.mailbox, msg)
    except Exception as e:
        if svc.is_definite_refusal(e):  # provably not accepted: slot goes back, same key may retry
            await svc.finish_dispatch(session, claimed.dispatch_id, "failed", **release)
            raise HTTPException(502, f"SMTP submission failed: {type(e).__name__}") from e
        # Timeout/disconnect/unknown: the server may already hold the message. Keep the slot, never retransmit.
        await svc.finish_dispatch(session, claimed.dispatch_id, "unknown")
        log.error("smtp outcome unknown for message %s (%s)", message_id, type(e).__name__)
        return _err(503, "smtp_outcome_unknown", "SMTP outcome unknown; not retransmitted until an operator reconciles it",
                    300, message_id=message_id)
    body = {
        "message_id": message_id,
        "status": "sent",
        "domain_id": str(claimed.domain.id),
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await svc.finish_dispatch(session, claimed.dispatch_id, "sent", response=body)
    except Exception:  # mail is out; the row stays `sending` so a retry is held, not re-sent
        log.exception("sent but could not record dispatch %s", message_id)
    return body
