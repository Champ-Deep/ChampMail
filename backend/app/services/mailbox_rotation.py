"""Per-mailbox selection and send accounting.

Why this exists
---------------
`_send_via_inboxkit` used to pick its mailbox with:

    select(EmailAccount).where(...).limit(1)

with no ORDER BY. Postgres is free to return rows in any order, and in practice
returns them stably — so "the first Ready mailbox on the domain" meant *the same
mailbox every time*. Provision three mailboxes and exactly one of them sends,
which is both a waste of the per-mailbox fee and the fastest way to burn a
single sender's reputation while the other two sit idle.

Combined with `sent_today` never being incremented on the production send path
(see migration 015), nothing anywhere enforced a ceiling either.

This module owns both halves:

- `select_mailbox()` — least-recently-used ordering among mailboxes that are
  under their daily cap, so volume spreads evenly.
- `record_send()`    — increments the mailbox counter *and* the domain counter,
  which is what makes `domain_rotation`'s utilisation maths real.

Daily reset is date-based rather than cron-based: a `sent_today_date` that isn't
today is treated as zero. A missed Celery beat schedule therefore cannot freeze
a mailbox at its cap — the worst case is a stale row, not a stalled sender.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, case, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_account import EmailAccount

logger = logging.getLogger(__name__)


class NoMailboxAvailable(RuntimeError):
    """No mailbox on the domain is both ready and under its daily cap.

    Raised rather than returning None so a caller cannot accidentally treat
    "everything is at its limit" as "send anyway" — that distinction is the
    whole point of having a cap.
    """


def _effective_sent_today(account: EmailAccount, today: date) -> int:
    """`sent_today`, or 0 if the counter belongs to an earlier day."""
    if account.sent_today_date != today:
        return 0
    return account.sent_today or 0


class MailboxRotator:
    """Chooses which InboxKit mailbox sends the next email on a domain."""

    async def select_mailbox(
        self,
        session: AsyncSession,
        domain_id: Any,
        *,
        today: Optional[date] = None,
    ) -> EmailAccount:
        """Return the least-recently-used ready mailbox under its daily cap.

        Ordering is `last_send_at NULLS FIRST` so a freshly provisioned mailbox
        (which has never sent) is preferred — that warms new capacity into
        rotation instead of leaving it permanently behind whichever mailbox was
        created first.
        """
        today = today or date.today()

        # The cap comparison has to account for a stale counter, so it is
        # expressed in SQL rather than filtered in Python — otherwise a domain
        # with many mailboxes would load them all on every send.
        effective_sent = case(
            (EmailAccount.sent_today_date == today, EmailAccount.sent_today),
            else_=0,
        )

        stmt = (
            select(EmailAccount)
            .where(
                EmailAccount.domain_id == domain_id,
                EmailAccount.inboxkit_uid.isnot(None),
                EmailAccount.is_active.is_(True),
                EmailAccount.credentials_persisted.is_(True),
                effective_sent < EmailAccount.daily_send_limit,
            )
            .order_by(EmailAccount.last_send_at.nulls_first())
            .limit(1)
        )
        result = await session.execute(stmt)
        mailbox = result.scalar_one_or_none()

        if mailbox is None:
            # Distinguish "no mailboxes at all" from "all of them are capped",
            # because the operator response is completely different: provision
            # more vs. wait for the daily reset.
            total = await session.execute(
                select(EmailAccount.id).where(
                    EmailAccount.domain_id == domain_id,
                    EmailAccount.inboxkit_uid.isnot(None),
                    EmailAccount.is_active.is_(True),
                    EmailAccount.credentials_persisted.is_(True),
                )
            )
            existing = len(total.scalars().all())
            if existing == 0:
                raise NoMailboxAvailable(
                    f"no ready InboxKit mailbox on domain {domain_id}"
                )
            raise NoMailboxAvailable(
                f"all {existing} mailbox(es) on domain {domain_id} have hit "
                f"their daily send limit"
            )

        return mailbox

    async def record_send(
        self,
        session: AsyncSession,
        mailbox_id: Any,
        *,
        domain_id: Any = None,
        today: Optional[date] = None,
    ) -> None:
        """Count one send against the mailbox and (if given) its domain.

        This is the fix for the accounting gap: without it `sent_today` stays 0,
        every utilisation calculation reads 0%, and no cap anywhere can trip.
        """
        today = today or date.today()
        now = datetime.utcnow()

        # Reset-and-increment in one statement so two concurrent workers cannot
        # both read a stale date and each write 1.
        await session.execute(
            update(EmailAccount)
            .where(EmailAccount.id == mailbox_id)
            .values(
                sent_today=case(
                    (EmailAccount.sent_today_date == today, EmailAccount.sent_today + 1),
                    else_=1,
                ),
                sent_today_date=today,
                last_send_at=now,
                updated_at=now,
            )
        )

        if domain_id is not None:
            # Keep the domain counter truthful too — domain_rotation.py reads it
            # to spread load across domains, one level up from this one.
            from app.services.domain_service import domain_service

            try:
                await domain_service.increment_sent_count(session, domain_id)
            except Exception:
                # ! Never fail a completed send because bookkeeping failed; the
                # ! email has already gone out and cannot be un-sent.
                logger.exception(
                    "record_send: domain counter update failed for %s", domain_id
                )
                return

        await session.commit()


mailbox_rotator = MailboxRotator()
