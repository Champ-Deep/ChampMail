"""
Suppression list model (SUGGESTIONS 4.6).

Every send path checks this before dispatch: bounced, unsubscribed, or manually
suppressed addresses must never be emailed again. Written by the suppressions
route on email.bounced / email.unsubscribed events.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Column, DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.postgres import Base


class Suppression(Base):
    __tablename__ = "suppressions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), nullable=False, index=True)  # * stored lowercased
    team_id = Column(UUID(as_uuid=True), nullable=True)      # * NULL = global
    reason = Column(String(50), nullable=False)              # * bounce | unsubscribe | manual
    source = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("email", "team_id", name="uq_suppressions_email_team"),
    )
