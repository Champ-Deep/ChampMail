"""MX toolkit tables: DNSBL zone config, one health row per domain per day, one row per DMARC aggregate report."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, Column, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.postgres import Base


class DnsblZone(Base):
    """A blocklist to query. kind `ip` zones are asked about the domain's IPv4 addresses (reversed octets),
    `domain` zones about the domain name. Rows are config: add or disable one without a deploy."""

    __tablename__ = "dnsbl_zones"
    __table_args__ = (CheckConstraint("kind IN ('ip', 'domain')", name="ck_dnsbl_zones_kind"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(64), nullable=False, unique=True)
    zone = Column(String(255), nullable=False)
    kind = Column(String(8), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)


class DomainHealthDaily(Base):
    """What the daily job saw for one domain on one UTC day. `dnsbl_listed` is the list of zone names that hit."""

    __tablename__ = "domain_health_daily"
    __table_args__ = (UniqueConstraint("domain_id", "day", name="uq_domain_health_daily_domain_day"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain_id = Column(UUID(as_uuid=True), ForeignKey("domains.id"), nullable=False, index=True)
    day = Column(Date, nullable=False)
    spf_ok = Column(Boolean, nullable=False)
    dkim_ok = Column(Boolean, nullable=False)
    dmarc_policy = Column(String(16), nullable=True)  # none | quarantine | reject, NULL when no valid record
    dmarc_aligned = Column(Boolean, nullable=True)  # NULL when no aggregate report covered the previous day
    mta_sts_ok = Column(Boolean, nullable=False)
    dnsbl_listed = Column(JSON, nullable=False, default=list)
    dmarc_reports_pass_count = Column(Integer, nullable=False, default=0)  # previous UTC day, from dmarc_reports
    dmarc_reports_fail_count = Column(Integer, nullable=False, default=0)
    postmaster_spam_rate = Column(Float, nullable=True)  # NULL unless Postmaster Tools is configured and has data
    postmaster_reputation = Column(String(16), nullable=True)
    source = Column(String(64), nullable=False)  # which inputs contributed, e.g. dns+dmarc+postmaster
    checked_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class DmarcReport(Base):
    """One DMARC aggregate report for one of our domains. (org, report_id, domain) is unique so re-reading a
    mailbox never double counts. Counts are weighted by each record's message count."""

    __tablename__ = "dmarc_reports"
    __table_args__ = (UniqueConstraint("org_name", "report_id", "domain_id", name="uq_dmarc_reports_org_report_domain"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_name = Column(String(255), nullable=False)
    report_id = Column(String(255), nullable=False)
    domain_id = Column(UUID(as_uuid=True), ForeignKey("domains.id"), nullable=False, index=True)
    day = Column(Date, nullable=False, index=True)  # UTC date the reporting window began
    pass_count = Column(Integer, nullable=False)
    fail_count = Column(Integer, nullable=False)
    fail_ips = Column(JSON, nullable=False, default=dict)  # {source ip: failing message count}
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
