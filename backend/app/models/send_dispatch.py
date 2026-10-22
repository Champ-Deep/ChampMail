"""One row per accepted send attempt: message identity, owning mailbox/domain, and outcome.

Written in the same transaction as the mailbox claim, before SMTP, so a crash never leaves a
message without a record. `status`: sending (claim committed, SMTP not resolved), sent,
failed (definite pre-submit refusal, safe to retry), unknown (SMTP outcome ambiguous, never
auto-retried). Holds no SMTP secrets and no message content.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.postgres import Base


class SendDispatch(Base):
    __tablename__ = "send_dispatches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(String(998), nullable=False, unique=True)
    domain_id = Column(UUID(as_uuid=True), ForeignKey("domains.id"), nullable=False)
    mailbox_id = Column(UUID(as_uuid=True), ForeignKey("email_accounts.id"), nullable=False, index=True)
    idempotency_key = Column(String(255), nullable=True, unique=True)  # NULL = keyless (Harbinger)
    payload_hash = Column(String(64), nullable=False)  # conflict detection only, never a dedupe key
    status = Column(String(16), nullable=False, default="sending")
    response = Column(JSON, nullable=True)  # the 200 body, set when status == sent
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
