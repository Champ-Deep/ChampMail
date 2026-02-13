"""Add email accounts table

Revision ID: 003_email_accounts
Revises: 002_domains
Create Date: 2025-01-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003_email_accounts"
down_revision: Union[str, None] = "002_domains"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create email_accounts table
    op.create_table(
        "email_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, index=True),

        # SMTP Configuration (Outbound)
        sa.Column("smtp_host", sa.String(255), nullable=False),
        sa.Column("smtp_port", sa.Integer(), default=587, nullable=False),
        sa.Column("smtp_username", sa.String(255), nullable=False),
        sa.Column("smtp_password_encrypted", sa.Text(), nullable=False),  # Encrypted with Fernet
        sa.Column("smtp_use_tls", sa.Boolean(), default=True, nullable=False),
        sa.Column("smtp_use_ssl", sa.Boolean(), default=False, nullable=False),
        sa.Column("smtp_verified", sa.Boolean(), default=False, nullable=False),
        sa.Column("smtp_verified_at", sa.DateTime(), nullable=True),
        sa.Column("smtp_last_test_at", sa.DateTime(), nullable=True),
        sa.Column("smtp_last_error", sa.Text(), nullable=True),

        # IMAP Configuration (Inbound/Reply Detection)
        sa.Column("imap_host", sa.String(255), nullable=True),
        sa.Column("imap_port", sa.Integer(), default=993, nullable=True),
        sa.Column("imap_username", sa.String(255), nullable=True),
        sa.Column("imap_password_encrypted", sa.Text(), nullable=True),  # Encrypted with Fernet
        sa.Column("imap_use_ssl", sa.Boolean(), default=True, nullable=False),
        sa.Column("imap_mailbox", sa.String(255), default="INBOX", nullable=False),
        sa.Column("imap_verified", sa.Boolean(), default=False, nullable=False),
        sa.Column("imap_verified_at", sa.DateTime(), nullable=True),
        sa.Column("imap_last_check_at", sa.DateTime(), nullable=True),
        sa.Column("imap_last_error", sa.Text(), nullable=True),

        # Sending Settings
        sa.Column("from_name", sa.String(255), nullable=True),
        sa.Column("reply_to_email", sa.String(255), nullable=True),
        sa.Column("is_default", sa.Boolean(), default=False, nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("daily_send_limit", sa.Integer(), default=100, nullable=False),
        sa.Column("emails_sent_today", sa.Integer(), default=0, nullable=False),
        sa.Column("last_send_at", sa.DateTime(), nullable=True),

        # Metadata
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Create index on user_id for fast lookups
    op.create_index("idx_email_accounts_user_id", "email_accounts", ["user_id"])

    # Create index on email for fast lookups
    op.create_index("idx_email_accounts_email", "email_accounts", ["email"])

    # Create composite index for finding default account per user
    op.create_index("idx_email_accounts_user_default", "email_accounts", ["user_id", "is_default"])


def downgrade() -> None:
    op.drop_index("idx_email_accounts_user_default", "email_accounts")
    op.drop_index("idx_email_accounts_email", "email_accounts")
    op.drop_index("idx_email_accounts_user_id", "email_accounts")
    op.drop_table("email_accounts")
