"""M1 gate, live: real Postgres + Redis + Mailpit of the compose stack, InboxKit mocked with respx.

Runs inside the api container (live stack, wipes Mailpit): M1_GATE=1 pytest tests/test_m1_gate.py -s
Skipped otherwise, so the plain suite stays hermetic. Needs EMAIL_ENCRYPTION_KEY from the stack's .env.
Tests share state and must run in file order.
"""
import asyncio
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text


if os.environ.get("M1_GATE") != "1":
    pytest.skip("live-stack gate, set M1_GATE=1", allow_module_level=True)

IK = "https://api.inboxkit.com/v1/api"
MAILPIT = "http://mailpit:8025/api/v1"
RUN = uuid.uuid4().hex[:6]
KEY = {"X-API-Key": os.environ["CHAMPMAIL_API_KEY"]}
db = create_engine(os.environ["DATABASE_URL"])
S = {}  # shared state across ordered tests


def sql(q, **p):
    with db.begin() as c:
        r = c.execute(text(q), p)
        return r.fetchall() if r.returns_rows else None


def mailpit_count():
    return httpx.get(f"{MAILPIT}/messages").json()["total"]


@pytest.fixture(scope="module")
def api():
    from app.main import app
    with TestClient(app) as c:
        yield c


def webhook(c, uid):
    sig = "sha256=" + hashlib.sha256(os.environ["INBOXKIT_API_KEY"].encode()).hexdigest()
    return c.post("/api/v1/webhooks/inboxkit", headers={"X-InboxKit-Signature": sig}, content=json.dumps({
        "event": "mailbox.status_changed", "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": {"mailbox": {"uid": uid, "status": "active"}}}))


def onboard(c, name, users):
    """POST /domains against mocked InboxKit, then simulate one mailbox webhook per mailbox."""
    boxes = {f"mb_{RUN}_{u}": {"uid": f"mb_{RUN}_{u}", "email": f"{u}@{name}", "status": "active", "platform": "google",
                               "domain_id": f"dom_{name}", "domain_name": name} for u in users}
    with respx.mock(assert_all_called=False) as m:
        order = m.post(f"{IK}/orders").mock(return_value=httpx.Response(
            200, json={"uid": f"ord_{name}", "status": "queued", "domains": [{"uid": f"dom_{name}", "name": name}]}))
        m.post(f"{IK}/mailboxes/status").mock(side_effect=lambda req: httpx.Response(
            200, json={"mailboxes": [boxes[u] for u in json.loads(req.content)["uids"]]}))
        m.get(f"{IK}/mailboxes/show-credentials").mock(return_value=httpx.Response(200, json={"password": "pw"}))
        r = c.post("/api/v1/domains", headers=KEY,
                   json={"domain": name, "brand_id": f"brand_{RUN}", "mailbox_count": len(users), "usernames": users})
        assert r.status_code == 201, r.text
        for uid in boxes:
            w = webhook(c, uid)
            assert w.status_code == 200 and w.json()["result"]["status"] == "updated", w.text
        again = webhook(c, next(iter(boxes)))  # same event redelivered
        assert again.json()["result"]["status"] == "duplicate"
    # Point the imported mailbox's SMTP at Mailpit (the only edit to what the webhook imported).
    sql("UPDATE email_accounts SET smtp_host='mailpit', smtp_port=1025, smtp_use_tls=false "
        "WHERE domain_id=(SELECT id FROM domains WHERE domain_name=:d)", d=name)
    return r.json(), json.loads(order.calls.last.request.content)


def mb(email):
    return sql("SELECT id::text, status, sent_today, daily_send_limit FROM email_accounts WHERE email=:e", e=email)[0]


def unthrottle():
    sql("UPDATE email_accounts SET next_send_at=NULL")


def send(c, **kw):
    body = {"to": "lead@example.org", "subject": "gate", "html_body": '<p>hi <a href="https://example.org/x">x</a></p>',
            "text_body": "hi", "unsubscribe_url": "https://unsub.example.org/u/1", **kw}
    return c.post("/api/v1/send", headers=KEY, json=body)


A, B = f"gate-{RUN}.com", f"gate2-{RUN}.com"


