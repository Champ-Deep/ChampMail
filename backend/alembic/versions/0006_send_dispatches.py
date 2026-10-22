"""send_dispatches: durable send identity and idempotency; unique provider mailbox identity

Revision ID: 0006
Revises: 0005

send_dispatches.message_id/domain_id/mailbox_id are NOT NULL: the row is created in the same
transaction as the mailbox claim. idempotency_key is NULL for keyless requests (unique among
non-NULLs). email_accounts.inboxkit_uid becomes unique so webhook imports are a true upsert.
Fails loudly if duplicate inboxkit_uid rows already exist; resolve them by hand, never auto-merge.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "send_dispatches",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("message_id", sa.String(998), nullable=False),
        sa.Column("domain_id", sa.Uuid(), sa.ForeignKey("domains.id"), nullable=False),
        sa.Column("mailbox_id", sa.Uuid(), sa.ForeignKey("email_accounts.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(255)),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("response", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("message_id", name="uq_send_dispatches_message_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_send_dispatches_idempotency_key"),
    )
    op.create_index("ix_send_dispatches_mailbox_id", "send_dispatches", ["mailbox_id"])
    op.drop_index("ix_email_accounts_inboxkit_uid", table_name="email_accounts")
    op.create_index("ix_email_accounts_inboxkit_uid", "email_accounts", ["inboxkit_uid"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_email_accounts_inboxkit_uid", table_name="email_accounts")
    op.create_index("ix_email_accounts_inboxkit_uid", "email_accounts", ["inboxkit_uid"])
    op.drop_table("send_dispatches")
