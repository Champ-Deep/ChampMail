"""The email_account model as v3 lifts it: accounting columns, cap 30, no users FK.

Adapted from the v2 tests/unit/test_mailbox_rotation.py model assertions; the
rotation query tests stayed behind because v3's send path claims a mailbox
atomically instead of select-then-record.
"""
from app.models import EmailAccount


def test_model_has_accounting_column():
    for column in ("daily_send_limit", "sent_today", "sent_today_date", "last_send_at"):
        assert column in EmailAccount.__table__.columns, f"{column} missing from model"


def test_default_daily_limit_is_30():
    """30/day per mailbox. Scaling happens by adding mailboxes, not volume."""
    assert EmailAccount.__table__.columns["daily_send_limit"].default.arg == 30


def test_no_users_foreign_key():
    """v3 has no users table; the legacy FK must not come back."""
    referenced = {fk.column.table.name for fk in EmailAccount.__table__.foreign_keys}
    assert referenced == {"domains"}, f"unexpected FK targets: {referenced}"