def test_g2_domain_order_and_webhook_imports_two_mailboxes(api):
    d, order_body = onboard(api, A, ["alex", "sam"])
    print("POST /api/v1/domains ->", json.dumps(d))
    print("InboxKit order body sent ->", json.dumps(order_body)[:300])
    assert d["order_uid"] == f"ord_{A}" and d["tracking_subdomain"] == f"track.{A}"
    rows = sql("SELECT email, is_active, credentials_persisted, domain_id IS NOT NULL FROM email_accounts "
               "WHERE email LIKE :p ORDER BY email", p=f"%@{A}")
    print("email_accounts ->", rows)
    assert [r[0] for r in rows] == [f"alex@{A}", f"sam@{A}"] and all(r[1] and r[2] and r[3] for r in rows)
    got = api.get("/api/v1/mailboxes", headers=KEY, params={"domain": A}).json()
    assert len(got) == 2


def test_g3_send_delivers_to_mailpit_with_unsubscribe_headers(api):
    assert httpx.delete(f"{MAILPIT}/messages").status_code == 200
    assert mailpit_count() == 0
    unthrottle()
    r = send(api, from_address=f"alex@{A}")
    print("POST /api/v1/send ->", r.status_code, r.text)
    assert r.status_code == 200 and r.json()["message_id"] and r.json()["status"] == "sent"
    assert mailpit_count() == 1
    mid = httpx.get(f"{MAILPIT}/messages").json()["messages"][0]["ID"]
    h = httpx.get(f"{MAILPIT}/message/{mid}/headers").json()
    print("Mailpit headers ->", json.dumps(h, indent=1))
    assert h["List-Unsubscribe"] == ["<https://unsub.example.org/u/1>"]
    assert h["List-Unsubscribe-Post"] == ["List-Unsubscribe=One-Click"]
    assert h["Message-Id"] == [f"<{r.json()['message_id']}>"]
    html = httpx.get(f"{MAILPIT}/message/{mid}").json()["HTML"]
    assert f"https://track.{A}/c/" in html and f"https://track.{A}/o/" in html


def test_g4_cap_one_second_send_refused_then_routed_to_other_mailbox(api):
    sql("UPDATE email_accounts SET daily_send_limit=1 WHERE email=:e", e=f"alex@{A}")
    before = mailpit_count()
    unthrottle()  # isolate the cap from the 45s gap
    r = send(api, from_address=f"alex@{A}")
    print("2nd send, alex cap=1 ->", r.status_code, r.text)
    assert r.status_code == 429 and r.json()["code"] == "daily_cap"
    assert mailpit_count() == before and mb(f"alex@{A}")[2] == 1
    # pooled send for the domain: alex is at cap, so it must land on sam
    unthrottle()
    r = send(api, domain_id=sql("SELECT id::text FROM domains WHERE domain_name=:d", d=A)[0][0])
    print("pooled send ->", r.status_code, r.text)
    assert r.status_code == 200
    assert mailpit_count() == before + 1
    frm = httpx.get(f"{MAILPIT}/messages").json()["messages"][0]["From"]["Address"]
    print("routed to", frm, "| alex", mb(f"alex@{A}"), "| sam", mb(f"sam@{A}"))
    assert frm == f"sam@{A}" and mb(f"alex@{A}")[2] == 1 and mb(f"sam@{A}")[2] == 1


def test_g5_paused_and_retired_are_refused(api):
    before = mailpit_count()
    sam = mb(f"sam@{A}")[0]
    out = {}
    for status in ("paused", "retired"):
        unthrottle()
        sql("UPDATE email_accounts SET status='active', daily_send_limit=30 WHERE email=:e", e=f"sam@{A}")
        assert api.patch(f"/api/v1/mailboxes/{sam}", headers=KEY, json={"status": status, "reason": "gate"}).status_code == 200
        r = send(api, mailbox_id=sam)
        out[f"mailbox {status}"] = (r.status_code, r.json()["code"])
        assert r.status_code == 409 and r.json()["code"] == f"mailbox_{status}"
    # domain level: mailboxes left active, only the domain gate is closed (the path auto-pause takes)
    sql("UPDATE email_accounts SET status='active', daily_send_limit=30")
    dom = sql("SELECT id::text FROM domains WHERE domain_name=:d", d=A)[0][0]
    for col, val, code in (("paused", "true", "domain_paused"), ("paused", "false", None), ("status", "'retired'", "domain_retired")):
        unthrottle()
        sql(f"UPDATE domains SET {col}={val} WHERE domain_name=:d", d=A)
        if code:
            r = send(api, domain_id=dom)
            out[f"domain {col}={val}"] = (r.status_code, r.json()["code"])
            assert r.status_code == 409 and r.json()["code"] == code
    # operator PATCH on the domain cascades and also refuses
    sql("UPDATE domains SET status='verified' WHERE domain_name=:d", d=A)
    sql("UPDATE email_accounts SET status='active'")
    assert api.patch(f"/api/v1/domains/{dom}", headers=KEY, json={"status": "paused", "reason": "gate"}).status_code == 200
    unthrottle()
    r = send(api, domain_id=dom)
    out["PATCH domain paused"] = (r.status_code, r.json()["code"])
    assert r.status_code == 409
    print("refusals ->", json.dumps(out, indent=1))
    assert mailpit_count() == before  # nothing reached SMTP


