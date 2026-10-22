"""send path: mailbox status + throttle gate, domain brand + tracking subdomain

Revision ID: 0003
Revises: 0002

email_accounts.status      active | paused | retired. Send path refuses the last two.
email_accounts.next_send_at  earliest time the mailbox may send again (45s floor + jitter).
domains.brand_id           selects mailboxes when a send names a brand.
domains.tracking_subdomain one per sending domain; a send without it is a hard error.
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("email_accounts", sa.Column("status", sa.String(16), nullable=False,
                                              server_default="active"))
    op.add_column("email_accounts", sa.Column("next_send_at", sa.DateTime()))
    op.add_column("domains", sa.Column("brand_id", sa.String(64)))
    op.add_column("domains", sa.Column("tracking_subdomain", sa.String(255)))
    op.create_index("ix_domains_brand_id", "domains", ["brand_id"])


def downgrade() -> None:
    op.drop_index("ix_domains_brand_id", table_name="domains")
    op.drop_column("domains", "tracking_subdomain")
    op.drop_column("domains", "brand_id")
    op.drop_column("email_accounts", "next_send_at")
    op.drop_column("email_accounts", "status")
