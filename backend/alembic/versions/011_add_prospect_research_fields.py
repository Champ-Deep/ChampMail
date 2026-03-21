"""Add prospect research fields (location, timezone, research_status, linkedin_connection_status)

Revision ID: 011_add_prospect_research
Revises: 010_fix_prospect_lists
Create Date: 2026-03-21

Adds columns for the prospect research pipeline:
- location: city/state/country extracted from research
- timezone: IANA timezone string for send scheduling
- research_status: pending/completed/failed
- research_completed_at: when research was last run
- linkedin_connection_status: manual connection tracking
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "011_add_prospect_research"
down_revision: Union[str, None] = "010_fix_prospect_lists"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("prospects", sa.Column("location", sa.String(255), nullable=True))
    op.add_column("prospects", sa.Column("timezone", sa.String(100), nullable=True))
    op.add_column(
        "prospects",
        sa.Column("research_status", sa.String(50), server_default="pending", nullable=True),
    )
    op.add_column(
        "prospects",
        sa.Column("research_completed_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "prospects",
        sa.Column("linkedin_connection_status", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("prospects", "linkedin_connection_status")
    op.drop_column("prospects", "research_completed_at")
    op.drop_column("prospects", "research_status")
    op.drop_column("prospects", "timezone")
    op.drop_column("prospects", "location")
