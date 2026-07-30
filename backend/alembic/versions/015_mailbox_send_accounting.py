"""Per-mailbox send accounting and daily cap

Revision ID: 015_mailbox_send_accounting
Revises: 014_email_account_domain_link
Create Date: 2026-07-30

The daily send cap lived only on `domains` (daily_send_limit / sent_today) and
was never incremented on the production send path — `increment_sent_count` was
called from app/tasks/warmup.py and nowhere else, so `sent_today` stayed 0
forever, domain_rotation always computed 0/50 utilisation, the cap never
tripped, and every send piled onto whichever domain sorted first. That is the
exact failure domain rotation exists to prevent.

It is also the wrong entity. Deliverability is governed per MAILBOX, not per
domain: InboxKit puts N mailboxes on one domain, so a domain-level 50/day both
under-uses the paid capacity and lets a single mailbox absorb all of it.

This moves the cap to where it belongs and adds the columns needed to rotate
fairly:

- daily_send_limit  — per-mailbox ceiling. Default 25, the safe cold-outreach
                      figure (Google's 2,000/day is a technical limit, not a
                      deliverability one).
- sent_today        — counter.
- sent_today_date   — the date `sent_today` refers to. Lets the reset be
                      self-healing: a stale date means "treat as 0" without
                      depending on a cron having run. A missed beat schedule
                      therefore cannot silently freeze a mailbox at its cap.
- last_send_at      — least-recently-used ordering, so rotation spreads volume
                      instead of draining one mailbox before touching the next.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "015_mailbox_send_accounting"
down_revision: Union[str, None] = "014_email_account_domain_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE email_accounts "
        "ADD COLUMN IF NOT EXISTS daily_send_limit INTEGER NOT NULL DEFAULT 25"
    )
    op.execute(
        "ALTER TABLE email_accounts "
        "ADD COLUMN IF NOT EXISTS sent_today INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE email_accounts ADD COLUMN IF NOT EXISTS sent_today_date DATE"
    )
    op.execute(
        "ALTER TABLE email_accounts ADD COLUMN IF NOT EXISTS last_send_at TIMESTAMP"
    )
    # Rotation reads (domain_id, under-cap, least-recently-used) on every send,
    # so it gets a covering index rather than a sequential scan per email.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_email_accounts_rotation "
        "ON email_accounts (domain_id, last_send_at NULLS FIRST)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_email_accounts_rotation")
    for col in ("last_send_at", "sent_today_date", "sent_today", "daily_send_limit"):
        op.execute(f"ALTER TABLE email_accounts DROP COLUMN IF EXISTS {col}")
