"""Add Harbinger contact-verification columns to prospects

Revision ID: 012_prospect_verification
Revises: 011_send_logs_prospect_id
Create Date: 2026-07-27

Wires the contact-verification waterfall (ChampHarbinger POST /api/v1/enrich/
waterfall) into the campaign pipeline: verify_contacts() writes status and
confidence back onto Prospect before personalize_emails() runs.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "012_prospect_verification"
down_revision: Union[str, None] = "011_send_logs_prospect_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE prospects ADD COLUMN IF NOT EXISTS verification_status VARCHAR(50)")
    op.execute("ALTER TABLE prospects ADD COLUMN IF NOT EXISTS verification_confidence FLOAT")
    op.execute("ALTER TABLE prospects ADD COLUMN IF NOT EXISTS verification_checked_at TIMESTAMP")


def downgrade() -> None:
    op.execute("ALTER TABLE prospects DROP COLUMN IF EXISTS verification_checked_at")
    op.execute("ALTER TABLE prospects DROP COLUMN IF EXISTS verification_confidence")
    op.execute("ALTER TABLE prospects DROP COLUMN IF EXISTS verification_status")
