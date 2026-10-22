"""bounces: parsed DSNs, hard and soft

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bounces",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email_account_id", sa.Uuid(), sa.ForeignKey("email_accounts.id"), nullable=False),
        sa.Column("dsn_hash", sa.String(64), nullable=False),
        sa.Column("message_id", sa.String(998)),
        sa.Column("recipient", sa.String(255)),
        sa.Column("status_code", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("diagnostic", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
        sa.UniqueConstraint("dsn_hash", name="uq_bounces_dsn_hash"),
    )
    op.create_index("ix_bounces_email_account_id", "bounces", ["email_account_id"])
    op.create_index("ix_bounces_message_id", "bounces", ["message_id"])


def downgrade() -> None:
    op.drop_table("bounces")
