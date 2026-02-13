"""
Send log and analytics models for tracking email deliveries.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.postgres import Base


class SendLog(Base):
    """Individual email send record for tracking and analytics."""

    __tablename__ = "send_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    domain_id = Column(UUID(as_uuid=True), ForeignKey("domains.id"), nullable=True)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=True)
    prospect_id = Column(UUID(as_uuid=True), ForeignKey("prospects.id"), nullable=True)
    sequence_enrollment_id = Column(UUID(as_uuid=True), ForeignKey("sequence_enrollments.id"), nullable=True)

    # Email details
    message_id = Column(String(255), unique=True, nullable=False, index=True)
    recipient_email = Column(String(255), nullable=False, index=True)
    from_address = Column(String(255), nullable=True)
    subject = Column(Text, nullable=True)

    # Status
    status = Column(String(50), default="pending")  # pending, sent, delivered, opened, clicked, bounced, failed

    # Tracking
    opened_at = Column(DateTime, nullable=True)
    first_open_at = Column(DateTime, nullable=True)
    open_count = Column(Integer, default=0)

    clicked_at = Column(DateTime, nullable=True)
    first_click_at = Column(DateTime, nullable=True)
    click_count = Column(Integer, default=0)
    clicked_urls = Column(JSON, nullable=True)

    # Bounce handling
    bounced_at = Column(DateTime, nullable=True)
    bounce_type = Column(String(50), nullable=True)
    bounce_reason = Column(Text, nullable=True)
    smtp_response = Column(Text, nullable=True)

    # Reply tracking
    replied_at = Column(DateTime, nullable=True)
    reply_text = Column(Text, nullable=True)

    # Timing
    sent_at = Column(DateTime, default=datetime.utcnow)
    delivered_at = Column(DateTime, nullable=True)

    # Team association
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)

    # Relationships
    domain = relationship("Domain", back_populates="send_logs")


class DailyStats(Base):
    """Daily aggregated statistics for domains and campaigns."""

    __tablename__ = "daily_stats"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    domain_id = Column(UUID(as_uuid=True), ForeignKey("domains.id"), nullable=True)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=True)

    date = Column(DateTime, nullable=False, index=True)

    # Volume
    total_sent = Column(Integer, default=0)
    total_delivered = Column(Integer, default=0)
    total_failed = Column(Integer, default=0)

    # Engagement
    total_opened = Column(Integer, default=0)
    unique_opened = Column(Integer, default=0)
    total_clicked = Column(Integer, default=0)
    unique_clicked = Column(Integer, default=0)

    # Outcomes
    total_replied = Column(Integer, default=0)
    total_bounced = Column(Integer, default=0)
    total_unsubscribed = Column(Integer, default=0)

    # Rates
    open_rate = Column(Float, default=0.0)
    click_rate = Column(Float, default=0.0)
    bounce_rate = Column(Float, default=0.0)
    reply_rate = Column(Float, default=0.0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    domain = relationship("Domain", back_populates="daily_stats")


class BounceLog(Base):
    """Bounce records for tracking delivery failures."""

    __tablename__ = "bounce_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    send_log_id = Column(UUID(as_uuid=True), ForeignKey("send_logs.id"), nullable=True)
    prospect_id = Column(UUID(as_uuid=True), ForeignKey("prospects.id"), nullable=True)

    email = Column(String(255), nullable=False, index=True)
    bounce_type = Column(String(50), nullable=False)  # hard, soft, transient
    bounce_category = Column(String(100), nullable=True)  # mailbox_full, unknown_user, etc.

    smtp_error_code = Column(String(20), nullable=True)
    smtp_response = Column(Text, nullable=True)

    processed = Column(Boolean, default=False)
    prospect_marked_bounced = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    send_log = relationship("SendLog")


class APIKey(Base):
    """API keys for external integrations."""

    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    key_hash = Column(String(255), unique=True, nullable=False)
    name = Column(String(100), nullable=False)

    permissions = Column(JSON, default=list)

    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    team = relationship("Team")
