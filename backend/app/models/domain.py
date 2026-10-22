"""
Domain model for sending domains with DNS verification.

Lifted from v2 with the legacy team link and the DNS check log dropped: v3 has
no teams table, and the DNS checker still lives on the v2 side.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, Float
from sqlalchemy.dialects.postgresql import UUID

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
    # Dedicated sending IP — reputation is owned per-IP, so the ramp-governor keys
    # on this, not only the domain (plan H).
    sending_ip = Column(String(45), nullable=True)  # 45 = max IPv6 textual length

    # External integrations
    namecheap_domain_id = Column(String(255), nullable=True)
    cloudflare_zone_id = Column(String(255), nullable=True)

    # * InboxKit IAL (ChampMail Build Spec §1). infra_provider selects which
    # * MailInfraProvider implementation owns this domain's mailboxes. v3 ships
    # * InboxKit only, so that is the default; the two UID columns are the
    # * InboxKit-native handles and native_status is the raw status string
    # * InboxKit emits (e.g. "configuring_dkim") for debugging.
    infra_provider = Column(String(32), default="inboxkit", nullable=False)
    inboxkit_domain_uid = Column(String(255), nullable=True, index=True)
    inboxkit_workspace_uid = Column(String(255), nullable=True)
    inboxkit_native_status = Column(String(64), nullable=True)

    # Send path (0003): brand selects mailboxes; one tracking host per domain,
    # never a shared fallback.
    brand_id = Column(String(64), nullable=True, index=True)
    tracking_subdomain = Column(String(255), nullable=True)

    # Operator send gate (active|paused|retired) with a reason. Separate from
    # `status` (provider lifecycle) and `paused` (auto-pause) so a webhook can
    # never un-pause it. PATCH cascades it onto the domain's mailboxes (whose
    # `status` the send path reads); new mailboxes inherit it on import.
    send_status = Column(String(16), nullable=False, default="active", server_default="active")
    send_status_reason = Column(Text, nullable=True)
    inboxkit_order_uid = Column(String(255), nullable=True)

    # Deliverability
    health_score = Column(Float, default=100.0)
    bounce_rate = Column(Float, default=0.0)
    complaint_rate = Column(Float, default=0.0)
    last_health_check = Column(DateTime, nullable=True)

    # Blacklist state (refreshed by the worker)
    blacklisted = Column(Boolean, default=False)
    blacklist_hits = Column(Integer, default=0)

    # Auto-pause flag — set by bounce/complaint/blacklist threshold enforcement
    paused = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)