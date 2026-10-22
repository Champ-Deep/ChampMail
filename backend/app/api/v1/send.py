"""POST /api/v1/send. Request/response shape is fixed by ChampHarbinger src/lib/email/champmail.ts."""
from __future__ import annotations

import hmac
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.postgres import async_session_maker
from app.services import send as svc

router = APIRouter()


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

    @field_validator("to", "subject", "from_name", "from_address", "reply_to", "unsubscribe_url")
    @classmethod
    def no_header_injection(cls, v):
        if v is not None and ("\r" in v or "\n" in v):
            raise ValueError("line breaks are not allowed in header fields")
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


@router.post("/send", dependencies=[Depends(require_api_key)])
async def send(req: SendRequest, session: AsyncSession = Depends(get_session)):
    if not (req.html_body or req.text_body):
        raise HTTPException(422, "html_body or text_body is required")
    try:
        claimed = await svc.claim_mailbox(
            session,
            mailbox_id=req.mailbox_id,
            email=req.from_address,
            brand_id=req.brand_id,
            domain_id=req.domain_id,
        )
        msg, message_id = svc.build_message(
            claimed,
            to=req.to,
            subject=req.subject,
            html_body=req.html_body,
            text_body=req.text_body,
            from_name=req.from_name,
            reply_to=req.reply_to,
            unsubscribe_url=req.unsubscribe_url,
            track_opens=req.track_opens,
            track_clicks=req.track_clicks,
        )
    except svc.SendRefused as e:
        headers = {"Retry-After": str(e.retry_after)} if e.retry_after else None
        return JSONResponse({"detail": e.detail, "code": e.code}, status_code=e.status, headers=headers)
    try:
        await svc.submit_smtp(claimed.mailbox, msg)
    except Exception as e:  # any SMTP/network/decrypt failure: slot goes back, caller retries
        await svc.release_claim(session, claimed.mailbox.id)
        raise HTTPException(502, f"SMTP submission failed: {type(e).__name__}") from e
    return {
        "message_id": message_id,
        "status": "sent",
        "domain_id": str(claimed.domain.id),
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
