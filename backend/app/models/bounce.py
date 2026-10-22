"""Parsed DSN bounces. Hard (5.x.x) and soft (4.x.x) are both kept; only hard ones are emitted."""
from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.postgres import Base


class Bounce(Base):
    __tablename__ = "bounces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_account_id = Column(UUID(as_uuid=True), ForeignKey("email_accounts.id"), nullable=False, index=True)
    # sha256 of the raw DSN: a re-polled DSN hits the unique constraint instead of storing twice.
    dsn_hash = Column(String(64), nullable=False, unique=True)
    # Message-ID of the original outbound mail quoted inside the DSN; NULL if the DSN omitted it.
    message_id = Column(String(998), nullable=True, index=True)
    recipient = Column(String(255), nullable=True)
    status_code = Column(String(16), nullable=False)  # e.g. 5.1.1
    kind = Column(String(8), nullable=False)  # hard | soft
    diagnostic = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
