"""Add data team role, prospect lists, and audit logs

Revision ID: 005_data_team
Revises: 004_send_logs
Create Date: 2026-02-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005_data_team"
down_revision: Union[str, None] = "004_send_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Note: data_team role will be added to User model enum
    # No DB change needed for role - it's a string field

    # Create prospect_lists table for secure file upload tracking
    op.create_table(
        "prospect_lists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),

        # File storage
        sa.Column("file_path", sa.String(500), nullable=False),  # Encrypted storage path
        sa.Column("file_hash", sa.String(64), nullable=False),  # SHA256 for deduplication
        sa.Column("file_size", sa.BigInteger(), nullable=False),  # Bytes
        sa.Column("original_filename", sa.String(255), nullable=False),

        # Ownership
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True),

        # Processing status
        sa.Column("status", sa.String(50), default="uploading", nullable=False, index=True),  # uploading, processing, ready, failed
        sa.Column("total_prospects", sa.Integer(), default=0, nullable=False),
        sa.Column("processed_prospects", sa.Integer(), default=0, nullable=False),
        sa.Column("failed_prospects", sa.Integer(), default=0, nullable=False),

        # Security
        sa.Column("is_downloadable", sa.Boolean(), default=False, nullable=False),  # Never allow download by default
        sa.Column("is_deleted", sa.Boolean(), default=False, nullable=False),  # Soft delete

        # Processing metadata
        sa.Column("processing_errors", postgresql.JSON(), nullable=True),  # List of errors
        sa.Column("processing_started_at", sa.DateTime(), nullable=True),
        sa.Column("processing_completed_at", sa.DateTime(), nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Create indexes for prospect_lists
    op.create_index("idx_prospect_lists_team_id", "prospect_lists", ["team_id"])
    op.create_index("idx_prospect_lists_status", "prospect_lists", ["status"])
    op.create_index("idx_prospect_lists_uploaded_by", "prospect_lists", ["uploaded_by"])
    op.create_index("idx_prospect_lists_file_hash", "prospect_lists", ["file_hash"])

    # Create audit_logs table for tracking sensitive operations
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        # Actor
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("user_email", sa.String(255), nullable=True),  # Denormalized for retention
        sa.Column("user_role", sa.String(50), nullable=True),

        # Action
        sa.Column("action", sa.String(100), nullable=False, index=True),  # create, update, delete, export, download, upload
        sa.Column("resource_type", sa.String(50), nullable=False, index=True),  # prospect_list, campaign, user, etc.
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("resource_name", sa.String(255), nullable=True),  # Denormalized for readability

        # Context
        sa.Column("ip_address", sa.String(45), nullable=True),  # IPv4 or IPv6
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("request_method", sa.String(10), nullable=True),  # GET, POST, PUT, DELETE
        sa.Column("request_path", sa.String(500), nullable=True),

        # Details
        sa.Column("details", postgresql.JSON(), nullable=True),  # Arbitrary metadata
        sa.Column("changes", postgresql.JSON(), nullable=True),  # Before/after for updates

        # Outcome
        sa.Column("status", sa.String(50), default="success", nullable=False),  # success, failed, denied
        sa.Column("error_message", sa.Text(), nullable=True),

        # Timestamp
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False, index=True),
    )

    # Create indexes for audit_logs
    op.create_index("idx_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("idx_audit_logs_team_id", "audit_logs", ["team_id"])
    op.create_index("idx_audit_logs_action", "audit_logs", ["action"])
    op.create_index("idx_audit_logs_resource_type", "audit_logs", ["resource_type"])
    op.create_index("idx_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("idx_audit_logs_resource_id", "audit_logs", ["resource_id"])

    # Composite indexes for common queries
    op.create_index("idx_audit_logs_team_created", "audit_logs", ["team_id", "created_at"])
    op.create_index("idx_audit_logs_user_action", "audit_logs", ["user_id", "action"])
    op.create_index("idx_audit_logs_resource_lookup", "audit_logs", ["resource_type", "resource_id"])


def downgrade() -> None:
    # Drop audit_logs
    op.drop_index("idx_audit_logs_resource_lookup", "audit_logs")
    op.drop_index("idx_audit_logs_user_action", "audit_logs")
    op.drop_index("idx_audit_logs_team_created", "audit_logs")
    op.drop_index("idx_audit_logs_resource_id", "audit_logs")
    op.drop_index("idx_audit_logs_created_at", "audit_logs")
    op.drop_index("idx_audit_logs_resource_type", "audit_logs")
    op.drop_index("idx_audit_logs_action", "audit_logs")
    op.drop_index("idx_audit_logs_team_id", "audit_logs")
    op.drop_index("idx_audit_logs_user_id", "audit_logs")
    op.drop_table("audit_logs")

    # Drop prospect_lists
    op.drop_index("idx_prospect_lists_file_hash", "prospect_lists")
    op.drop_index("idx_prospect_lists_uploaded_by", "prospect_lists")
    op.drop_index("idx_prospect_lists_status", "prospect_lists")
    op.drop_index("idx_prospect_lists_team_id", "prospect_lists")
    op.drop_table("prospect_lists")
