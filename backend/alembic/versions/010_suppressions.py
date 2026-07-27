"""Suppression list (SUGGESTIONS 4.6)

Revision ID: 010_suppressions
Revises: 009_send_logs_team_id
Create Date: 2026-07-21

Legal prerequisite for real outreach (CAN-SPAM/GDPR): every send path must
check this table before dispatch. Keyed by email (+optional tenant). Written
by the suppression route on email.bounced / email.unsubscribed events and by
manual adds.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "010_suppressions"
down_revision: Union[str, None] = "009_send_logs_team_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "suppressions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, index=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.String(50), nullable=False),  # bounce | unsubscribe | manual
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("email", "team_id", name="uq_suppressions_email_team"),
    )
    op.create_index("idx_suppressions_email", "suppressions", ["email"])


def downgrade() -> None:
    op.drop_index("idx_suppressions_email", "suppressions")
    op.drop_table("suppressions")
