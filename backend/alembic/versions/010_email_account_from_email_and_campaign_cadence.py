"""Add from_email to email_accounts and cadence_seconds to campaigns

Revision ID: 010_from_email_cadence
Revises: 009_prospect_assignment_logs
Create Date: 2026-04-16

Adds:
- email_accounts.from_email     -- display "From" address (may differ from login email)
- campaigns.cadence_seconds     -- minimum gap between sends (default 3600 = 1 hour)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "010_from_email_cadence"
down_revision: Union[str, None] = "009_prospect_assignment_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # email_accounts.from_email — nullable, user sets this to control the visible "From" address
    op.add_column(
        "email_accounts",
        sa.Column("from_email", sa.String(255), nullable=True),
    )
    # campaigns.cadence_seconds — default 1 hour between sends
    op.add_column(
        "campaigns",
        sa.Column("cadence_seconds", sa.Integer(), server_default="3600", nullable=True),
    )


def downgrade() -> None:
    op.drop_column("campaigns", "cadence_seconds")
    op.drop_column("email_accounts", "from_email")
