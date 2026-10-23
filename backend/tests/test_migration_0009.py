"""Migration 0009 on a database already at 0008 with data: new tables, seeded DNSBL zones, dns_status, round trip."""
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


def test_0009_seeds_three_zones_keeps_existing_domains_and_round_trips():
    engine = create_engine(URL)
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    alembic("upgrade", "0008")
    with engine.begin() as c:
        c.execute(text("INSERT INTO domains (id, domain_name, send_status) VALUES (gen_random_uuid(), 'd.test', 'active')"))
    alembic("upgrade", "head")
    with engine.connect() as c:
        drift = [d for d in compare_metadata(MigrationContext.configure(c), Base.metadata)
                 if "ix_email_accounts_rotation" not in repr(d)]
        assert drift == []
        assert c.execute(text("SELECT name, zone, kind, enabled FROM dnsbl_zones ORDER BY name")).all() == [
            ("barracuda", "b.barracudacentral.org", "ip", True),
            ("spamhaus_zen", "zen.spamhaus.org", "ip", True),
            ("surbl", "multi.surbl.org", "domain", True),
        ]
        assert c.execute(text("SELECT dns_status FROM domains")).scalar_one() is None
        assert {tuple(u["column_names"]) for u in inspect(c).get_unique_constraints("domain_health_daily")} == {("domain_id", "day")}
    with engine.begin() as c, pytest.raises(IntegrityError):
        c.execute(text("INSERT INTO dnsbl_zones (id, name, zone, kind, enabled) VALUES (gen_random_uuid(), 'x', 'x.test', 'url', true)"))
    alembic("downgrade", "0008")
    alembic("upgrade", "head")
    engine.dispose()
