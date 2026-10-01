"""
Suppression list API (SUGGESTIONS 4.6).

POST upserts an address (called by the event path on email.bounced /
email.unsubscribed, or manually). GET checks an address. Both behind
require_auth — same token the send routes use.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenData, require_auth
from app.db.postgres import get_db_session
from app.models.suppression import Suppression

router = APIRouter()


class SuppressionAddRequest(BaseModel):
    email: EmailStr
    reason: str = "manual"  # bounce | unsubscribe | manual
    source: str | None = None


@router.post("/suppressions", status_code=201)
async def add_suppression(
    request: SuppressionAddRequest,
    current_user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    email = str(request.email).lower()
    existing = (
        await session.execute(
            select(Suppression).where(
                Suppression.email == email,
                Suppression.team_id.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing:
        return {"ok": True, "email": email, "already_suppressed": True}

    session.add(
        Suppression(email=email, reason=request.reason, source=request.source)
    )
    await session.commit()
    return {"ok": True, "email": email, "already_suppressed": False}


@router.get("/suppressions/check")
async def check_suppression(
    email: str,
    current_user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    row = (
        await session.execute(
            select(Suppression).where(Suppression.email == email.lower()).limit(1)
        )
    ).scalar_one_or_none()
    return {"email": email.lower(), "suppressed": row is not None,
            "reason": row.reason if row else None}
