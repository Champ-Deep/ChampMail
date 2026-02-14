"""
User model for PostgreSQL persistence.

Replaces the in-memory user storage with proper database persistence.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.postgres import Base


class Team(Base):
    """Team/organization model for multi-user support."""

    __tablename__ = "teams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", use_alter=True), nullable=True)
    max_members = Column(String(50), default="10")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    members = relationship("User", back_populates="team", foreign_keys="User.team_id")
    domains = relationship("Domain", back_populates="team")
    campaigns = relationship("Campaign", back_populates="team")
    sequences = relationship("Sequence", back_populates="team")
    prospects = relationship("Prospect", back_populates="team")


class User(Base):
    """User model with authentication and team support."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    job_title = Column(String(255), nullable=True)
    role = Column(String(50), default="user")  # user, admin, team_admin

    # Team association
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)

    # Account status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

    # Onboarding progress tracking (for interactive tutorials)
    onboarding_progress = Column(JSON, default=lambda: {"completed_tours": [], "skipped_tours": []})

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    # Relationships
    team = relationship("Team", back_populates="members", foreign_keys=[team_id])
    email_settings = relationship("EmailSettings", back_populates="user", uselist=False)
    email_accounts = relationship("EmailAccount", back_populates="user", order_by="EmailAccount.created_at")


class TeamInvite(Base):
    """Team invitation model for onboarding new members."""

    __tablename__ = "team_invites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    email = Column(String(255), nullable=False)
    role = Column(String(50), default="user")
    token = Column(String(255), unique=True, nullable=False)
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    team = relationship("Team")
    inviter = relationship("User", foreign_keys=[invited_by])
