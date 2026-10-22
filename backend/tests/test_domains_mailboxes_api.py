"""Domains/mailboxes API against a mocked InboxKit (respx) and a sqlite stand-in for Postgres."""
import asyncio
import hashlib
import json
from datetime import datetime, timezone

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.db.postgres as pg
from app.api.v1 import inboxkit_webhooks as wh
from app.api.v1.deps import get_session
from app.main import app
from app.models.email_account import EmailAccount

IK = "https://api.inboxkit.com/v1/api"
MAILBOXES = {
    "mb_1": {"uid": "mb_1", "email": "alex@acme-mail.com", "status": "active", "platform": "google",
             "domain_id": "dom_1", "domain_name": "acme-mail.com"},
    "mb_2": {"uid": "mb_2", "email": "sam@acme-mail.com", "status": "active", "platform": "google",
             "domain_id": "dom_1", "domain_name": "acme-mail.com"},
}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAIL_ENCRYPTION_KEY", "test-key")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def create():
        async with engine.begin() as c:
            await c.run_sync(pg.Base.metadata.create_all)
    asyncio.run(create())

    async def session():
        async with maker() as s:
            yield s
    app.dependency_overrides[get_session] = session
    monkeypatch.setattr(pg, "async_session_maker", maker)  # the webhook imports it at call time

    async def no_redis(*_):
        return False
    monkeypatch.setattr(wh, "_already_seen", no_redis)
    monkeypatch.setattr(wh, "_mark_seen", no_redis)
    with TestClient(app) as c:
        c.maker = maker
        yield c
    app.dependency_overrides.clear()


def mock_inboxkit(mock, order_domains=None):
    order = mock.post(f"{IK}/orders").mock(return_value=httpx.Response(
        200, json={"uid": "ord_1", "status": "queued",
                   "domains": order_domains if order_domains is not None else [{"uid": "dom_1", "name": "acme-mail.com"}]}))

    def status(request):
        uids = json.loads(request.content)["uids"]
        return httpx.Response(200, json={"mailboxes": [MAILBOXES[u] for u in uids]})
    mock.post(f"{IK}/mailboxes/status").mock(side_effect=status)
    mock.get(f"{IK}/mailboxes/show-credentials").mock(return_value=httpx.Response(200, json={"password": "pw", "app_password": "app pw"}))
    return order


def webhook(c, event, data):
    return c.post("/api/v1/webhooks/inboxkit", content=json.dumps({
        "event": event, "timestamp": datetime.now(timezone.utc).isoformat(), "data": data}),
        headers={"X-InboxKit-Signature": "sha256=" + hashlib.sha256(b"test-key").hexdigest()})


def order_domain(c, **kw):
    body = {"domain": "acme-mail.com", "brand_id": "brand_1", "mailbox_count": 2, "usernames": ["alex", "sam"], **kw}
    return c.post("/api/v1/domains", json=body)


def import_mailboxes(c):
    for uid in MAILBOXES:
        assert webhook(c, "mailbox.status_changed", {"mailbox": {"uid": uid, "status": "active"}}).json()["result"]["status"] == "updated"


def test_order_then_webhook_imports_two_mailboxes_and_gets_match_harbinger_types(api):
    with respx.mock(assert_all_called=False) as mock:
        order = mock_inboxkit(mock)
        r = order_domain(api)
        assert r.status_code == 201, r.text
        sent = json.loads(order.calls.last.request.content)["domains"][0]
        assert sent["name"] == "acme-mail.com"
        assert [m["username"] for m in sent["mailboxes"]] == ["alex", "sam"]
        import_mailboxes(api)

    assert r.json()["order_uid"] == "ord_1" and r.json()["tracking_subdomain"] == "track.acme-mail.com"
    domains = api.get("/api/v1/domains").json()
    assert len(domains) == 1
    d = domains[0]
    # Harbinger DomainStatus, field for field, plus the health/accounting extras.
    assert d["domain"] == "acme-mail.com" and isinstance(d["status"], str)
    assert all(isinstance(d[k], bool) for k in ("spfVerified", "dkimVerified", "dmarcVerified", "healthy"))
    assert d["healthy"] is False and isinstance(d["reason"], str)  # DNS flags unverified: honest, not healthy
    assert d["dnsbl_listed"] is False and d["complaint_rate"] == 0 and d["hard_bounce_rate"] == 0
    assert d["sends_today"] == 0 and d["cap"] == 60 and d["brand_id"] == "brand_1"

    boxes = api.get("/api/v1/mailboxes", params={"domain": "acme-mail.com"}).json()
    assert sorted(b["email"] for b in boxes) == ["alex@acme-mail.com", "sam@acme-mail.com"]
    b = boxes[0]  # Harbinger MailboxStatus {email, status}
    assert b["status"] == "active" and b["domain"] == "acme-mail.com"
    assert b["cap"] == 30 and b["sends_today"] == 0 and b["dnsbl_listed"] is False
    assert b["complaint_rate"] is None and b["hard_bounce_rate"] is None
    assert api.get("/api/v1/mailboxes", params={"domain": "other.com"}).json() == []


