"""domain_health_daily DMARC counts are nullable: NULL means no aggregate report covered the day

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

COLS = ("dmarc_reports_pass_count", "dmarc_reports_fail_count")


def upgrade() -> None:
    for c in COLS:
        op.alter_column("domain_health_daily", c, existing_type=sa.Integer(), nullable=True)
    # 0009 wrote 0 for "no report"; only rows with both zero are unknown, a real 0 fail with passes stays.
    op.execute("UPDATE domain_health_daily SET dmarc_reports_pass_count = NULL, dmarc_reports_fail_count = NULL "
               "WHERE dmarc_reports_pass_count = 0 AND dmarc_reports_fail_count = 0")


def downgrade() -> None:
    for c in COLS:
        op.execute(f"UPDATE domain_health_daily SET {c} = 0 WHERE {c} IS NULL")
        op.alter_column("domain_health_daily", c, existing_type=sa.Integer(), nullable=False)
