"""
Suppression list — stores emails that must never be sent to again.

Reasons: hard bounce, spam complaint, manual unsubscribe.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Column, DateTime, String, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import Base

logger = logging.getLogger(__name__)


class SuppressionEntry(Base):
    __tablename__ = "suppression_list"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    reason = Column(String(100), nullable=False)  # bounce, complaint, unsubscribe
    added_at = Column(DateTime, default=datetime.utcnow)


class SuppressionService:
    async def is_suppressed(self, session: AsyncSession, email: str) -> bool:
        result = await session.execute(
            select(SuppressionEntry).where(
                SuppressionEntry.email == email.lower().strip()
            )
        )
        return result.scalar_one_or_none() is not None

    async def add(self, session: AsyncSession, email: str, reason: str) -> bool:
        email = email.lower().strip()
        if await self.is_suppressed(session, email):
            return False
        session.add(SuppressionEntry(id=uuid4(), email=email, reason=reason))
        await session.commit()
        logger.info("Suppressed %s (%s)", email, reason)
        return True


suppression_service = SuppressionService()
