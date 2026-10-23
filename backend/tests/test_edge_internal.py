"""POST /api/v1/events/internal: the Worker's callback. Shared-secret auth, then the same token, dispatch
and host checks the in-process /o and /c routes make. Unknown or forged input creates no event."""
from __future__ import annotations

import os

import httpx
import pytest

from app.api.v1.deps import get_session
from app.config import get_settings
from app.main import app
from app.services import tracking
from tests.helpers import add_dispatch, outbox
from tests.test_send import run, seed

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")
HOST = "t.example.com"  # the tracking_subdomain tests.test_send.seed gives every domain


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(get_settings(), "internal_events_secret", "edge-s3cret")
    monkeypatch.setattr(get_settings(), "champmail_api_key", "api-k3y")  # the edge secret must work without it
    yield
    app.dependency_overrides.clear()


async def post(Session, body, secret="edge-s3cret"):
    async def session_dep():
        async with Session() as s:
            yield s
    app.dependency_overrides[get_session] = session_dep
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://api") as c:
        return await c.post("/api/v1/events/internal", json=body, headers={"X-Edge-Secret": secret} if secret is not None else None)


async def world(Session):
    dom, (mb,) = await seed(Session)
    return dom, await add_dispatch(Session, dom, mb)


@pytest.mark.parametrize("event_type,kind,url", [("opened", "o", None), ("clicked", "c", "https://dest.example/p"), ("unsubscribed", "u", None)])
def test_valid_token_queues_one_event_and_a_repeat_is_a_duplicate(event_type, kind, url):
    async def go(Session):
        dom, mid = await world(Session)
        body = {"event_type": event_type, "token": tracking.sign(kind, mid, dom, url), "host": HOST, "message_id": mid}
        a, b = await post(Session, body), await post(Session, body)
        return mid, a, b, await outbox(Session)
    mid, a, b, rows = run(go)
    assert (a.status_code, a.json()["status"]) == (200, "queued") and (b.status_code, b.json()["status"]) == (200, "duplicate")
    assert [(r.event_type, r.message_id) for r in rows] == [(event_type, mid)]


@pytest.mark.parametrize("secret", [None, "", "wrong", "api-k3y"])
def test_requires_the_edge_secret_not_the_api_key(secret):
    async def go(Session):
        dom, mid = await world(Session)
        body = {"event_type": "opened", "token": tracking.sign("o", mid, dom), "host": HOST}
        return (await post(Session, body, secret)).status_code, await outbox(Session)
    assert run(go) == (401, [])


def test_blank_configured_secret_refuses_everything(monkeypatch):
    monkeypatch.setattr(get_settings(), "internal_events_secret", "")

    async def go(Session):
        dom, mid = await world(Session)
        body = {"event_type": "opened", "token": tracking.sign("o", mid, dom), "host": HOST}
        return (await post(Session, body, "")).status_code, await outbox(Session)
    assert run(go) == (401, [])


def test_forged_or_wrong_kind_token_is_400_and_creates_nothing():
    async def go(Session):
        dom, mid = await world(Session)
        good_o = tracking.sign("o", mid, dom)
        out = []
        for body in (
            {"event_type": "opened", "token": good_o[:-2] + "xx", "host": HOST},          # forged mac
            {"event_type": "clicked", "token": good_o, "host": HOST},                     # open token used as a click
            {"event_type": "unsubscribed", "token": good_o, "host": HOST},
            {"event_type": "opened", "token": "garbage", "host": HOST},
        ):
            out.append((await post(Session, body)).status_code)
        return out, await outbox(Session)
    assert run(go) == ([400, 400, 400, 400], [])


def test_unknown_message_and_foreign_host_are_404_and_message_id_mismatch_is_422():
    async def go(Session):
        dom, mid = await world(Session)
        ghost = tracking.sign("o", "ghost@fixture.test", dom)
        good = tracking.sign("o", mid, dom)
        out = [
            (await post(Session, {"event_type": "opened", "token": ghost, "host": HOST})).status_code,
            (await post(Session, {"event_type": "opened", "token": good, "host": "track.other.com"})).status_code,
            (await post(Session, {"event_type": "opened", "token": good, "host": HOST, "message_id": "other@x"})).status_code,
        ]
        return out, await outbox(Session)
    assert run(go) == ([404, 404, 422], [])
