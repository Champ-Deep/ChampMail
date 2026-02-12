"""
Domain model for sending domains with DNS verification.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.postgres import Base


class Domain(Base):
    """Sending domain model with DNS verification status."""

    __tablename__ = "domains"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    domain_name = Column(String(255), unique=True, nullable=False, index=True)
    status = Column(String(50), default="pending")  # pending, verifying, verified, failed

    # DNS verification status
    mx_verified = Column(Boolean, default=False)
    spf_verified = Column(Boolean, default=False)
    dkim_verified = Column(Boolean, default=False)
    dmarc_verified = Column(Boolean, default=False)

    # DKIM keys
    dkim_selector = Column(String(100), default="champmail")
    dkim_private_key = Column(Text, nullable=True)
    dkim_public_key = Column(Text, nullable=True)

    # Sending configuration
    daily_send_limit = Column(Integer, default=50)
    sent_today = Column(Integer, default=0)
    warmup_enabled = Column(Boolean, default=True)
    warmup_day = Column(Integer, default=0)

    # External integrations
    namecheap_domain_id = Column(String(255), nullable=True)
    cloudflare_zone_id = Column(String(255), nullable=True)

    # Deliverability
    health_score = Column(Float, default=100.0)
    bounce_rate = Column(Float, default=0.0)
    last_health_check = Column(DateTime, nullable=True)

    # Team association
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    team = relationship("Team", back_populates="domains")
    send_logs = relationship("SendLog", back_populates="domain")
    daily_stats = relationship("DailyStats", back_populates="domain")


class DNSCheckLog(Base):
    """Log of DNS verification checks for domains."""

    __tablename__ = "dns_check_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    domain_id = Column(UUID(as_uuid=True), ForeignKey("domains.id"), nullable=False)

    mx_valid = Column(Boolean, default=False)
    spf_valid = Column(Boolean, default=False)
    dkim_valid = Column(Boolean, default=False)
    dmarc_valid = Column(Boolean, default=False)

    checked_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    domain = relationship("Domain")
