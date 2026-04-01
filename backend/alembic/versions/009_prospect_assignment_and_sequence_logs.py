"""Add prospect assignment, research fields, and sequence step logs

Revision ID: 009_prospect_assignment_logs
Revises: 008_add_job_title
Create Date: 2026-03-31

Adds:
- prospects.assigned_to_user_id  -- which user a prospect is assigned to
- prospects.research_data        -- JSON blob of AI research results
- prospects.research_status      -- pending/running/completed/failed
- sequence_step_logs table       -- immutable audit log for 3-point follow-up steps
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "009_prospect_assignment_logs"
down_revision: Union[str, None] = "008_add_job_title"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    cols = [c["name"] for c in sa_inspect(op.get_bind()).get_columns(table)]
    return column in cols


def _table_exists(table: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(table)


def _index_exists(index: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_indexes WHERE indexname = :name"
        ),
        {"name": index},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # prospects: assigned_to_user_id
    # ------------------------------------------------------------------ #
    if not _column_exists("prospects", "assigned_to_user_id"):
        op.add_column(
            "prospects",
            sa.Column(
                "assigned_to_user_id",
                UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
    if not _index_exists("idx_prospects_assigned_to"):
        op.create_index(
            "idx_prospects_assigned_to",
            "prospects",
            ["assigned_to_user_id"],
        )

    # ------------------------------------------------------------------ #
    # prospects: research_data, research_status
    # ------------------------------------------------------------------ #
    if not _column_exists("prospects", "research_data"):
        op.add_column(
            "prospects",
            sa.Column("research_data", JSONB, nullable=True),
        )
    if not _column_exists("prospects", "research_status"):
        op.add_column(
            "prospects",
            sa.Column(
                "research_status",
                sa.String(50),
                nullable=False,
                server_default="pending",
            ),
        )

    # ------------------------------------------------------------------ #
    # sequence_step_logs table
    # ------------------------------------------------------------------ #
    if not _table_exists("sequence_step_logs"):
        op.create_table(
            "sequence_step_logs",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "prospect_id",
                UUID(as_uuid=True),
                sa.ForeignKey("prospects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "campaign_id",
                UUID(as_uuid=True),
                sa.ForeignKey("campaigns.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "sequence_id",
                UUID(as_uuid=True),
                sa.ForeignKey("sequences.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "enrollment_id",
                UUID(as_uuid=True),
                sa.ForeignKey("sequence_enrollments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("sequence_step", sa.Integer, nullable=False),
            sa.Column("action_taken", sa.String(50), nullable=False),
            sa.Column("reply_detected", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("email_content_summary", sa.Text, nullable=True),
            sa.Column("raw_subject", sa.Text, nullable=True),
            sa.Column("raw_body_snippet", sa.Text, nullable=True),
            sa.Column(
                "timestamp",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("NOW()"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("NOW()"),
            ),
        )

    for idx_name, col in [
        ("idx_seq_step_logs_prospect", "prospect_id"),
        ("idx_seq_step_logs_campaign", "campaign_id"),
        ("idx_seq_step_logs_sequence", "sequence_id"),
        ("idx_seq_step_logs_enrollment", "enrollment_id"),
    ]:
        if not _index_exists(idx_name):
            op.create_index(idx_name, "sequence_step_logs", [col])

    if not _index_exists("idx_seq_step_logs_timestamp"):
        op.create_index(
            "idx_seq_step_logs_timestamp",
            "sequence_step_logs",
            ["timestamp"],
            postgresql_ops={"timestamp": "DESC"},
        )


def downgrade() -> None:
    op.drop_table("sequence_step_logs")
    op.drop_index("idx_prospects_assigned_to", table_name="prospects")
    op.drop_column("prospects", "assigned_to_user_id")
    op.drop_column("prospects", "research_data")
    op.drop_column("prospects", "research_status")
