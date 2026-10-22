"""POST /api/v1/events: the authenticated input for delivered / replied / complained / unsubscribed."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.api.v1.deps import get_session
from app.config import get_settings
from app.main import app
from app.services import outbound_events as oe
from tests.helpers import Receiver, add_dispatch, outbox
from tests.test_send import run, seed

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(get_settings(), "champmail_api_key", "k3y")
    yield
    app.dependency_overrides.clear()


async def post(Session, body, key="k3y"):
    async def session_dep():
        async with Session() as s:
            yield s
    app.dependency_overrides[get_session] = session_dep
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://api") as c:
        return await c.post("/api/v1/events", json=body, headers={"X-API-Key": key} if key else None)


def iso(**delta):
    return (datetime.now(timezone.utc) + timedelta(**delta)).isoformat()


@pytest.mark.parametrize("event_type", ["delivered", "replied", "complained", "unsubscribed"])
def test_trusted_event_is_queued_once_and_repeat_is_a_duplicate(event_type):
    async def go(Session):
        dom, (mb,) = await seed(Session)
        mid = await add_dispatch(Session, dom, mb)
        body = {"event_type": event_type, "message_id": mid, "timestamp": iso()}
        a, b = await post(Session, body), await post(Session, body)
        return mid, a, b, await outbox(Session)
    mid, a, b, rows = run(go)
    assert (a.status_code, a.json()["status"]) == (200, "queued") and (b.status_code, b.json()["status"]) == (200, "duplicate")
    assert [(r.event_type, r.message_id, r.status) for r in rows] == [(event_type, mid, "pending")]


def test_requires_the_api_key():
    async def go(Session):
        dom, (mb,) = await seed(Session)
        body = {"event_type": "replied", "message_id": await add_dispatch(Session, dom, mb)}
        return [(await post(Session, body, key=k)).status_code for k in (None, "wrong", "")], await outbox(Session)
    assert run(go) == ([401, 401, 401], [])


def test_unknown_message_and_refused_dispatch_are_404_nothing_queued():
    async def go(Session):
        dom, (mb,) = await seed(Session)
        failed = await add_dispatch(Session, dom, mb, status="failed")
        return [(await post(Session, {"event_type": "delivered", "message_id": m})).status_code
                for m in ("ghost@x.test", failed)], await outbox(Session)
    assert run(go) == ([404, 404], [])


@pytest.mark.parametrize("body", [
    {"event_type": "bounced"}, {"event_type": "opened"}, {"event_type": "clicked"},  # own channels only
    {"event_type": "exploded"}, {"event_type": None}, {},
    {"event_type": "delivered", "message_id": ""},
    {"event_type": "delivered", "timestamp": "yesterday-ish"},
    {"event_type": "delivered", "timestamp": iso(hours=1)},
    {"event_type": "delivered", "timestamp": iso(days=-2)},  # before the message existed
])
def test_validation_rejects_without_queueing(body):
    async def go(Session):
        dom, (mb,) = await seed(Session)
        mid = await add_dispatch(Session, dom, mb)
        r = await post(Session, {"message_id": mid, **body})
        return r.status_code, await outbox(Session)
    status, rows = run(go)
    assert status == 422 and rows == []


def test_naive_timestamp_is_utc_header_form_id_accepted_and_event_reaches_the_receiver(monkeypatch):
    rcv = Receiver()
    s = get_settings()
    monkeypatch.setattr(s, "champmail_client_url", rcv.url)
    monkeypatch.setattr(s, "champmail_webhook_secret", "shh")

    async def go(Session):
        dom, (mb,) = await seed(Session)
        mid = await add_dispatch(Session, dom, mb)
        ts = (datetime.now(timezone.utc) - timedelta(seconds=5)).replace(tzinfo=None).isoformat()
        r = await post(Session, {"event_type": "replied", "message_id": f"<{mid}>", "timestamp": ts})
        async with httpx.AsyncClient() as c:
            await oe.drain(Session, c)
        return mid, ts, r
    try:
        mid, ts, r = run(go)
    finally:
        rcv.close()
    assert r.status_code == 200 and r.json()["message_id"] == mid
    (headers, body), = rcv.requests
    assert body == {"event_type": "replied", "message_id": mid, "timestamp": ts + "+00:00"}
    assert headers["x-webhook-secret"] == "shh"
