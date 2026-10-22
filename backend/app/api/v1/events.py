"""POST /api/v1/events: trusted input for feedback ChampMail cannot observe itself.

For the real delivered / replied / complained / unsubscribed signals that provider or mail-client
adapters forward. ChampMail does not detect replies or complaints: nothing here fabricates them, an
upstream adapter must call this with the real signal. Bounces arrive over IMAP and opens/clicks over
the signed tracking routes, so those three types are refused here. API-key authenticated.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_session, require_api_key
from app.models.send_dispatch import SendDispatch
from app.services.outbound_events import UnknownDispatch, _now, emit, to_naive_utc

router = APIRouter(prefix="/events", tags=["Events"], dependencies=[Depends(require_api_key)])

MAX_FUTURE = timedelta(minutes=5)  # clock skew allowance
SKEW_BEFORE_SEND = timedelta(minutes=1)


class EventIn(BaseModel):
    event_type: Literal["delivered", "replied", "complained", "unsubscribed"]
    message_id: str = Field(min_length=1, max_length=998)
    timestamp: Optional[datetime] = None  # naive means UTC; omitted means now

    @field_validator("message_id")
    @classmethod
    def bare_id(cls, v):
        return v.strip().strip("<>")  # accept the header form too; stored ids have no angle brackets


@router.post("")
async def post_event(body: EventIn, session: AsyncSession = Depends(get_session)) -> dict:
    row = (await session.execute(
        select(SendDispatch.created_at).where(SendDispatch.message_id == body.message_id, SendDispatch.status != "failed")
    )).first()
    if row is None:
        raise HTTPException(404, "unknown message_id")
    ts = to_naive_utc(body.timestamp) if body.timestamp else None
    if ts and (ts > _now() + MAX_FUTURE or ts < row[0] - SKEW_BEFORE_SEND):
        raise HTTPException(422, "timestamp is in the future or before the message was sent")
    try:
        queued = await emit(session, body.event_type, body.message_id, ts)
    except UnknownDispatch:  # lost a race with nothing: dispatches are never deleted, but stay honest
        raise HTTPException(404, "unknown message_id")
    await session.commit()
    return {"status": "queued" if queued else "duplicate", "event_type": body.event_type, "message_id": body.message_id}
