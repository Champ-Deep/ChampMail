"""
Email settings model for storing user-specific SMTP/IMAP configuration.

Credentials are encrypted at rest using Fernet symmetric encryption.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.postgres import Base


class EmailSettings(Base):
    """User email configuration (SMTP/IMAP) with encrypted credentials."""

    __tablename__ = "email_settings"

    # Primary key is the user_id (one settings record per user)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)

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
    from_email = Column(String(255), nullable=True)
    from_name = Column(String(255), nullable=True)
    reply_to_email = Column(String(255), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="email_settings")
