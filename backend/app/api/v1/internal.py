"""POST /api/v1/events/internal: the edge Worker's callback for opened, clicked and unsubscribed.

Auth is the shared INTERNAL_EVENTS_SECRET (X-Edge-Secret), not the API key: the Worker is the only caller
and must not hold anything that can send mail. The Worker has already verified the token's HMAC; it is
verified again here with the same dispatch and host checks the in-process /o and /c routes make, so a
leaked edge secret still cannot record an event for a message the token does not name.
"""
from __future__ import annotations

import hmac
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_session
from app.api.v1.tracking import authorize
from app.config import get_settings
from app.services import tracking
from app.services.outbound_events import emit

KIND = {"opened": "o", "clicked": "c", "unsubscribed": "u"}


def require_edge_secret(x_edge_secret: Optional[str] = Header(default=None, alias="X-Edge-Secret")) -> None:
    want = get_settings().internal_events_secret.strip()
    if not want or not x_edge_secret or not hmac.compare_digest(x_edge_secret, want):
        raise HTTPException(401, "invalid edge secret")


router = APIRouter(prefix="/events/internal", tags=["Edge"], dependencies=[Depends(require_edge_secret)])


class EdgeEvent(BaseModel):
    event_type: Literal["opened", "clicked", "unsubscribed"]
    token: str = Field(min_length=1, max_length=4096)
    host: str = Field(min_length=1, max_length=255)  # the tracking host the recipient hit
    message_id: Optional[str] = Field(default=None, max_length=998)  # cross-check only; the token is the truth


@router.post("")
async def edge_event(body: EdgeEvent, session: AsyncSession = Depends(get_session)) -> dict:
    if tracking.verify(body.token, KIND[body.event_type]) is None:
        raise HTTPException(400, "bad token")
    claim = await authorize(session, body.host, body.token, KIND[body.event_type])
    if claim is None:
        raise HTTPException(404, "unknown message or host")
    if body.message_id is not None and body.message_id.strip().strip("<>") != claim["message_id"]:
        raise HTTPException(422, "message_id does not match the token")
    queued = await emit(session, body.event_type, claim["message_id"])
    await session.commit()
    return {"status": "queued" if queued else "duplicate", "event_type": body.event_type, "message_id": claim["message_id"]}
