"""seeds registry; per-domain canary counter; send_dispatches.canary

Revision ID: 0008
Revises: 0007

seeds: the only recipients a `canary: true` send may reach. domains.canary_sends_today/_date: the
separate daily cap of 6 canaries per domain. send_dispatches.canary: marks the dispatch row.
Existing rows get 0 / NULL / false, so nothing changes for sends already recorded.
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seeds",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("address", sa.String(320), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("address", name="uq_seeds_address"),
        sa.CheckConstraint("provider IN ('gmail', 'outlook')", name="ck_seeds_provider"),
    )
    op.add_column("domains", sa.Column("canary_sends_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("domains", sa.Column("canary_sends_date", sa.Date()))
    op.add_column("send_dispatches", sa.Column("canary", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("send_dispatches", "canary")
    op.drop_column("domains", "canary_sends_date")
    op.drop_column("domains", "canary_sends_today")
    op.drop_table("seeds")
