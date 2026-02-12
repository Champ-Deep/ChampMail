"""
Sequence model for multi-step email outreach sequences.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.postgres import Base


class Sequence(Base):
    """Email sequence model for automated multi-step outreach."""

    __tablename__ = "sequences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Status
    status = Column(String(50), default="draft")  # draft, active, paused

    # Configuration
    from_name = Column(String(255), nullable=True)
    from_address = Column(String(255), nullable=True)
    reply_to = Column(String(255), nullable=True)

    # Scheduling
    default_delay_hours = Column(Integer, default=24)
    business_hours_only = Column(Boolean, default=False)
    timezone = Column(String(50), default="UTC")

    # Limits
    daily_limit = Column(Integer, default=100)

    # Reply detection
    auto_pause_on_reply = Column(Boolean, default=True)
    reply_detection_enabled = Column(Boolean, default=True)

    # AI configuration
    use_ai_personalization = Column(Boolean, default=False)
    ai_model = Column(String(50), default="claude-3-5-sonnet")

    # Campaign association
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=True)

    # Team association
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    activated_at = Column(DateTime, nullable=True)

    # Relationships
    team = relationship("Team", back_populates="sequences")
    campaign = relationship("Campaign", back_populates="sequence")
    steps = relationship("SequenceStep", back_populates="sequence", order_by="SequenceStep.order")
    enrollments = relationship("SequenceEnrollment", back_populates="sequence")


class SequenceStep(Base):
    """Individual step within a sequence."""

    __tablename__ = "sequence_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    sequence_id = Column(UUID(as_uuid=True), ForeignKey("sequences.id"), nullable=False)

    order = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)

    # Email content
    subject_template = Column(Text, nullable=True)
    html_template = Column(Text, nullable=True)
    plain_text_template = Column(Text, nullable=True)

    # AI personalization for this step
    use_ai_personalization = Column(Boolean, default=False)
    ai_prompt = Column(Text, nullable=True)

    # Timing
    delay_hours = Column(Integer, default=24)
    delay_days = Column(Integer, default=0)
    send_at_hour = Column(Integer, nullable=True)  # Hour of day to send (0-23)

    # Reply handling
    wait_for_reply = Column(Boolean, default=False)
    skip_if_no_open = Column(Boolean, default=False)
    skip_if_clicked = Column(Boolean, default=False)

    # Status
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sequence = relationship("Sequence", back_populates="steps")
    executions = relationship("SequenceStepExecution", back_populates="step")


class SequenceEnrollment(Base):
    """Enrollment of a prospect in a sequence."""

    __tablename__ = "sequence_enrollments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    sequence_id = Column(UUID(as_uuid=True), ForeignKey("sequences.id"), nullable=False)
    prospect_id = Column(UUID(as_uuid=True), ForeignKey("prospects.id"), nullable=False)

    status = Column(String(50), default="active")  # active, completed, paused, stopped
    current_step_order = Column(Integer, default=0)

    # Metrics
    emails_sent = Column(Integer, default=0)
    opened = Column(Boolean, default=False)
    clicked = Column(Boolean, default=False)
    replied = Column(Boolean, default=False)
    bounced = Column(Boolean, default=False)

    # Timing
    enrolled_at = Column(DateTime, default=datetime.utcnow)
    next_step_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    paused_at = Column(DateTime, nullable=True)
    pause_reason = Column(String(255), nullable=True)

    # Relationships
    sequence = relationship("Sequence", back_populates="enrollments")
    prospect = relationship("Prospect")


class SequenceStepExecution(Base):
    """Execution record for sequence steps."""

    __tablename__ = "sequence_step_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("sequence_enrollments.id"), nullable=False)
    step_id = Column(UUID(as_uuid=True), ForeignKey("sequence_steps.id"), nullable=False)

    status = Column(String(50), default="pending")  # pending, scheduled, sent, failed, skipped

    # Email details
    message_id = Column(String(255), nullable=True)
    recipient_email = Column(String(255), nullable=True)
    subject = Column(Text, nullable=True)
    html_body = Column(Text, nullable=True)

    # Timing
    scheduled_for = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    opened_at = Column(DateTime, nullable=True)
    clicked_at = Column(DateTime, nullable=True)

    # Error handling
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    enrollment = relationship("SequenceEnrollment")
    step = relationship("SequenceStep", back_populates="executions")
