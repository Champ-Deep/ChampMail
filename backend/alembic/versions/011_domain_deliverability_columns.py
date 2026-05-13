"""Add deliverability columns to domains table

Revision ID: 011
Revises: 010
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("domains", sa.Column("complaint_rate", sa.Float(), nullable=True, server_default="0.0"))
    op.add_column("domains", sa.Column("blacklisted", sa.Boolean(), nullable=True, server_default="false"))
    op.add_column("domains", sa.Column("blacklist_hits", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("domains", sa.Column("paused", sa.Boolean(), nullable=True, server_default="false"))


def downgrade() -> None:
    op.drop_column("domains", "paused")
    op.drop_column("domains", "blacklist_hits")
    op.drop_column("domains", "blacklisted")
    op.drop_column("domains", "complaint_rate")
