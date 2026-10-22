"""Outbound events + DSN bounce poller: idempotency, backoff, hard/soft classification."""
import asyncio
import json

import httpx
import pytest
import respx

from app.config import get_settings
from app.services import outbound_events as oe
from app.services.bounce_poller import parse_dsn, process_dsn

URL = "https://harbinger.test"
TRACK = f"{URL}/api/email/track"


class FakeRedis:
    def __init__(self):
        self.kv, self.lists = {}, {}

    async def set(self, k, v, nx=False):
        if nx and k in self.kv:
            return None
        self.kv[k] = v
        return True

    async def delete(self, k):
        self.kv.pop(k, None)

    async def rpush(self, k, v):
        self.lists.setdefault(k, []).append(v)

    async def lpop(self, k):
        q = self.lists.get(k)
        return q.pop(0) if q else None


class FakeSession:
    def __init__(self):
        self.added = []

    async def execute(self, stmt):
        self.added.append(stmt.compile().params)

    async def commit(self):
        pass

    async def rollback(self):
        pass


@pytest.fixture(autouse=True)
def client_env(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "champmail_client_url", URL)
    monkeypatch.setattr(s, "champmail_webhook_secret", "shh")


def dsn(status: str, action="failed", orig_id="<orig-1@champmail.test>") -> bytes:
    return f"""From: MAILER-DAEMON@mx.test
To: sender@champmail.test
Subject: Delivery Status Notification
MIME-Version: 1.0
Content-Type: multipart/report; report-type=delivery-status; boundary="b"

--b
Content-Type: text/plain

Delivery failed.

--b
Content-Type: message/delivery-status

Reporting-MTA: dns; mx.test

Final-Recipient: rfc822; bob@example.com
Action: {action}
Status: {status}
Diagnostic-Code: smtp; {status.replace('.', ' ')} mailbox problem

--b
Content-Type: text/rfc822-headers

Message-ID: {orig_id}
Subject: hi

--b--
""".encode()


def run(coro):
    return asyncio.run(coro)


def test_classifies_hard_and_soft():
    hard = parse_dsn(dsn("5.1.1"))
    soft = parse_dsn(dsn("4.2.2", action="delayed"))
    assert (hard.kind, hard.status, hard.message_id, hard.recipient) == ("hard", "5.1.1", "orig-1@champmail.test", "bob@example.com")
    assert (soft.kind, soft.status) == ("soft", "4.2.2")
    assert parse_dsn(dsn("2.0.0", action="delivered")) is None


def test_hard_bounce_stored_and_emitted_once():
    r, s = FakeRedis(), FakeSession()
    raw = dsn("5.1.1")
    assert run(process_dsn(s, r, "acc", raw)) == "hard"
    assert run(process_dsn(s, r, "acc", raw)) == "hard"  # re-poll of the same DSN
    assert [b["kind"] for b in s.added] == ["hard", "hard"]  # DB unique constraint dedupes the row
    queued = [json.loads(x) for x in r.lists[oe.QUEUE]]
    assert len(queued) == 1 and queued[0]["event_type"] == "bounced"
    assert queued[0]["message_id"] == "orig-1@champmail.test"


def test_soft_bounce_stored_never_emitted():
    r, s = FakeRedis(), FakeSession()
    assert run(process_dsn(s, r, "acc", dsn("4.2.2", action="delayed"))) == "soft"
    assert [b["kind"] for b in s.added] == ["soft"]
    assert s.added[0]["status_code"] == "4.2.2"
    assert oe.QUEUE not in r.lists


def test_emit_idempotent_per_message_and_type():
    r = FakeRedis()
    assert run(oe.emit(r, "opened", "m1")) is True
    assert run(oe.emit(r, "opened", "m1")) is False
    assert run(oe.emit(r, "clicked", "m1")) is True  # different type is a different event
    assert run(oe.emit(r, "opened", "m2")) is True
    with pytest.raises(ValueError):
        run(oe.emit(r, "exploded", "m1"))


@respx.mock
def test_drain_payload_secret_and_no_double_emit():
    route = respx.post(TRACK).respond(200, json={"updated": 1})
    r = FakeRedis()

    async def go():
        await oe.emit(r, "delivered", "m1")
        await oe.emit(r, "delivered", "m1")
        async with httpx.AsyncClient() as c:
            return await oe.drain(r, c)

    assert run(go()) == 1
    assert route.call_count == 1
    req = route.calls[0].request
    assert req.headers["x-webhook-secret"] == "shh"
    body = json.loads(req.content)
    assert set(body) == {"event_type", "message_id", "timestamp"} and body["event_type"] == "delivered"
    # Emitting again after a successful send is still a no-op.
    assert run(oe.emit(r, "delivered", "m1")) is False


@respx.mock
def test_backoff_retry_on_5xx_then_success():
    route = respx.post(TRACK).mock(side_effect=[httpx.Response(503), httpx.Response(500), httpx.Response(200)])
    r, delays = FakeRedis(), []

    async def fake_sleep(d):
        delays.append(d)

    async def go():
        await oe.emit(r, "bounced", "m1")
        async with httpx.AsyncClient() as c:
            return await oe.drain(r, c, sleep=fake_sleep)

    assert run(go()) == 1
    assert route.call_count == 3
    assert delays == [1.0, 2.0]


@respx.mock
def test_gives_up_to_dead_letter_without_reemit_and_4xx_not_retried():
    r, delays = FakeRedis(), []

    async def fake_sleep(d):
        delays.append(d)

    async def go(status):
        respx.post(TRACK).respond(status)
        await oe.emit(r, "bounced", f"m{status}")
        async with httpx.AsyncClient() as c:
            return await oe.drain(r, c, max_attempts=3, sleep=fake_sleep)

    assert run(go(500)) == 0 and delays == [1.0, 2.0]
    assert len(r.lists[oe.DEAD]) == 1
    delays.clear()
    assert run(go(401)) == 0 and delays == []  # permanent failure, no retry
    assert len(r.lists[oe.DEAD]) == 2
    assert run(oe.emit(r, "bounced", "m500")) is False
