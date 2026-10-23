"""Seed registry. Canary sends (POST /send with canary: true) may only go to addresses listed here."""
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_session, require_api_key
from app.models.seed import Seed

router = APIRouter(prefix="/seeds", tags=["Seeds"], dependencies=[Depends(require_api_key)])

# One bare address: no display name, comma, angle brackets, quotes or whitespace (so no header tricks).
_ADDRESS = re.compile(r"^[^@\s,<>\";]+@[^@\s,<>\";]+\.[^@\s,<>\";]+$")


class SeedCreate(BaseModel):
    address: str
    provider: Literal["gmail", "outlook"]

    @field_validator("address")
    @classmethod
    def _address(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) > 320 or not _ADDRESS.match(v):
            raise ValueError("address must be one bare email address")
        return v


def serialize_seed(s: Seed) -> dict:
    return {"id": str(s.id), "address": s.address, "provider": s.provider, "created_at": s.created_at.isoformat()}


@router.post("", status_code=201)
async def create_seed(body: SeedCreate, session: AsyncSession = Depends(get_session)) -> dict:
    seed = Seed(address=body.address, provider=body.provider)
    session.add(seed)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "seed already registered") from None
    return serialize_seed(seed)


@router.get("")
async def list_seeds(session: AsyncSession = Depends(get_session)) -> list[dict]:
    return [serialize_seed(s) for s in (await session.execute(select(Seed).order_by(Seed.address))).scalars()]
