"""Public open/click routes on the per-domain tracking host: GET /o/<token>.gif and GET /c/<token>.

A token only counts if its HMAC verifies, it names a known send_dispatches row, that row belongs to
the signed domain, and the request's Host is that domain's own tracking_subdomain (no shared host,
no cross-domain use). Anything else is a bare 404 and creates no event. Repeats are absorbed by the
outbox's unique (message_id, event_type), so a valid link always answers, and answers the same.
Mounted at the app root (not /api/v1): the proxy for a tracking host should expose only /o and /c.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_session
from app.models.domain import Domain
from app.models.send_dispatch import SendDispatch
from app.services import tracking
from app.services.outbound_events import emit

router = APIRouter(tags=["Tracking"])
log = logging.getLogger("champmail.tracking")

PIXEL = bytes.fromhex("47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b")  # 1x1 GIF
NO_STORE = {"Cache-Control": "no-store"}


async def _authorize(session: AsyncSession, request: Request, token: Optional[str], kind: str) -> Optional[dict]:
    return await authorize(session, request.headers.get("host", ""), token, kind)


async def authorize(session: AsyncSession, host: str, token: Optional[str], kind: str) -> Optional[dict]:
    """The claim if the token verifies, names a live dispatch of the signed domain, and `host` is that domain's own tracking host."""
    claim = tracking.verify(token, kind) if token else None
    if claim is None:
        return None
    try:
        domain_id = UUID(claim["domain_id"])
    except ValueError:
        return None
    row = (await session.execute(
        select(Domain.tracking_subdomain)
        .join(SendDispatch, SendDispatch.domain_id == Domain.id)
        .where(SendDispatch.message_id == claim["message_id"], SendDispatch.domain_id == domain_id,
               SendDispatch.status != "failed")
    )).first()
    host = host.rsplit(":", 1)[0].strip().lower().rstrip(".")
    if row is None or not host or host != (row[0] or "").strip().lower():
        return None
    return claim


async def _record(session: AsyncSession, event_type: str, message_id: str) -> None:
    try:
        await emit(session, event_type, message_id)
        await session.commit()
    except Exception:  # never break the recipient's page or image over bookkeeping
        log.exception("could not record %s for %s", event_type, message_id)
        await session.rollback()


@router.get("/o/{name}")
async def open_pixel(name: str, request: Request, session: AsyncSession = Depends(get_session)):
    claim = await _authorize(session, request, name[:-4] if name.endswith(".gif") else None, "o")
    if claim is None:
        return Response(status_code=404)
    await _record(session, "opened", claim["message_id"])
    return Response(PIXEL, media_type="image/gif", headers=NO_STORE)


@router.get("/c/{token}")
async def click(token: str, request: Request, session: AsyncSession = Depends(get_session)):
    claim = await _authorize(session, request, token, "c")
    if claim is None:
        return Response(status_code=404)
    await _record(session, "clicked", claim["message_id"])
    return RedirectResponse(claim["url"], status_code=302, headers=NO_STORE)
