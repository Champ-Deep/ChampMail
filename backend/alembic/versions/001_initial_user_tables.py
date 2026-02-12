"""Initial user and team tables

Revision ID: 001_initial
Revises:
Create Date: 2025-01-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create teams table first (users reference it)
    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("max_members", sa.String(50), default="10"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(50), default="user"),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("is_verified", sa.Boolean(), default=False),
        sa.Column("onboarding_progress", postgresql.JSON(), default={}),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("last_login", sa.DateTime(), nullable=True),
    )

    # Add foreign key from teams.owner_id to users.id
    op.create_foreign_key(
        "fk_teams_owner_id",
        "teams",
        "users",
        ["owner_id"],
        ["id"],
    )

    # Create team_invites table
    op.create_table(
        "team_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), default="user"),
        sa.Column("token", sa.String(255), unique=True, nullable=False),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # Create email_settings table
    op.create_table(
        "email_settings",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), primary_key=True),
        # SMTP Configuration
        sa.Column("smtp_host", sa.String(255), nullable=True),
        sa.Column("smtp_port", sa.Integer(), default=587),
        sa.Column("smtp_username", sa.String(255), nullable=True),
        sa.Column("smtp_password_encrypted", sa.Text(), nullable=True),
        sa.Column("smtp_use_tls", sa.Boolean(), default=True),
        sa.Column("smtp_verified", sa.Boolean(), default=False),
        sa.Column("smtp_verified_at", sa.DateTime(), nullable=True),
        # IMAP Configuration
        sa.Column("imap_host", sa.String(255), nullable=True),
        sa.Column("imap_port", sa.Integer(), default=993),
        sa.Column("imap_username", sa.String(255), nullable=True),
        sa.Column("imap_password_encrypted", sa.Text(), nullable=True),
        sa.Column("imap_use_ssl", sa.Boolean(), default=True),
        sa.Column("imap_mailbox", sa.String(255), default="INBOX"),
        sa.Column("imap_verified", sa.Boolean(), default=False),
        sa.Column("imap_verified_at", sa.DateTime(), nullable=True),
        # Sending Identity
        sa.Column("from_email", sa.String(255), nullable=True),
        sa.Column("from_name", sa.String(255), nullable=True),
        sa.Column("reply_to_email", sa.String(255), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("email_settings")
    op.drop_table("team_invites")
    op.drop_constraint("fk_teams_owner_id", "teams", type_="foreignkey")
    op.drop_table("users")
    op.drop_table("teams")