def test_g6_missing_tracking_subdomain_is_hard_error_no_fallback(api):
    onboard(api, B, ["kim", "lee"])
    before = mailpit_count()
    for v in ("NULL", "''"):
        sql(f"UPDATE domains SET tracking_subdomain={v} WHERE domain_name=:d", d=B)
        unthrottle()
        r = send(api, from_address=f"kim@{B}")
        print(f"tracking_subdomain={v} ->", r.status_code, r.text)
        assert r.status_code == 500 and r.json()["code"] == "tracking_subdomain_missing"
        r = send(api, domain_id=sql("SELECT id::text FROM domains WHERE domain_name=:d", d=B)[0][0])
        assert r.status_code == 500 and r.json()["code"] == "tracking_subdomain_missing"
    assert mailpit_count() == before and mb(f"kim@{B}")[2] == 0  # no mail, no cap slot burned


def _run(coro):
    return asyncio.run(coro)


def test_g7_events_idempotent_and_bounce_hard_vs_soft():
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool
    from app.config import get_settings
    from app.services import outbound_events as oe
    from app.services.bounce_poller import process_dsn
    from tests.test_outbound_events_bounces import dsn

    s = get_settings()
    s.champmail_client_url, s.champmail_webhook_secret = "https://harbinger.test", "shh"
    hard_id, soft_id, ev_id = f"hard-{RUN}@gate.test", f"soft-{RUN}@gate.test", f"ev-{RUN}@gate.test"
    acct = sql("SELECT id FROM email_accounts LIMIT 1")[0][0]
    hard, soft = dsn("5.1.1", orig_id=f"<{hard_id}>"), dsn("4.2.2", action="delayed", orig_id=f"<{soft_id}>")

    async def go():
        r = aioredis.from_url(s.redis_url, decode_responses=True)
        eng = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
        Session = async_sessionmaker(eng, expire_on_commit=False)
        qlen0 = await r.llen(oe.QUEUE)
        out = {}
        out["emit1"] = await oe.emit(r, "delivered", ev_id)
        out["emit2"] = await oe.emit(r, "delivered", ev_id)
        async with Session() as sess:
            out["hard"] = await process_dsn(sess, r, acct, hard)
            out["hard_again"] = await process_dsn(sess, r, acct, hard)
            out["soft"] = await process_dsn(sess, r, acct, soft)
        out["queued"] = await r.llen(oe.QUEUE) - qlen0
        with respx.mock() as m:
            route = m.post("https://harbinger.test/api/email/track").respond(200, json={})
            async with httpx.AsyncClient() as c:
                out["delivered"] = await oe.drain(r, c)
            out["posts"] = [(json.loads(x.request.content), x.request.headers["x-webhook-secret"]) for x in route.calls]
        out["emit3_after_send"] = await oe.emit(r, "delivered", ev_id)
        await r.aclose()
        await eng.dispose()
        return out

    out = _run(go())
    print("events ->", json.dumps(out, indent=1))
    assert (out["emit1"], out["emit2"], out["emit3_after_send"]) == (True, False, False)
    assert out["hard"] == out["hard_again"] == "hard" and out["soft"] == "soft"
    assert out["queued"] == 2  # delivered + ONE bounced (hard re-poll and soft added nothing)
    assert sorted(p[0]["event_type"] for p in out["posts"]) == ["bounced", "delivered"]
    assert {p[0]["message_id"] for p in out["posts"]} == {ev_id, hard_id}
    assert all(p[1] == "shh" for p in out["posts"])
    rows = sql("SELECT kind, status_code, message_id FROM bounces WHERE message_id IN (:h,:s) ORDER BY kind",
               h=hard_id, s=soft_id)
    print("bounces rows ->", rows)
    assert rows == [("hard", "5.1.1", hard_id), ("soft", "4.2.2", soft_id)]
