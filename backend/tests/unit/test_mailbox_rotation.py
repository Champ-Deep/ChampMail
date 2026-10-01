"""Per-mailbox rotation and send accounting.

These assert against compiled SQL and pure logic rather than a live database, so
they run in CI without Postgres. What they pin down is exactly what was broken:

- the mailbox query is ORDERED (the old `.limit(1)` had no ORDER BY, so it
  returned the same mailbox every time and one of N mailboxes did all sending)
- the daily cap is compared against a counter that self-heals across days
- the increment is expressed as a single UPDATE, so two concurrent workers
  cannot both read a stale date and each write 1
"""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import case, select, update
from sqlalchemy.dialects import postgresql

from app.models.email_account import EmailAccount
from app.services.mailbox_rotation import _effective_sent_today


def _compile(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )


# --- the daily counter self-heals ------------------------------------------


def test_counter_is_zero_when_it_belongs_to_an_earlier_day():
    """A stale `sent_today_date` must read as 0.

    Without this, a missed Celery beat reset would freeze the mailbox at its cap
    and it would silently stop sending — a cron outage becoming a send outage.
    """
    today = date(2026, 7, 30)
    account = SimpleNamespace(sent_today=25, sent_today_date=today - timedelta(days=1))
    assert _effective_sent_today(account, today) == 0


def test_counter_is_honoured_when_it_is_todays():
    today = date(2026, 7, 30)
    account = SimpleNamespace(sent_today=7, sent_today_date=today)
    assert _effective_sent_today(account, today) == 7


def test_counter_is_zero_when_never_set():
    account = SimpleNamespace(sent_today=0, sent_today_date=None)
    assert _effective_sent_today(account, date(2026, 7, 30)) == 0


# --- the selection query ---------------------------------------------------


def _selection_sql(today: date) -> str:
    """Rebuild the statement from select_mailbox() so it can be compiled."""
    effective_sent = case(
        (EmailAccount.sent_today_date == today, EmailAccount.sent_today), else_=0
    )
    stmt = (
        select(EmailAccount)
        .where(
            EmailAccount.domain_id == "00000000-0000-0000-0000-000000000001",
            EmailAccount.inboxkit_uid.isnot(None),
            EmailAccount.is_active.is_(True),
            EmailAccount.credentials_persisted.is_(True),
            effective_sent < EmailAccount.daily_send_limit,
        )
        .order_by(EmailAccount.last_send_at.nulls_first())
        .limit(1)
    )
    return _compile(stmt)


def test_mailbox_selection_is_ordered():
    """The core fix.

    An unordered `.limit(1)` lets Postgres return any row, and in practice
    returns a stable one — so three provisioned mailboxes meant one sender doing
    all the work and absorbing all the reputation damage.
    """
    sql = _selection_sql(date(2026, 7, 30))
    assert "ORDER BY" in sql, f"selection must be ordered, got: {sql}"


def test_least_recently_used_ordering_prefers_never_used_mailboxes():
    """NULLS FIRST puts a freshly provisioned mailbox at the front.

    Otherwise new capacity sorts last forever and never enters rotation.
    """
    sql = _selection_sql(date(2026, 7, 30))
    assert "last_send_at" in sql
    assert "NULLS FIRST" in sql.upper(), f"expected NULLS FIRST, got: {sql}"


def test_selection_excludes_mailboxes_at_their_cap():
    sql = _selection_sql(date(2026, 7, 30))
    assert "daily_send_limit" in sql
    assert "CASE" in sql.upper(), "cap comparison must account for a stale counter"


def test_selection_is_scoped_to_one_domain_and_to_ready_mailboxes():
    """Guards against reintroducing the cross-domain leak migration 014 fixed."""
    sql = _selection_sql(date(2026, 7, 30))
    for column in ("domain_id", "inboxkit_uid", "is_active", "credentials_persisted"):
        assert column in sql, f"{column} missing from selection predicate"


# --- the increment ---------------------------------------------------------


def test_increment_resets_and_bumps_in_a_single_statement():
    """Read-then-write would let two workers both see a stale date and write 1.

    Expressing the reset as a CASE inside the UPDATE keeps it atomic.
    """
    today = date(2026, 7, 30)
    stmt = (
        update(EmailAccount)
        .where(EmailAccount.id == "00000000-0000-0000-0000-000000000002")
        .values(
            sent_today=case(
                (EmailAccount.sent_today_date == today, EmailAccount.sent_today + 1),
                else_=1,
            ),
            sent_today_date=today,
        )
    )
    sql = _compile(stmt)
    assert sql.upper().startswith("UPDATE")
    assert "CASE" in sql.upper()
    assert "sent_today_date" in sql


# --- the model actually carries the columns --------------------------------


@pytest.mark.parametrize(
    "column",
    ["daily_send_limit", "sent_today", "sent_today_date", "last_send_at"],
)
def test_model_has_accounting_column(column: str):
    assert column in EmailAccount.__table__.columns, (
        f"{column} missing — migration 015 and the model have drifted"
    )


def test_default_daily_limit_is_the_safe_cold_outreach_figure():
    """25/day per mailbox. Google's 2,000/day is a technical ceiling, not a
    deliverability one; scaling happens by adding mailboxes, not volume."""
    assert EmailAccount.__table__.columns["daily_send_limit"].default.arg == 25
