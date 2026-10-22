"""Migration 0006 on an empty database: upgrade, models match the migrated schema, downgrade and re-upgrade."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

import app.models  # noqa: F401  (registers tables on Base.metadata)
from app.db.postgres import Base

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")
BACKEND = Path(__file__).resolve().parent.parent


def alembic(*args):
    env = {**os.environ, "DATABASE_URL": URL}
    p = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout


def test_0006_upgrades_cleanly_matches_models_and_round_trips():
    engine = create_engine(URL)
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    alembic("upgrade", "head")
    with engine.connect() as c:
        drift = [d for d in compare_metadata(MigrationContext.configure(c), Base.metadata)
                 if "ix_email_accounts_rotation" not in repr(d)]  # 0002 index the model never declared (pre-existing)
        assert drift == []
        insp = inspect(c)
        cols = {x["name"]: x for x in insp.get_columns("send_dispatches")}
        assert {"message_id", "domain_id", "mailbox_id", "idempotency_key", "payload_hash", "status", "response",
                "created_at", "updated_at"} <= set(cols)
        assert cols["idempotency_key"]["nullable"] and not cols["message_id"]["nullable"]
        uniques = {tuple(u["column_names"]) for u in insp.get_unique_constraints("send_dispatches")}
        assert {("message_id",), ("idempotency_key",)} <= uniques
    alembic("downgrade", "0005")
    alembic("upgrade", "head")
    engine.dispose()