def test_status_patches_persist_and_cascade(api):
    with respx.mock(assert_all_called=False) as mock:
        mock_inboxkit(mock)
        domain_id = order_domain(api).json()["id"]
        import_mailboxes(api)
    boxes = api.get("/api/v1/mailboxes").json()

    assert api.patch(f"/api/v1/mailboxes/{boxes[0]['id']}", json={"status": "paused"}).status_code == 422  # reason required
    r = api.patch(f"/api/v1/mailboxes/{boxes[0]['id']}", json={"status": "paused", "reason": "complaint spike"})
    assert r.json()["status"] == "paused" and r.json()["status_reason"] == "complaint spike"

    async def stored():
        async with api.maker() as s:
            return {m.email: m.status for m in (await s.execute(select(EmailAccount))).scalars()}
    assert asyncio.run(stored())[boxes[0]["email"]] == "paused"  # the column the send path reads

    # Domain pause holds the still-active mailbox, leaves the individually paused one's reason alone.
    r = api.patch(f"/api/v1/domains/{domain_id}", json={"status": "paused", "reason": "dnsbl"})
    assert r.json()["send_status"] == "paused" and r.json()["healthy"] is False
    assert {b["status"] for b in api.get("/api/v1/mailboxes").json()} == {"paused"}

    # Mailbox imported later onto the paused domain must not start sending.
    with respx.mock(assert_all_called=False) as mock:
        mock_inboxkit(mock)
        MAILBOXES["mb_3"] = {**MAILBOXES["mb_1"], "uid": "mb_3", "email": "jo@acme-mail.com"}
        try:
            webhook(api, "mailbox.status_changed", {"mailbox": {"uid": "mb_3", "status": "active"}})
        finally:
            del MAILBOXES["mb_3"]
    assert {b["email"]: b["status"] for b in api.get("/api/v1/mailboxes").json()}["jo@acme-mail.com"] == "paused"

    # Re-activating releases what the domain held, not the mailbox paused for its own reason.
    api.patch(f"/api/v1/domains/{domain_id}", json={"status": "active"})
    st = {b["email"]: b["status"] for b in api.get("/api/v1/mailboxes").json()}
    assert st["jo@acme-mail.com"] == "active" and st[boxes[0]["email"]] == "paused"

    assert api.patch(f"/api/v1/domains/{domain_id}", json={"status": "retired", "reason": "burned"}).status_code == 200
    assert api.patch(f"/api/v1/domains/{domain_id}", json={"status": "active"}).status_code == 409  # terminal
    assert api.patch("/api/v1/domains/not-a-uuid", json={"status": "active"}).status_code == 404


def test_failed_order_leaves_no_row_and_duplicates_conflict(api):
    with respx.mock(assert_all_called=False) as mock:
        mock.post(f"{IK}/orders").mock(return_value=httpx.Response(400, json={"error": True, "message": "no"}))
        assert order_domain(api).status_code == 502
        assert api.get("/api/v1/domains").json() == []
    with respx.mock(assert_all_called=False) as mock:
        mock_inboxkit(mock, order_domains=[])  # no domain uid in the order: webhook adopts the row by name
        assert order_domain(api).status_code == 201
        assert order_domain(api).status_code == 409
        webhook(api, "domain.status_changed", {"domain": {"uid": "dom_9", "status": "active"}})
    assert order_domain(api, domain="not a domain").status_code == 422
    assert order_domain(api, usernames=["only-one"]).status_code == 422


def test_api_key_enforced_when_configured(api, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "champmail_api_key", "k")
    assert api.get("/api/v1/domains").status_code == 401
    assert api.get("/api/v1/domains", headers={"X-API-Key": "k"}).status_code == 200
