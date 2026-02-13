"""Add domains and DNS check logs tables

Revision ID: 002_domains
Revises: 001_initial
Create Date: 2025-01-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002_domains"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create domains table
    op.create_table(
        "domains",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("domain", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("is_verified", sa.Boolean(), default=False, nullable=False),
        sa.Column("verification_status", sa.String(50), default="pending", nullable=False),
        sa.Column("warmup_enabled", sa.Boolean(), default=False, nullable=False),
        sa.Column("warmup_day", sa.Integer(), default=0, nullable=False),
        sa.Column("daily_send_limit", sa.Integer(), default=50, nullable=False),
        sa.Column("emails_sent_today", sa.Integer(), default=0, nullable=False),
        sa.Column("health_score", sa.Integer(), default=100, nullable=False),
        sa.Column("bounce_count", sa.Integer(), default=0, nullable=False),
        sa.Column("last_send_at", sa.DateTime(), nullable=True),
        sa.Column("dkim_selector", sa.String(100), nullable=True),
        sa.Column("dkim_private_key", sa.Text(), nullable=True),
        sa.Column("dkim_public_key", sa.Text(), nullable=True),
        sa.Column("cloudflare_zone_id", sa.String(255), nullable=True),
        sa.Column("namecheap_domain_id", sa.String(255), nullable=True),
        sa.Column("mx_record_status", sa.String(50), default="pending", nullable=False),
        sa.Column("spf_record_status", sa.String(50), default="pending", nullable=False),
        sa.Column("dkim_record_status", sa.String(50), default="pending", nullable=False),
        sa.Column("dmarc_record_status", sa.String(50), default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Create index on team_id for fast lookups
    op.create_index("idx_domains_team_id", "domains", ["team_id"])

    # Create DNS check logs table for tracking verification attempts
    op.create_table(
        "dns_check_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("check_type", sa.String(50), nullable=False),  # mx, spf, dkim, dmarc
        sa.Column("status", sa.String(50), nullable=False),  # pass, fail, pending
        sa.Column("expected_value", sa.Text(), nullable=True),
        sa.Column("actual_value", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # Create index on domain_id for fast lookups
    op.create_index("idx_dns_check_logs_domain_id", "dns_check_logs", ["domain_id"])


def downgrade() -> None:
    op.drop_index("idx_dns_check_logs_domain_id", "dns_check_logs")
    op.drop_table("dns_check_logs")
    op.drop_index("idx_domains_team_id", "domains")
    op.drop_table("domains")
