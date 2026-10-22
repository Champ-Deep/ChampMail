"""Send path against a real Postgres (the atomic claim is meaningless on a mock).

Set TEST_DATABASE_URL=postgresql+psycopg://user:pw@host:port/db; tests skip without it.
The shared tables are dropped and recreated per test.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

import aiosmtplib
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.v1 import send as send_api
from app.crypto import encrypt_secret
from app.main import app
from app.models import Domain, EmailAccount
from app.db.postgres import Base
from app.services import send as svc

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")


class RedisUp:
    async def ping(self):
        return True


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("EMAIL_ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setattr(send_api, "redis_client", RedisUp())  # Redis gate open; its own tests close it


def run(coro_fn):
    """Run `coro_fn(Session)` on a fresh schema and a fresh NullPool engine (real concurrent connections)."""
    async def main():
        engine = create_async_engine(URL, poolclass=NullPool)
        async with engine.begin() as c:
            await c.run_sync(Base.metadata.drop_all)
            await c.run_sync(Base.metadata.create_all)
        try:
            return await coro_fn(async_sessionmaker(engine, expire_on_commit=False))
        finally:
            await engine.dispose()
    return asyncio.run(main())


async def seed(Session, *, n=1, limit=30, brand="b1", tracking="t.example.com", dom_kw=None, box_kw=None):
    async with Session() as s:
        dom = Domain(**{"id": uuid.uuid4(), "domain_name": f"{uuid.uuid4().hex[:8]}.com", "brand_id": brand,
                        "tracking_subdomain": tracking, "status": "verified", **(dom_kw or {})})
        s.add(dom)
        await s.flush()
        boxes = []
        for i in range(n):
            b = EmailAccount(**{"id": uuid.uuid4(), "name": f"m{i}", "email": f"m{i}@{dom.domain_name}",
                                "domain_id": dom.id, "smtp_host": "smtp.test", "smtp_port": 587, "smtp_use_tls": True,
                                "smtp_password_encrypted": encrypt_secret("pw"), "daily_send_limit": limit,
                                "sent_today": 0, "status": "active", "is_active": True, **(box_kw or {})})
            s.add(b)
            boxes.append(b)
        await s.commit()
        return dom.id, [b.id for b in boxes]


# --- claim --------------------------------------------------------------------

def test_concurrent_claims_never_exceed_cap():
    async def go(Session):
        _, (mb,) = await seed(Session, limit=5)

        async def one():
            async with Session() as s:
                try:
                    await svc.claim_mailbox(s, mailbox_id=mb, gap_s=lambda: -60)
                    return True
                except svc.SendRefused as e:
                    assert e.code == "daily_cap" or e.code == "throttled"
                    return False
        wins = sum(await asyncio.gather(*[one() for _ in range(40)]))
        async with Session() as s:
            row = (await s.execute(select(EmailAccount).where(EmailAccount.id == mb))).scalar_one()
        return wins, row.sent_today
    wins, sent = run(go)
    assert wins == 5 and sent == 5


def test_concurrent_claims_respect_45s_floor():
    async def go(Session):
        _, (mb,) = await seed(Session, limit=30)

        async def one():
            async with Session() as s:
                try:
                    c = await svc.claim_mailbox(s, mailbox_id=mb)
                    return c.mailbox.next_send_at - c.mailbox.last_send_at
                except svc.SendRefused as e:
                    assert e.code == "throttled" and e.retry_after >= 1
        return [g for g in await asyncio.gather(*[one() for _ in range(20)]) if g is not None]
    gaps = run(go)
    assert len(gaps) == 1
    assert timedelta(seconds=45) <= gaps[0] < timedelta(seconds=135)


def test_auto_pick_is_lru_and_fans_out_under_concurrency():
    async def go(Session):
        _, ids = await seed(Session, n=3, limit=30)

        async def one():
            async with Session() as s:
                return (await svc.claim_mailbox(s, brand_id="b1")).mailbox.id
        return ids, await asyncio.gather(*[one() for _ in range(3)])
    ids, got = run(go)
    assert sorted(got) == sorted(ids)  # three claimers, three distinct mailboxes


def test_daily_counter_resets_on_new_day():
    async def go(Session):
        _, (mb,) = await seed(Session, limit=1, box_kw={"sent_today": 1, "sent_today_date": (datetime.now(timezone.utc) - timedelta(days=1)).date()})
        async with Session() as s:
            c = await svc.claim_mailbox(s, mailbox_id=mb)
            return c.mailbox.sent_today
    assert run(go) == 1


@pytest.mark.parametrize("box_kw,dom_kw,code", [
    ({"status": "paused"}, {}, "mailbox_paused"),
    ({"status": "retired"}, {}, "mailbox_retired"),
    ({}, {"paused": True}, "domain_paused"),
    ({}, {"status": "retired"}, "domain_retired"),
    ({}, {"status": "paused"}, "domain_paused"),
    ({}, {"blacklisted": True}, "domain_blacklisted"),
])
def test_paused_or_retired_are_refused_by_id_and_by_brand(box_kw, dom_kw, code):
    async def go(Session):
        _, (mb,) = await seed(Session, box_kw=box_kw, dom_kw=dom_kw)
        out = []
        for kw in ({"mailbox_id": mb}, {"brand_id": "b1"}):
            async with Session() as s:
                with pytest.raises(svc.SendRefused) as e:
                    await svc.claim_mailbox(s, **kw)
                out.append((e.value.status, e.value.code))
        return out
    assert run(go) == [(409, code)] * 2


def test_missing_tracking_subdomain_is_a_hard_error_not_a_fallback():
    async def go(Session):
        _, (mb,) = await seed(Session, tracking=None)
        async with Session() as s:
            with pytest.raises(svc.SendRefused) as e:
                await svc.claim_mailbox(s, brand_id="b1")
            return e.value.status, e.value.code, (await s.execute(select(EmailAccount.sent_today))).scalar_one()
    assert run(go) == (500, "tracking_subdomain_missing", 0)


# --- message ------------------------------------------------------------------

def test_headers_unsubscribe_and_tracking_use_domain_host():
    async def go(Session):
        await seed(Session, tracking="trk.acme.io")
        async with Session() as s:
            return await svc.claim_mailbox(s, brand_id="b1")
    c = run(go)
    kw = dict(to="x@y.com", subject="hi", from_name=None, reply_to=None, track_opens=True, track_clicks=True,
              text_body="t", html_body='<a href="https://example.org/p?a=1&b=2">go</a>')
    msg, mid = svc.build_message(c, unsubscribe_url="https://u.example/unsub/abc", **kw)
    assert msg["List-Unsubscribe"] == "<https://u.example/unsub/abc>"
    assert msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert msg["Message-ID"] == f"<{mid}>"
    html = msg.get_body(("html",)).get_content()
    assert 'href="https://trk.acme.io/c/' in html and "https%3A%2F%2Fexample.org%2Fp%3Fa%3D1%26b%3D2" in html
    assert 'src="https://trk.acme.io/o/' in html
    plain, _ = svc.build_message(c, unsubscribe_url=None, **kw)
    assert plain["List-Unsubscribe"] is None and plain["List-Unsubscribe-Post"] is None


# --- HTTP: contract with champmail.ts -----------------------------------------

def http(Session, sent, *, key="k", headers=None, body=None, monkeypatch=None, smtp_error=None):
    async def fake_send(msg, **kw):
        if smtp_error:
            raise smtp_error
        sent.append((msg, kw))

    async def session_dep():
        async with Session() as s:
            yield s
    app.dependency_overrides[send_api.get_session] = session_dep
    monkeypatch.setattr(svc.aiosmtplib, "send", fake_send)

    async def call():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return await c.post("/api/v1/send", json=body, headers=headers)
    return call()


@pytest.fixture
def api_key(monkeypatch):
    class S:  # minimal stand-in for Settings
        champmail_api_key = "secret"
        champmail_env = "development"
    monkeypatch.setattr(send_api, "get_settings", lambda: S)
    yield
    app.dependency_overrides.clear()


# Exactly the body ChampMailProvider.send builds, plus mailbox/brand selectors.
HARBINGER = {"to": "lead@corp.com", "from_name": "Deep", "subject": "Hi", "html_body": "<p>hi</p>",
             "text_body": "hi", "reply_to": None, "domain_id": None, "track_opens": True, "track_clicks": True}


def test_http_response_shape_and_smtp_credentials(api_key, monkeypatch):
    sent = []

    async def go(Session):
        dom, (mb,) = await seed(Session)
        r = await http(Session, sent, headers={"X-API-Key": "secret"}, monkeypatch=monkeypatch,
                       body={**HARBINGER, "brand_id": "b1", "unsubscribe_url": "https://u.example/x"})
        return dom, mb, r
    dom, mb, r = run(go)
    assert r.status_code == 200, r.text
    j = r.json()
    assert set(j) == {"message_id", "status", "domain_id", "sent_at"}  # ChampMailSendResponse
    assert j["status"] == "sent" and j["domain_id"] == str(dom)
    datetime.fromisoformat(j["sent_at"])
    msg, kw = sent[0]
    assert kw["hostname"] == "smtp.test" and kw["password"] == "pw" and kw["start_tls"] is True
    assert msg["List-Unsubscribe"] == "<https://u.example/x>" and msg["To"] == "lead@corp.com"


@pytest.mark.parametrize("headers,status", [({}, 401), ({"X-API-Key": "nope"}, 401)])
def test_http_auth_required(api_key, monkeypatch, headers, status):
    async def go(Session):
        await seed(Session)
        return await http(Session, [], headers=headers, monkeypatch=monkeypatch, body=HARBINGER)
    assert run(go).status_code == status


def test_http_fails_closed_in_production_without_key(monkeypatch):
    class S:
        champmail_api_key = ""
        champmail_env = "production"
    monkeypatch.setattr(send_api, "get_settings", lambda: S)

    async def go(Session):
        return await http(Session, [], monkeypatch=monkeypatch, body=HARBINGER)
    try:
        assert run(go).status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_http_header_injection_rejected(api_key, monkeypatch):
    async def go(Session):
        await seed(Session)
        return await http(Session, [], headers={"X-API-Key": "secret"}, monkeypatch=monkeypatch,
                          body={**HARBINGER, "subject": "a\r\nBcc: evil@x.com"})
    assert run(go).status_code == 422


def test_http_paused_mailbox_is_refused_and_smtp_not_called(api_key, monkeypatch):
    sent = []

    async def go(Session):
        _, (mb,) = await seed(Session, box_kw={"status": "paused"})
        return await http(Session, sent, headers={"X-API-Key": "secret"}, monkeypatch=monkeypatch,
                          body={**HARBINGER, "mailbox_id": str(mb)})
    r = run(go)
    assert r.status_code == 409 and r.json()["code"] == "mailbox_paused" and sent == []


def test_http_throttle_returns_429_with_retry_after_and_smtp_failure_releases_slot(api_key, monkeypatch):
    sent = []

    async def go(Session):
        _, (mb,) = await seed(Session)
        h = {"X-API-Key": "secret"}
        bad = await http(Session, sent, headers=h, monkeypatch=monkeypatch, body={**HARBINGER, "brand_id": "b1"},
                         smtp_error=aiosmtplib.SMTPConnectError("down"))
        async with Session() as s:
            after_fail = (await s.execute(select(EmailAccount.sent_today))).scalar_one()
        # throttle stays as backoff after a failure, so the retry is told to wait
        retry = await http(Session, sent, headers=h, monkeypatch=monkeypatch, body={**HARBINGER, "brand_id": "b1"})
        return bad, after_fail, retry
    bad, after_fail, retry = run(go)
    assert bad.status_code == 502 and after_fail == 0
    assert retry.status_code == 429 and int(retry.headers["retry-after"]) >= 1 and sent == []
