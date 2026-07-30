"""Link email_accounts to their owning domain

Revision ID: 014_email_account_domain
Revises: 013_inboxkit_ial
Create Date: 2026-07-29

email_accounts had no domain foreign key at all, so any code picking "the
mailbox for domain X" (send agent, InboxKit warmup delegation) had no way
to scope the query and could silently grab a mailbox belonging to a
different domain. This adds the missing link; existing rows get NULL
until the next InboxKit webhook / backfill sets it.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "014_email_account_domain_link"
down_revision: Union[str, None] = "013_inboxkit_ial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE email_accounts ADD COLUMN IF NOT EXISTS domain_id UUID "
        "REFERENCES domains(id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_email_accounts_domain_id "
        "ON email_accounts (domain_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_email_accounts_domain_id")
    op.execute("ALTER TABLE email_accounts DROP COLUMN IF EXISTS domain_id")
