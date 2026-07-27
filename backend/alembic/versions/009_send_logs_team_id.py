"""Add team_id to send_logs (engine tenant column)

Revision ID: 009_send_logs_team_id
Revises: 008_add_job_title
Create Date: 2026-07-21

Single-owner rule for send_logs (SUGGESTIONS 1.4): Alembic owns the schema,
the Go mail-engine no longer creates the table and writes through the aligned
columns (to_email/from_email + this team_id). Guarded with IF NOT EXISTS so
it applies cleanly on databases where a drifted shape already exists.

Known remaining drift (flagged, not fixed here): the SendLog ORM model in
backend/app/models/send_log.py still describes a third shape (recipient_email,
from_address, prospect_id) that matches neither 004 nor the engine. Analytics
queries against it need their own reconciliation pass.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009_send_logs_team_id"
down_revision: Union[str, None] = "008_add_job_title"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # * tenant id written by the mail-engine; NULL until the tenancy control
    # * plane (SUGGESTIONS 3.2) starts supplying real ids
    op.execute("ALTER TABLE send_logs ADD COLUMN IF NOT EXISTS team_id UUID")


def downgrade() -> None:
    op.execute("ALTER TABLE send_logs DROP COLUMN IF EXISTS team_id")
