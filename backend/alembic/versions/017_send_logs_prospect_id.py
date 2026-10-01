"""Add prospect_id to send_logs (analytics uses it; 004 omitted it)

Revision ID: 017_send_logs_prospect_id
Revises: 016_suppressions
Create Date: 2026-07-21

Completes the send_logs convergence (SUGGESTIONS 1.4 follow-up): Alembic owns
the shape (004), the Go engine writes it, and the ORM model now mirrors it.
prospect_id is the one column the ORM/analytics side needed that 004 lacked.
"""
from typing import Sequence, Union

from alembic import op

revision = "017_send_logs_prospect_id"
down_revision = "016_suppressions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE send_logs ADD COLUMN IF NOT EXISTS prospect_id UUID")


def downgrade() -> None:
    op.execute("ALTER TABLE send_logs DROP COLUMN IF EXISTS prospect_id")
