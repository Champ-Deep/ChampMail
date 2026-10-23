"""MX toolkit: dnsbl_zones (seeded), domain_health_daily, dmarc_reports, domains.dns_status

Revision ID: 0009
Revises: 0008

dnsbl_zones is config: the three lists the spec names, queried read-only. domain_health_daily is one row
per domain per UTC day. dmarc_reports is one row per aggregate report (unique per org, report id, domain).
domains.dns_status tracks Cloudflare DNS automation: NULL (not automated), pending, propagated, failed.
Existing rows get NULL, so nothing changes for domains already provisioned.
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

ZONES = [
    ("spamhaus_zen", "zen.spamhaus.org", "ip"),
    ("surbl", "multi.surbl.org", "domain"),
    ("barracuda", "b.barracudacentral.org", "ip"),
]


def upgrade() -> None:
    zones = op.create_table(
        "dnsbl_zones",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("zone", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.CheckConstraint("kind IN ('ip', 'domain')", name="ck_dnsbl_zones_kind"),
    )
    op.bulk_insert(zones, [{"id": uuid.uuid4(), "name": n, "zone": z, "kind": k, "enabled": True} for n, z, k in ZONES])
    op.create_table(
        "domain_health_daily",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("domain_id", sa.Uuid(), sa.ForeignKey("domains.id"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("spf_ok", sa.Boolean(), nullable=False),
        sa.Column("dkim_ok", sa.Boolean(), nullable=False),
        sa.Column("dmarc_policy", sa.String(16)),
        sa.Column("dmarc_aligned", sa.Boolean()),
        sa.Column("mta_sts_ok", sa.Boolean(), nullable=False),
        sa.Column("dnsbl_listed", sa.JSON(), nullable=False),
        sa.Column("dmarc_reports_pass_count", sa.Integer(), nullable=False),
        sa.Column("dmarc_reports_fail_count", sa.Integer(), nullable=False),
        sa.Column("postmaster_spam_rate", sa.Float()),
        sa.Column("postmaster_reputation", sa.String(16)),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("domain_id", "day", name="uq_domain_health_daily_domain_day"),
    )
    op.create_index("ix_domain_health_daily_domain_id", "domain_health_daily", ["domain_id"])
    op.create_table(
        "dmarc_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_name", sa.String(255), nullable=False),
        sa.Column("report_id", sa.String(255), nullable=False),
        sa.Column("domain_id", sa.Uuid(), sa.ForeignKey("domains.id"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("pass_count", sa.Integer(), nullable=False),
        sa.Column("fail_count", sa.Integer(), nullable=False),
        sa.Column("fail_ips", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("org_name", "report_id", "domain_id", name="uq_dmarc_reports_org_report_domain"),
    )
    op.create_index("ix_dmarc_reports_domain_id", "dmarc_reports", ["domain_id"])
    op.create_index("ix_dmarc_reports_day", "dmarc_reports", ["day"])
    op.add_column("domains", sa.Column("dns_status", sa.String(16)))


def downgrade() -> None:
    op.drop_column("domains", "dns_status")
    op.drop_table("dmarc_reports")
    op.drop_table("domain_health_daily")
    op.drop_table("dnsbl_zones")
