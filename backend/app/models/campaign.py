"""
Campaign model for email outreach campaigns.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, Float, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.postgres import Base


class Campaign(Base):
    """Email campaign model for managing outreach efforts."""

    __tablename__ = "campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Status
    status = Column(String(50), default="draft")  # draft, active, paused, completed

    # Configuration
    from_name = Column(String(255), nullable=True)
    from_address = Column(String(255), nullable=True)
    reply_to = Column(String(255), nullable=True)

    # Template
    subject_template = Column(Text, nullable=True)
    html_template = Column(Text, nullable=True)
    plain_text_template = Column(Text, nullable=True)

    # AI personalization
    use_ai_personalization = Column(Boolean, default=False)
    ai_prompt = Column(Text, nullable=True)

    # Targeting
    prospect_list_id = Column(UUID(as_uuid=True), nullable=True)
    target_company_size = Column(JSON, nullable=True)
    target_industries = Column(JSON, nullable=True)

    # Domain rotation
    domain_ids = Column(JSON, default=list)

    # Scheduling
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    timezone = Column(String(50), default="UTC")

    # Limits
    daily_limit = Column(Integer, default=100)
    total_limit = Column(Integer, nullable=True)

    # Statistics (updated periodically)
    total_prospects = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    opened_count = Column(Integer, default=0)
    clicked_count = Column(Integer, default=0)
    bounced_count = Column(Integer, default=0)
    replied_count = Column(Integer, default=0)
    unsubscribed_count = Column(Integer, default=0)

    # Team association
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    activated_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    team = relationship("Team", back_populates="campaigns")
    sequence = relationship("Sequence", back_populates="campaign", uselist=False)
    prospect_enrollments = relationship("CampaignProspect", back_populates="campaign")
    utm_config = relationship("CampaignUTMConfig", back_populates="campaign", uselist=False, lazy="selectin")


class CampaignProspect(Base):
    """Junction table for campaign-prospect enrollment."""

    __tablename__ = "campaign_prospects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False)
    prospect_id = Column(UUID(as_uuid=True), ForeignKey("prospects.id"), nullable=False)

    status = Column(String(50), default="enrolled")  # enrolled, active, completed, paused, bounced, unsubscribed
    current_step = Column(Integer, default=0)

    # Metrics
    email_sent = Column(Boolean, default=False)
    opened = Column(Boolean, default=False)
    clicked = Column(Boolean, default=False)
    replied = Column(Boolean, default=False)
    bounced = Column(Boolean, default=False)
    unsubscribed = Column(Boolean, default=False)

    # Message tracking
    last_message_id = Column(String(255), nullable=True)
    last_sent_at = Column(DateTime, nullable=True)
    next_step_at = Column(DateTime, nullable=True)

    # Timestamps
    enrolled_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    campaign = relationship("Campaign", back_populates="prospect_enrollments")
    prospect = relationship("Prospect", back_populates="campaign_enrollments")


class Prospect(Base):
    """Prospect model for email recipients."""

    __tablename__ = "prospects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=True)

    # Company information
    company_name = Column(String(255), nullable=True)
    company_domain = Column(String(255), nullable=True)
    company_size = Column(String(50), nullable=True)
    industry = Column(String(100), nullable=True)
    job_title = Column(String(255), nullable=True)

    # Personalization
    linkedin_url = Column(String(500), nullable=True)
    twitter_handle = Column(String(100), nullable=True)
    bio = Column(Text, nullable=True)
    interests = Column(JSON, nullable=True)

    # AI-generated content
    personalized_subject = Column(Text, nullable=True)
    personalized_body = Column(Text, nullable=True)

    # Status
    status = Column(String(50), default="active")  # active, bounced, unsubscribed, do_not_contact

    # Source
    source = Column(String(100), nullable=True)
    import_batch_id = Column(String(100), nullable=True)

    # Team association
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_contacted_at = Column(DateTime, nullable=True)

    # Relationships
    team = relationship("Team", back_populates="prospects")
    campaign_enrollments = relationship("CampaignProspect", back_populates="prospect")
