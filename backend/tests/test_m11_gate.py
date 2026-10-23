"""M1.1 gate, live: canary sends on a paused domain, seed registry, cap-only PATCH. Real Postgres + Redis + Mailpit.

Runs inside the api container after the M1 gate: M1_GATE=1 pytest tests/test_m11_gate.py -s
Counts Mailpit deltas only (never wipes it). Tests share state and must run in file order.
"""
import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient

if os.environ.get("M1_GATE") != "1":
    pytest.skip("live-stack gate, set M1_GATE=1", allow_module_level=True)

from tests.test_m1_gate import KEY, MAILPIT, RUN, mailpit_count, mb, onboard, sql, unthrottle  # noqa: E402

C = f"canary-{RUN}.com"
SEED = f"seed-{RUN}@gmail.com"
S = {}


@pytest.fixture(scope="module")
def api():
    from app.main import app
    with TestClient(app) as c:
        yield c


def send(c, **kw):
    body = {"to": SEED, "subject": "gate", "html_body": "<p>hi</p>", "text_body": "hi", "brand_id": f"brand_{RUN}", **kw}
    return c.post("/api/v1/send", headers=KEY, json=body)


def canary(c, **kw):
    return send(c, canary=True, headers={"X-Sledgehammer-Canary": f"run-{RUN}"}, **kw)


def test_h1_paused_domain_refuses_normal_send_and_accepts_canary_to_a_seed(api):
    onboard(api, C, ["alex", "sam"])
    S["dom"] = sql("SELECT id::text FROM domains WHERE domain_name=:d", d=C)[0][0]
    r = api.post("/api/v1/seeds", headers=KEY, json={"address": SEED, "provider": "gmail"})
    print("POST /api/v1/seeds ->", r.status_code, r.text)
    assert r.status_code == 201
    print("GET /api/v1/seeds ->", api.get("/api/v1/seeds", headers=KEY).json())
    assert api.patch(f"/api/v1/domains/{S['dom']}", headers=KEY, json={"status": "paused", "reason": "gate"}).status_code == 200
    unthrottle()
    before = mailpit_count()
    r = send(api)
    print("normal send, paused domain ->", r.status_code, r.text)
    assert r.status_code == 409 and r.json()["code"] == "domain_paused" and mailpit_count() == before
    r = canary(api)
    print("canary to seed, paused domain ->", r.status_code, r.text)
    assert r.status_code == 200 and mailpit_count() == before + 1
    mid = httpx.get(f"{MAILPIT}/messages").json()["messages"][0]["ID"]
    h = httpx.get(f"{MAILPIT}/message/{mid}/headers").json()
    print("Mailpit X-Sledgehammer-Canary ->", h.get("X-Sledgehammer-Canary"))
    assert h["X-Sledgehammer-Canary"] == [f"run-{RUN}"]
    assert sql("SELECT canary FROM send_dispatches WHERE message_id=:m", m=r.json()["message_id"]) == [(True,)]


def test_h2_canary_to_an_unregistered_address_is_422_and_nothing_goes_out(api):
    before = mailpit_count()
    r = canary(api, to=f"stranger-{RUN}@corp.com")
    print("canary to non-seed ->", r.status_code, r.text)
    assert r.status_code == 422 and mailpit_count() == before


def test_h3_seventh_canary_is_429_and_campaign_cap_unchanged(api):
    before = mailpit_count()
    codes = [canary(api).status_code for _ in range(5)]  # the first canary was h1
    r = canary(api)
    print("canaries 2..6 ->", codes, "| 7th ->", r.status_code, r.text)
    assert codes == [200] * 5 and r.status_code == 429 and r.json()["code"] == "canary_cap"
    assert mailpit_count() == before + 5
    boxes = sql("SELECT sent_today, daily_send_limit FROM email_accounts WHERE email LIKE :p", p=f"%@{C}")
    print("mailbox sent_today / cap after 6 canaries ->", boxes)
    assert all(sent == 0 for sent, _ in boxes)
    assert sql("SELECT canary_sends_today FROM domains WHERE domain_name=:d", d=C) == [(6,)]


def test_h4_cap_only_patch_changes_cap_and_not_status(api):
    box = mb(f"alex@{C}")[0]
    assert api.patch(f"/api/v1/mailboxes/{box}", headers=KEY, json={"status": "paused", "reason": "gate"}).status_code == 200
    r = api.patch(f"/api/v1/mailboxes/{box}", headers=KEY, json={"cap": 7})
    print("PATCH {cap:7} ->", r.status_code, json.dumps(r.json()))
    assert r.status_code == 200 and r.json()["cap"] == 7 and r.json()["status"] == "paused"
    assert sql("SELECT daily_send_limit, status FROM email_accounts WHERE id=CAST(:i AS uuid)", i=box) == [(7, "paused")]
    assert api.patch(f"/api/v1/mailboxes/{box}", headers=KEY, json={"cap": 201}).status_code == 422
    assert api.patch(f"/api/v1/mailboxes/{box}", headers=KEY, json={"status": "active"}).status_code == 200


def test_h5_retired_domain_canary_is_409(api):
    assert api.patch(f"/api/v1/domains/{S['dom']}", headers=KEY, json={"status": "retired", "reason": "gate"}).status_code == 200
    sql("UPDATE domains SET canary_sends_today=0 WHERE domain_name=:d", d=C)
    before = mailpit_count()
    r = canary(api)
    print("canary, retired domain ->", r.status_code, r.text)
    assert r.status_code == 409 and r.json()["code"] == "domain_retired" and mailpit_count() == before
