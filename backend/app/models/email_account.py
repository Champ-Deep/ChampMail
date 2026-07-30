"""
Email account model for storing multiple user email accounts.

Each user can have multiple email accounts configured with their own SMTP/IMAP credentials.
Credentials are encrypted at rest using Fernet symmetric encryption.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.postgres import Base


class EmailAccount(Base):
    """User email account with SMTP/IMAP configuration and encrypted credentials."""

    __tablename__ = "email_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # Account identification
    name = Column(String(255), nullable=False)  # Display name for the account (e.g., "Work Gmail")
    email = Column(String(255), nullable=False)  # The email address
    is_default = Column(Boolean, default=False)  # Whether this is the default sending account
    is_active = Column(Boolean, default=True)  # Whether this account is enabled

    # SMTP Configuration (Outbound)
    smtp_host = Column(String(255), nullable=True)
    smtp_port = Column(Integer, default=587)
    smtp_username = Column(String(255), nullable=True)
    smtp_password_encrypted = Column(Text, nullable=True)  # Fernet encrypted
    smtp_use_tls = Column(Boolean, default=True)
    smtp_verified = Column(Boolean, default=False)
    smtp_verified_at = Column(DateTime, nullable=True)

    # IMAP Configuration (Inbound/Reply Detection)
    imap_host = Column(String(255), nullable=True)
    imap_port = Column(Integer, default=993)
    imap_username = Column(String(255), nullable=True)
    imap_password_encrypted = Column(Text, nullable=True)  # Fernet encrypted
    imap_use_ssl = Column(Boolean, default=True)
    imap_mailbox = Column(String(255), default="INBOX")
    imap_verified = Column(Boolean, default=False)
    imap_verified_at = Column(DateTime, nullable=True)

    # Sending Identity
    from_name = Column(String(255), nullable=True)
    reply_to_email = Column(String(255), nullable=True)

    # * InboxKit IAL linkage (ChampMail Build Spec §1). inboxkit_uid is the
    # * provider-native mailbox handle; credentials_persisted is set True
    # * once the authenticated GET /mailboxes/show-credentials call has
    # * succeeded and the (encrypted) creds are on this row — never trust
    # * creds arriving in the webhook payload itself.
    inboxkit_uid = Column(String(255), nullable=True, index=True)
    inboxkit_workspace_uid = Column(String(255), nullable=True)
    platform = Column(String(32), nullable=True)  # google | microsoft | azure | smtp
    credentials_persisted = Column(Boolean, default=False)

    # * Owning domain (the mailbox lives on this domain). Needed to scope
    # * "give me a ready mailbox on domain X" queries — without it, a
    # * multi-domain InboxKit setup can't tell mailboxes on different
    # * domains apart. NULL for legacy rows created before this column
    # * existed; backfilled by the InboxKit webhook handler going forward.
    domain_id = Column(UUID(as_uuid=True), ForeignKey("domains.id"), nullable=True, index=True)

    # * Per-mailbox send accounting (migration 015). Deliverability is governed
    # * per mailbox, not per domain — InboxKit puts N mailboxes on one domain,
    # * so the domain-level cap both under-used paid capacity and let one
    # * mailbox absorb all of it. 25/day is the safe cold-outreach ceiling.
    # * `sent_today_date` makes the daily reset self-healing: a date that isn't
    # * today means "treat sent_today as 0", so a missed beat schedule cannot
    # * silently freeze a mailbox at its cap.
    daily_send_limit = Column(Integer, nullable=False, default=25)
    sent_today = Column(Integer, nullable=False, default=0)
    sent_today_date = Column(Date, nullable=True)
    last_send_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="email_accounts")
