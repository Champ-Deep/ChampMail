"""mail infra baseline: domains + email_accounts (squashed v2 019-021)

Revision ID: 0002
Revises: 0001

Squashes the v2 content of 019 (InboxKit IAL columns), 020 (mailbox ->
owning domain) and 021 (per-mailbox send accounting) into one fresh
baseline on top of the empty 0001, plus the tables those columns belong to.

Differences from the v2 donors, all deliberate:
- email_accounts has no users FK (v3 has no users table); the column stays.
- domains lost team_id and the DNS check log table: no teams table in v3.
- daily_send_limit defaults to 30 (v2 shipped 25), model + baseline together.
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "domains",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("domain_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column("mx_verified", sa.Boolean(), server_default=sa.false()),
        sa.Column("spf_verified", sa.Boolean(), server_default=sa.false()),
        sa.Column("dkim_verified", sa.Boolean(), server_default=sa.false()),
        sa.Column("dmarc_verified", sa.Boolean(), server_default=sa.false()),
        sa.Column("dkim_selector", sa.String(100), server_default="champmail"),
        sa.Column("dkim_private_key", sa.Text()),
        sa.Column("dkim_public_key", sa.Text()),
        sa.Column("daily_send_limit", sa.Integer(), server_default="50"),
        sa.Column("sent_today", sa.Integer(), server_default="0"),
        sa.Column("warmup_enabled", sa.Boolean(), server_default=sa.true()),
        sa.Column("warmup_day", sa.Integer(), server_default="0"),
        sa.Column("sending_ip", sa.String(45)),
        sa.Column("namecheap_domain_id", sa.String(255)),
        sa.Column("cloudflare_zone_id", sa.String(255)),
        # 019: which provider owns this domain's mailboxes.
        sa.Column("infra_provider", sa.String(32), nullable=False,
                     server_default="inboxkit"),
        sa.Column("inboxkit_domain_uid", sa.String(255)),
        sa.Column("inboxkit_workspace_uid", sa.String(255)),
        sa.Column("inboxkit_native_status", sa.String(64)),
        sa.Column("health_score", sa.Float(), server_default="100"),
        sa.Column("bounce_rate", sa.Float(), server_default="0"),
        sa.Column("complaint_rate", sa.Float(), server_default="0"),
        sa.Column("last_health_check", sa.DateTime()),
        sa.Column("blacklisted", sa.Boolean(), server_default=sa.false()),
        sa.Column("blacklist_hits", sa.Integer(), server_default="0"),
        sa.Column("paused", sa.Boolean(), server_default=sa.false()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )
    op.create_index("ix_domains_domain_name", "domains", ["domain_name"], unique=True)
    op.create_index("ix_domains_inboxkit_domain_uid", "domains", ["inboxkit_domain_uid"])

    op.create_table(
        "email_accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        # v2 FK'd this to users.id; v3 has no users table, so no constraint.
        sa.Column("user_id", sa.Uuid()),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
        sa.Column("smtp_host", sa.String(255)),
        sa.Column("smtp_port", sa.Integer(), server_default="587"),
        sa.Column("smtp_username", sa.String(255)),
        sa.Column("smtp_password_encrypted", sa.Text()),
        sa.Column("smtp_use_tls", sa.Boolean(), server_default=sa.true()),
        sa.Column("smtp_verified", sa.Boolean(), server_default=sa.false()),
        sa.Column("smtp_verified_at", sa.DateTime()),
        sa.Column("imap_host", sa.String(255)),
        sa.Column("imap_port", sa.Integer(), server_default="993"),
        sa.Column("imap_username", sa.String(255)),
        sa.Column("imap_password_encrypted", sa.Text()),
        sa.Column("imap_use_ssl", sa.Boolean(), server_default=sa.true()),
        sa.Column("imap_mailbox", sa.String(255), server_default="INBOX"),
        sa.Column("imap_verified", sa.Boolean(), server_default=sa.false()),
        sa.Column("imap_verified_at", sa.DateTime()),
        sa.Column("from_email", sa.String(255)),
        sa.Column("from_name", sa.String(255)),
        sa.Column("reply_to_email", sa.String(255)),
        # 019: InboxKit IAL linkage.
        sa.Column("inboxkit_uid", sa.String(255)),
        sa.Column("inboxkit_workspace_uid", sa.String(255)),
        sa.Column("platform", sa.String(32)),
        sa.Column("credentials_persisted", sa.Boolean(),
                     server_default=sa.false()),
        # 020: owning domain.
        sa.Column("domain_id", sa.Uuid(), sa.ForeignKey("domains.id")),
        # 021: per-mailbox send accounting.
        sa.Column("daily_send_limit", sa.Integer(), nullable=False,
                     server_default="30"),
        sa.Column("sent_today", sa.Integer(), nullable=False,
                     server_default="0"),
        sa.Column("sent_today_date", sa.Date()),
        sa.Column("last_send_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )
    op.create_index("ix_email_accounts_user_id", "email_accounts", ["user_id"])
    op.create_index("ix_email_accounts_inboxkit_uid", "email_accounts", ["inboxkit_uid"])
    op.create_index("ix_email_accounts_domain_id", "email_accounts", ["domain_id"])
    # Rotation reads (domain_id, under-cap, least-recently-used) on every send.
    op.create_index("ix_email_accounts_rotation", "email_accounts",
                    ["domain_id", sa.text("last_send_at NULLS FIRST")])


def downgrade() -> None:
    op.drop_table("email_accounts")
    op.drop_table("domains")