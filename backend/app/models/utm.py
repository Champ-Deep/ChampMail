"""
UTM tracking models for presets, campaign configs, and link click tracking.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship

from app.db.postgres import Base


class UTMPreset(Base):
    """Reusable UTM parameter presets scoped to a team."""

    __tablename__ = "utm_presets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    is_default = Column(Boolean, default=False)

    # UTM fields
    utm_source = Column(String(255), nullable=True)
    utm_medium = Column(String(255), nullable=True)
    utm_campaign = Column(String(255), nullable=True)
    utm_content = Column(String(255), nullable=True)
    utm_term = Column(String(255), nullable=True)

    # Additional custom parameters
    custom_params = Column(JSON, nullable=True)

    # Audit
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    team = relationship("Team", backref="utm_presets")
    created_by_user = relationship("User", foreign_keys=[created_by])


class CampaignUTMConfig(Base):
    """Per-campaign UTM configuration, optionally derived from a preset."""

    __tablename__ = "campaign_utm_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), unique=True, nullable=False)
    preset_id = Column(UUID(as_uuid=True), ForeignKey("utm_presets.id", ondelete="SET NULL"), nullable=True)
    enabled = Column(Boolean, default=True)

    # UTM fields (override preset values)
    utm_source = Column(String(255), nullable=True)
    utm_medium = Column(String(255), nullable=True)
    utm_campaign = Column(String(255), nullable=True)
    utm_content = Column(String(255), nullable=True)
    utm_term = Column(String(255), nullable=True)

    # Additional parameters
    custom_params = Column(JSON, nullable=True)
    link_overrides = Column(JSON, nullable=True)
    preserve_existing_utm = Column(Boolean, default=True)

    # Team association
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    campaign = relationship("Campaign", back_populates="utm_config")
    preset = relationship("UTMPreset", foreign_keys=[preset_id])


class LinkClick(Base):
    """Per-link click tracking with UTM attribution."""

    __tablename__ = "link_clicks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    prospect_id = Column(UUID(as_uuid=True), ForeignKey("prospects.id", ondelete="SET NULL"), nullable=True)
    send_log_id = Column(UUID(as_uuid=True), ForeignKey("send_logs.id", ondelete="SET NULL"), nullable=True)

    # Link details
    original_url = Column(Text, nullable=False)
    tracked_url = Column(Text, nullable=True)
    anchor_text = Column(String(500), nullable=True)
    link_position = Column(Integer, nullable=True)

    # UTM attribution
    utm_source = Column(String(255), nullable=True)
    utm_medium = Column(String(255), nullable=True)
    utm_campaign = Column(String(255), nullable=True)
    utm_content = Column(String(255), nullable=True)
    utm_term = Column(String(255), nullable=True)

    # Click metrics
    click_count = Column(Integer, default=0)
    unique_clicks = Column(Integer, default=0)
    first_clicked_at = Column(DateTime, nullable=True)
    last_clicked_at = Column(DateTime, nullable=True)

    # Team association
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    campaign = relationship("Campaign", backref="link_clicks")
    prospect = relationship("Prospect", backref="link_clicks")
    send_log = relationship("SendLog", backref="link_clicks")
