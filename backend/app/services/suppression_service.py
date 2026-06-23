"""Suppression service — the gate every send must pass through.

`is_suppressed` is checked in the send path before dispatch; `add` is called from
the unsubscribe handler, the bounce processor, and complaint webhooks so an
opt-out anywhere suppresses everywhere for that team. Addresses are normalized
(lowercased, trimmed) so matching is case-insensitive.
"""
from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.suppression import Suppression

logger = logging.getLogger(__name__)


def _norm(email: str) -> str:
    return (email or "").strip().lower()


class SuppressionService:
    async def is_suppressed(self, session: AsyncSession, team_id, email: str) -> bool:
        email = _norm(email)
        if not email:
            return True  # never send to an empty address
        stmt = select(Suppression.id).where(Suppression.email == email)
        if team_id is not None:
            stmt = stmt.where(Suppression.team_id == team_id)
        result = await session.execute(stmt.limit(1))
        return result.first() is not None

    async def filter_sendable(
        self, session: AsyncSession, team_id, emails: Iterable[str]
    ) -> set[str]:
        """Return the subset of `emails` that are NOT suppressed (normalized)."""
        norm = {_norm(e) for e in emails if _norm(e)}
        if not norm:
            return set()
        stmt = select(Suppression.email).where(Suppression.email.in_(norm))
        if team_id is not None:
            stmt = stmt.where(Suppression.team_id == team_id)
        rows = await session.execute(stmt)
        suppressed = {r[0] for r in rows.all()}
        return norm - suppressed

    async def add(
        self,
        session: AsyncSession,
        team_id,
        email: str,
        reason: str = "manual",
        source: str | None = None,
        note: str | None = None,
    ) -> bool:
        """Idempotently suppress an address. Returns True if newly added."""
        email = _norm(email)
        if not email:
            return False
        stmt = (
            pg_insert(Suppression)
            .values(team_id=team_id, email=email, reason=reason, source=source, note=note)
            .on_conflict_do_nothing(index_elements=["team_id", "email"])
            .returning(Suppression.id)
        )
        result = await session.execute(stmt)
        await session.commit()
        added = result.first() is not None
        if added:
            logger.info("suppressed %s (team=%s reason=%s)", email, team_id, reason)
        return added

    async def remove(self, session: AsyncSession, team_id, email: str) -> None:
        """Re-permit an address (e.g. a re-confirmed opt-in)."""
        from sqlalchemy import delete

        email = _norm(email)
        stmt = delete(Suppression).where(Suppression.email == email)
        if team_id is not None:
            stmt = stmt.where(Suppression.team_id == team_id)
        await session.execute(stmt)
        await session.commit()


suppression_service = SuppressionService()
