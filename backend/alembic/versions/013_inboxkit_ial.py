"""Add InboxKit IAL columns to domains and email_accounts

Revision ID: 013_inboxkit_ial
Revises: 012_prospect_verification
Create Date: 2026-07-28

Wires the InboxKit Infrastructure Abstraction Layer (ChampMail Build Spec
§1) into the schema. Domain.infra_provider selects which MailInfraProvider
owns a given domain ("stalwart" default, "inboxkit" when bought via the
InboxKit API). The InboxKit-native UIDs and raw status strings are stored
alongside for debugging and for the webhook handler's re-fetch pattern.

EmailAccount gains inboxkit_uid (the provider-native mailbox handle),
platform, and credentials_persisted (set True only after the authenticated
GET /mailboxes/show-credentials call succeeds — creds arriving in webhook
payloads are discarded per the security model).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "013_inboxkit_ial"
down_revision: Union[str, None] = "012_prospect_verification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # domains
    op.execute(
        "ALTER TABLE domains "
        "ADD COLUMN IF NOT EXISTS infra_provider VARCHAR(32) NOT NULL DEFAULT 'stalwart'"
    )
    op.execute(
        "ALTER TABLE domains ADD COLUMN IF NOT EXISTS inboxkit_domain_uid VARCHAR(255)"
    )
    op.execute(
        "ALTER TABLE domains ADD COLUMN IF NOT EXISTS inboxkit_workspace_uid VARCHAR(255)"
    )
    op.execute(
        "ALTER TABLE domains ADD COLUMN IF NOT EXISTS inboxkit_native_status VARCHAR(64)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_domains_inboxkit_domain_uid "
        "ON domains (inboxkit_domain_uid)"
    )

    # email_accounts
    op.execute(
        "ALTER TABLE email_accounts ADD COLUMN IF NOT EXISTS inboxkit_uid VARCHAR(255)"
    )
    op.execute(
        "ALTER TABLE email_accounts ADD COLUMN IF NOT EXISTS inboxkit_workspace_uid VARCHAR(255)"
    )
    op.execute(
        "ALTER TABLE email_accounts ADD COLUMN IF NOT EXISTS platform VARCHAR(32)"
    )
    op.execute(
        "ALTER TABLE email_accounts ADD COLUMN IF NOT EXISTS credentials_persisted BOOLEAN "
        "DEFAULT FALSE"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_email_accounts_inboxkit_uid "
        "ON email_accounts (inboxkit_uid)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_email_accounts_inboxkit_uid")
    op.execute("ALTER TABLE email_accounts DROP COLUMN IF EXISTS credentials_persisted")
    op.execute("ALTER TABLE email_accounts DROP COLUMN IF EXISTS platform")
    op.execute("ALTER TABLE email_accounts DROP COLUMN IF EXISTS inboxkit_workspace_uid")
    op.execute("ALTER TABLE email_accounts DROP COLUMN IF EXISTS inboxkit_uid")

    op.execute("DROP INDEX IF EXISTS ix_domains_inboxkit_domain_uid")
    op.execute("ALTER TABLE domains DROP COLUMN IF EXISTS inboxkit_native_status")
    op.execute("ALTER TABLE domains DROP COLUMN IF EXISTS inboxkit_workspace_uid")
    op.execute("ALTER TABLE domains DROP COLUMN IF EXISTS inboxkit_domain_uid")
    op.execute("ALTER TABLE domains DROP COLUMN IF EXISTS infra_provider")
