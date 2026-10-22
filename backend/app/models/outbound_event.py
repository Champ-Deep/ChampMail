"""Durable outbound-event outbox. One row per (message_id, event_type), ever.

status: pending (waiting for next_attempt_at), leased (a worker claimed it; lease_expires_at bounds
how long a crashed worker can hold it), delivered (receiver answered 2xx), dead (permanent receiver
rejection or attempts exhausted; kept for manual replay, see docs/outbound-events.md).
"""
from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.postgres import Base

EVENT_TYPES = ("delivered", "opened", "clicked", "replied", "bounced", "complained", "unsubscribed")
STATUSES = ("pending", "leased", "delivered", "dead")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


class OutboundEvent(Base):
    __tablename__ = "outbound_events"
    __table_args__ = (
        UniqueConstraint("message_id", "event_type", name="uq_outbound_events_message_event"),
        CheckConstraint(_in("event_type", EVENT_TYPES), name="ck_outbound_events_event_type"),
        CheckConstraint(_in("status", STATUSES), name="ck_outbound_events_status"),
        Index("ix_outbound_events_status_next", "status", "next_attempt_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(String(998), ForeignKey("send_dispatches.message_id"), nullable=False)
    event_type = Column(String(32), nullable=False)
    event_at = Column(DateTime, nullable=False)  # when it happened (naive UTC), sent as `timestamp`
    status = Column(String(16), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)  # bumped at claim, so a crash still counts
    next_attempt_at = Column(DateTime, nullable=False)
    lease_expires_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
