"""Operator domain holds survive mailbox activation, with real Postgres, Redis and SMTP."""
import os

import httpx
import pytest
from sqlalchemy import select

from app.api.v1 import deps, send as send_api
from app.config import get_settings
from app.db.redis import RedisClient
from app.main import app
from app.models import EmailAccount, SendDispatch
from tests.test_send import HARBINGER, run, seed
from tests.test_send_mailpit_live import API, SMTP, total

pytestmark = pytest.mark.skipif(not (os.environ.get("TEST_DATABASE_URL") and SMTP and API),
                                reason="needs TEST_DATABASE_URL, TEST_MAILPIT_SMTP and TEST_MAILPIT_API")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(get_settings(), "champmail_api_key", "domain-gate-test-key")
    monkeypatch.setenv("EMAIL_ENCRYPTION_KEY", "test-encryption-key")

    async def exercise(Session, scenario):
        async def session_dep():
            async with Session() as session:
                yield session
        app.dependency_overrides[deps.get_session] = session_dep
        app.dependency_overrides[send_api.get_session] = session_dep
        redis = RedisClient()
        monkeypatch.setattr(send_api, "redis_client", redis)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test",
                                         headers={"X-API-Key": "domain-gate-test-key"}) as c:
                await scenario(c)
        finally:
            app.dependency_overrides.clear()
            await redis.close()
    return exercise


@pytest.mark.parametrize("domain_status", ["paused", "retired"])
@pytest.mark.parametrize("selector", ["named", "pooled"])
def test_domain_hold_survives_mailbox_activation(client, domain_status, selector):
    async def go(Session):
        host, port = SMTP.rsplit(":", 1)
        dom, (mb,) = await seed(Session, box_kw={"smtp_host": host, "smtp_port": int(port),
                                               "smtp_use_tls": False, "imap_host": None})

        async def scenario(c):
            if domain_status == "retired":
                r = await c.patch(f"/api/v1/mailboxes/{mb}", json={"status": "paused", "reason": "independent hold"})
                assert r.status_code == 200
            r = await c.patch(f"/api/v1/domains/{dom}", json={"status": domain_status, "reason": "domain hold"})
            assert r.status_code == 200
            r = await c.patch(f"/api/v1/mailboxes/{mb}", json={"status": "active"})
            assert r.status_code == 200
            assert (r.json()["status"], r.json()["status_reason"]) == (domain_status, "domain hold")
            assert (await c.get("/api/v1/domains")).json()[0]["send_status"] == domain_status
            body = {**HARBINGER, "brand_id": "b1"}
            if selector == "named":
                body["mailbox_id"] = str(mb)
            before = total()
            r = await c.post("/api/v1/send", json=body)
            delta = total() - before
            assert r.status_code == 409, (r.text, delta)
            assert r.json()["code"] == f"domain_{domain_status}"
            assert delta == 0
            async with Session() as s:
                box = await s.get(EmailAccount, mb)
                assert box.sent_today == 0 and box.next_send_at is None
                assert not (await s.execute(select(SendDispatch))).all()
            if domain_status == "retired":
                r = await c.patch(f"/api/v1/domains/{dom}", json={"status": "active"})
                assert r.status_code == 409
        await client(Session, scenario)
    run(go)


@pytest.mark.parametrize("selector", ["named", "pooled"])
def test_domain_resume_releases_only_its_own_mailbox_holds(client, selector):
    async def go(Session):
        host, port = SMTP.rsplit(":", 1)
        dom, (held, ready) = await seed(Session, n=2, box_kw={"smtp_host": host, "smtp_port": int(port),
                                                           "smtp_use_tls": False, "imap_host": None})

        async def scenario(c):
            r = await c.patch(f"/api/v1/mailboxes/{held}", json={"status": "paused", "reason": "independent hold"})
            assert r.status_code == 200
            for status in ("paused", "active"):
                r = await c.patch(f"/api/v1/domains/{dom}", json={"status": status, "reason": "domain hold"})
                assert r.status_code == 200
            boxes = {b["id"]: b for b in (await c.get("/api/v1/mailboxes")).json()}
            assert boxes[str(held)]["status"] == "paused"
            assert boxes[str(held)]["status_reason"] == "independent hold"
            assert boxes[str(ready)]["status"] == "active"
            assert (await c.get("/api/v1/domains")).json()[0]["send_status"] == "active"
            before = total()
            r = await c.post("/api/v1/send", json={**HARBINGER, "mailbox_id": str(held)})
            assert r.status_code == 409 and r.json()["code"] == "mailbox_paused"
            assert total() == before
            body = {**HARBINGER, "brand_id": "b1"}
            if selector == "named":
                body["mailbox_id"] = str(ready)
            r = await c.post("/api/v1/send", json=body)
            assert r.status_code == 200, r.text
            assert total() == before + 1
            async with Session() as s:
                assert (await s.get(EmailAccount, held)).sent_today == 0
                assert (await s.get(EmailAccount, ready)).sent_today == 1
        await client(Session, scenario)
    run(go)


@pytest.mark.parametrize("selector", ["named", "pooled"])
@pytest.mark.parametrize("mailbox_reason", ["policy", "independent hold"])
@pytest.mark.parametrize("pause_during_domain_hold", [False, True])
def test_domain_resume_preserves_independent_pause_with_any_reason(
    client, selector, mailbox_reason, pause_during_domain_hold,
):
    async def go(Session):
        host, port = SMTP.rsplit(":", 1)
        dom, (mb,) = await seed(Session, box_kw={"smtp_host": host, "smtp_port": int(port),
                                               "smtp_use_tls": False, "imap_host": None})

        async def scenario(c):
            if pause_during_domain_hold:
                r = await c.patch(f"/api/v1/domains/{dom}", json={"status": "paused", "reason": "policy"})
                assert r.status_code == 200
            r = await c.patch(f"/api/v1/mailboxes/{mb}", json={"status": "paused", "reason": mailbox_reason})
            assert r.status_code == 200
            for status in ("paused", "active"):
                r = await c.patch(f"/api/v1/domains/{dom}", json={"status": status, "reason": "policy"})
                assert r.status_code == 200
            body = {**HARBINGER, "brand_id": "b1"}
            if selector == "named":
                body["mailbox_id"] = str(mb)
            before = total()
            r = await c.post("/api/v1/send", json=body)
            delta = total() - before
            assert r.status_code == 409, (r.text, delta)
            assert r.json()["code"] == "mailbox_paused" and delta == 0
            box = (await c.get("/api/v1/mailboxes")).json()[0]
            assert (box["status"], box["status_reason"]) == ("paused", mailbox_reason)
            async with Session() as s:
                box = await s.get(EmailAccount, mb)
                assert box.sent_today == 0 and box.next_send_at is None
                assert not (await s.execute(select(SendDispatch))).all()
        await client(Session, scenario)
    run(go)
