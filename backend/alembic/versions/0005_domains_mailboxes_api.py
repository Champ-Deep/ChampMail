"""domains/mailboxes API: operator send gate on domains, reasons, order uid

Revision ID: 0005
Revises: 0004

email_accounts.status already exists (0003); this adds its reason, and the
domain-level gate that PATCH /api/v1/domains/{id} sets.
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("domains", sa.Column("send_status", sa.String(16), nullable=False,
                                       server_default="active"))
    op.add_column("domains", sa.Column("send_status_reason", sa.Text()))
    op.add_column("domains", sa.Column("inboxkit_order_uid", sa.String(255)))
    op.add_column("email_accounts", sa.Column("status_reason", sa.Text()))


def downgrade() -> None:
    op.drop_column("email_accounts", "status_reason")
    for col in ("inboxkit_order_uid", "send_status_reason", "send_status"):
        op.drop_column("domains", col)
