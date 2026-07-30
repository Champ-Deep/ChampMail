"""Add prospect_id to send_logs (analytics uses it; 004 omitted it)

Revision ID: 011_send_logs_prospect_id
Revises: 010_suppressions
Create Date: 2026-07-21

Completes the send_logs convergence (SUGGESTIONS 1.4 follow-up): Alembic owns
the shape (004), the Go engine writes it, and the ORM model now mirrors it.
prospect_id is the one column the ORM/analytics side needed that 004 lacked.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "011_send_logs_prospect_id"
down_revision: Union[str, None] = "010_suppressions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE send_logs ADD COLUMN IF NOT EXISTS prospect_id UUID")


def downgrade() -> None:
    op.execute("ALTER TABLE send_logs DROP COLUMN IF EXISTS prospect_id")
