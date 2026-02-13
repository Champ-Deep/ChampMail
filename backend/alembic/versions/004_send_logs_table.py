"""Add send logs table for email tracking

Revision ID: 004_send_logs
Revises: 003_email_accounts
Create Date: 2025-01-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004_send_logs"
down_revision: Union[str, None] = "003_email_accounts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create send_logs table for tracking all email sends
    op.create_table(
        "send_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("message_id", sa.String(255), unique=True, nullable=False, index=True),

        # References
        sa.Column("domain_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("domains.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("email_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),

        # Email Details
        sa.Column("from_email", sa.String(255), nullable=False, index=True),
        sa.Column("from_name", sa.String(255), nullable=True),
        sa.Column("to_email", sa.String(255), nullable=False, index=True),
        sa.Column("to_name", sa.String(255), nullable=True),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),

        # Tracking
        sa.Column("status", sa.String(50), default="sent", nullable=False, index=True),  # sent, delivered, opened, clicked, bounced, failed
        sa.Column("sent_at", sa.DateTime(), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("opened_at", sa.DateTime(), nullable=True),
        sa.Column("first_opened_at", sa.DateTime(), nullable=True),
        sa.Column("clicked_at", sa.DateTime(), nullable=True),
        sa.Column("first_clicked_at", sa.DateTime(), nullable=True),
        sa.Column("bounced_at", sa.DateTime(), nullable=True),
        sa.Column("replied_at", sa.DateTime(), nullable=True),
        sa.Column("open_count", sa.Integer(), default=0, nullable=False),
        sa.Column("click_count", sa.Integer(), default=0, nullable=False),

        # Bounce/Error Details
        sa.Column("bounce_type", sa.String(50), nullable=True),  # hard, soft, complaint
        sa.Column("bounce_reason", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),

        # Click Tracking
        sa.Column("clicked_urls", postgresql.JSON(), nullable=True),  # Array of clicked URLs

        # Campaign/Sequence Context (optional)
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sequence_id", sa.Integer(), nullable=True),
        sa.Column("step_number", sa.Integer(), nullable=True),

        # Metadata
        sa.Column("metadata", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Create indexes for common queries
    op.create_index("idx_send_logs_message_id", "send_logs", ["message_id"])
    op.create_index("idx_send_logs_to_email", "send_logs", ["to_email"])
    op.create_index("idx_send_logs_from_email", "send_logs", ["from_email"])
    op.create_index("idx_send_logs_status", "send_logs", ["status"])
    op.create_index("idx_send_logs_sent_at", "send_logs", ["sent_at"])
    op.create_index("idx_send_logs_domain_id", "send_logs", ["domain_id"])
    op.create_index("idx_send_logs_user_id", "send_logs", ["user_id"])

    # Composite index for date range queries
    op.create_index("idx_send_logs_user_sent_at", "send_logs", ["user_id", "sent_at"])
    op.create_index("idx_send_logs_domain_sent_at", "send_logs", ["domain_id", "sent_at"])


def downgrade() -> None:
    op.drop_index("idx_send_logs_domain_sent_at", "send_logs")
    op.drop_index("idx_send_logs_user_sent_at", "send_logs")
    op.drop_index("idx_send_logs_user_id", "send_logs")
    op.drop_index("idx_send_logs_domain_id", "send_logs")
    op.drop_index("idx_send_logs_sent_at", "send_logs")
    op.drop_index("idx_send_logs_status", "send_logs")
    op.drop_index("idx_send_logs_from_email", "send_logs")
    op.drop_index("idx_send_logs_to_email", "send_logs")
    op.drop_index("idx_send_logs_message_id", "send_logs")
    op.drop_table("send_logs")
