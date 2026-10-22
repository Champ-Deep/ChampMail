"""Migration 0007 on an empty database: upgrade, models match the migrated schema, constraints bite, round trip."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

import app.models  # noqa: F401  (registers tables on Base.metadata)
from app.db.postgres import Base

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")
BACKEND = Path(__file__).resolve().parent.parent


def alembic(*args):
    p = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env={**os.environ, "DATABASE_URL": URL},
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


def test_0007_outbound_events_schema_constraints_and_round_trip():
    engine = create_engine(URL)
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    alembic("upgrade", "head")
    with engine.connect() as c:
        drift = [d for d in compare_metadata(MigrationContext.configure(c), Base.metadata)
                 if "ix_email_accounts_rotation" not in repr(d)]
        assert drift == []
        insp = inspect(c)
        assert {tuple(u["column_names"]) for u in insp.get_unique_constraints("outbound_events")} == {("message_id", "event_type")}
        assert [f["referred_table"] for f in insp.get_foreign_keys("outbound_events")] == ["send_dispatches"]
    with engine.begin() as c:  # a real dispatch to hang rows on
        c.execute(text("INSERT INTO domains (id, domain_name, send_status) VALUES (gen_random_uuid(), 'd.test', 'active')"))
        c.execute(text("INSERT INTO email_accounts (id, name, email, daily_send_limit, sent_today, status, domain_id) "
                       "SELECT gen_random_uuid(), 'm', 'm@d.test', 30, 0, 'active', id FROM domains"))
        c.execute(text("INSERT INTO send_dispatches (id, message_id, domain_id, mailbox_id, payload_hash, status, created_at, updated_at) "
                       "SELECT gen_random_uuid(), 'm1@d.test', d.id, e.id, 'h', 'sent', now(), now() FROM domains d, email_accounts e"))
    row = "INSERT INTO outbound_events (id,message_id,event_type,event_at,status,attempts,next_attempt_at,created_at,updated_at) " \
          "VALUES (gen_random_uuid(),:m,:t,now(),:s,0,now(),now(),now())"
    ok = {"m": "m1@d.test", "t": "opened", "s": "pending"}
    with engine.begin() as c:
        c.execute(text(row), ok)
    for bad in (ok, {**ok, "m": "ghost@d.test"}, {**ok, "t": "exploded"}, {**ok, "t": "clicked", "s": "weird"}):
        with pytest.raises(IntegrityError), engine.begin() as c:  # duplicate, unknown dispatch, bad enum, bad status
            c.execute(text(row), bad)
    alembic("downgrade", "0006")
    alembic("upgrade", "head")
    engine.dispose()
