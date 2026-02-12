"""
n8n Workflow models for PostgreSQL persistence.

Stores workflow configurations imported from n8n JSON files.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.db.postgres import Base


class WorkflowType(str, Enum):
    """Types of email automation workflows."""
    AUTO_REPLY = "auto_reply"  # Auto Email Reply - IMAP Listener
    EMAIL_WRITER = "email_writer"  # Email Writer
    EMAIL_SUMMARY = "email_summary"  # User Call Email Summary
    CONTROLLER = "controller"  # Head Bot Flow - Main Telegram Controller
    CUSTOM = "custom"  # User-defined workflows


class WorkflowStatus(str, Enum):
    """Workflow activation status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class Workflow(Base):
    """
    Workflow model for storing n8n workflow configurations.

    Each workflow represents an automated email process that can be
    triggered via webhooks or scheduled execution.
    """

    __tablename__ = "workflows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Basic info
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    workflow_type = Column(SQLEnum(WorkflowType), default=WorkflowType.CUSTOM)

    # n8n reference
    n8n_workflow_id = Column(String(100), nullable=True, unique=True)  # ID from n8n
    n8n_webhook_path = Column(String(255), nullable=True)  # Webhook endpoint path

    # Configuration stored as JSON
    config = Column(JSONB, default=dict)  # Full n8n workflow JSON
    settings = Column(JSONB, default=dict)  # User-configurable settings

    # Status
    status = Column(SQLEnum(WorkflowStatus), default=WorkflowStatus.INACTIVE)
    is_active = Column(Boolean, default=False)

    # Ownership
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)

    # Statistics
    execution_count = Column(String(50), default="0")
    last_executed_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner = relationship("User", foreign_keys=[owner_id])
    executions = relationship("WorkflowExecution", back_populates="workflow", cascade="all, delete-orphan")


class WorkflowExecution(Base):
    """
    Tracks individual workflow executions for logging and debugging.
    """

    __tablename__ = "workflow_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id"), nullable=False)

    # Execution details
    status = Column(String(50), default="pending")  # pending, running, success, failed
    trigger_type = Column(String(50), nullable=True)  # webhook, schedule, manual

    # Input/Output data
    input_data = Column(JSONB, default=dict)
    output_data = Column(JSONB, default=dict)
    error_message = Column(Text, nullable=True)

    # Timing
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(String(50), nullable=True)

    # Relationships
    workflow = relationship("Workflow", back_populates="executions")
