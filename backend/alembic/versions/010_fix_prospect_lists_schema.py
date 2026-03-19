"""Fix prospect_lists table schema to match endpoint code

Revision ID: 010_fix_prospect_lists
Revises: 009_add_campaign_send_mode
Create Date: 2026-03-19

Migration 005 created prospect_lists with column names that don't match
the endpoint code in app/api/v1/admin/prospect_lists.py. This migration
drops the old table (no production data exists — the endpoint was
returning 500) and recreates it with the correct schema.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "010_fix_prospect_lists"
down_revision: Union[str, None] = "009_add_campaign_send_mode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old table with mismatched columns (created by 005)
    op.execute("DROP TABLE IF EXISTS prospect_lists CASCADE")

    # Recreate with columns matching the endpoint code
    op.create_table(
        "prospect_lists",
        sa.Column("id", sa.String(36), primary_key=True),  # UUID stored as string
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),  # stored filename (e.g. <uuid>.csv)
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="uploaded"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_prospects", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_prospects", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.Text(), nullable=True),       # JSON array of error strings
        sa.Column("warnings", sa.Text(), nullable=True),      # JSON array of warning strings
        sa.Column("headers_found", sa.Text(), nullable=True),  # JSON array of CSV header names
        sa.Column("prospects_json", sa.Text(), nullable=True),  # JSON array of parsed prospect dicts
        sa.Column("team_id", sa.String(36), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
    )

    op.create_index("idx_prospect_lists_team_id_v2", "prospect_lists", ["team_id"])
    op.create_index("idx_prospect_lists_status_v2", "prospect_lists", ["status"])
    op.create_index("idx_prospect_lists_created_by", "prospect_lists", ["created_by"])


def downgrade() -> None:
    op.drop_index("idx_prospect_lists_created_by", "prospect_lists")
    op.drop_index("idx_prospect_lists_status_v2", "prospect_lists")
    op.drop_index("idx_prospect_lists_team_id_v2", "prospect_lists")
    op.drop_table("prospect_lists")
