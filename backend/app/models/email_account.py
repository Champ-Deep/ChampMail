"""
Email account model for storing multiple user email accounts.

Each user can have multiple email accounts configured with their own SMTP/IMAP credentials.
Credentials are encrypted at rest using Fernet symmetric encryption.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
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

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="email_accounts")
