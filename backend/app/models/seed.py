"""Seed addresses: the only recipients a `canary: true` send may reach (even on a paused domain)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.postgres import Base


class Seed(Base):
    __tablename__ = "seeds"
    __table_args__ = (CheckConstraint("provider IN ('gmail', 'outlook')", name="ck_seeds_provider"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    address = Column(String(320), nullable=False, unique=True)  # stored lowercase
    provider = Column(String(16), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
