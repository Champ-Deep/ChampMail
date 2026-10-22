"""Durable outbox on real Postgres, delivered to a real TCP HTTP receiver.

Calibrated against the old Redis queue: its audit showed an event claimed (LPOP) and then cancelled
before the POST was gone for good. Here the same fault leaves a leased row that is reclaimed.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, update

from app.config import get_settings
from app.models import OutboundEvent
from app.services import outbound_events as oe
from tests.helpers import Receiver, add_dispatch, outbox
from tests.test_send import run, seed

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")


@pytest.fixture
def receiver(monkeypatch):
    made = []

    def make(**kw):
        r = Receiver(**kw)
        made.append(r)
        s = get_settings()
        monkeypatch.setattr(s, "champmail_client_url", r.url)
        monkeypatch.setattr(s, "champmail_webhook_secret", "shh")
        return r
    yield make
    for r in made:
        r.close()


async def fixture_dispatch(Session, **kw):
    dom, (mb,) = await seed(Session)
    return await add_dispatch(Session, dom, mb, **kw)


async def emit(Session, *a, **kw):
    async with Session() as s:
        out = await oe.emit(s, *a, **kw)
        await s.commit()
        return out


async def drain(Session, **kw):
    async with httpx.AsyncClient(timeout=5) as c:
        return await oe.drain(Session, c, **kw)


def test_emit_is_idempotent_per_message_and_type_and_needs_a_known_dispatch():
    async def go(Session):
        mid = await fixture_dispatch(Session)
        other = await add_dispatch(Session, *(await _ids(Session)))
        first = [await emit(Session, "opened", mid), await emit(Session, "opened", mid)]
        more = [await emit(Session, "clicked", mid), await emit(Session, "opened", other)]
        with pytest.raises(ValueError):
            await emit(Session, "exploded", mid)
        with pytest.raises(oe.UnknownDispatch):
            await emit(Session, "opened", "never-sent@x.test")
        failed = await add_dispatch(Session, *(await _ids(Session)), status="failed")
        with pytest.raises(oe.UnknownDispatch):  # a refused send never reached anyone
            await emit(Session, "delivered", failed)
        return first, more, len(await outbox(Session))
    assert run(go) == ([True, False], [True, True], 3)


async def _ids(Session):
    from app.models import Domain, EmailAccount
    async with Session() as s:
        return (await s.execute(select(Domain.id))).scalars().first(), (await s.execute(select(EmailAccount.id))).scalars().first()


def test_concurrent_emits_of_the_same_event_create_one_row():
    async def go(Session):
        mid = await fixture_dispatch(Session)
        got = await asyncio.gather(*[emit(Session, "bounced", mid) for _ in range(20)])
        return sum(got), len(await outbox(Session))
    assert run(go) == (1, 1)


def test_delivery_payload_headers_and_ack_state(receiver):
    rcv = receiver()

    async def go(Session):
        mid = await fixture_dispatch(Session)
        ts = datetime(2026, 10, 1, 12, 0, 0)
        await emit(Session, "delivered", mid, ts)
        n = await drain(Session)
        return mid, n, (await outbox(Session))[0]
    mid, n, row = run(go)
    headers, body = rcv.requests[0]
    assert n == 1 and len(rcv.requests) == 1
    assert headers["x-webhook-secret"] == "shh" and headers["Idempotency-Key"] == f"delivered:{mid}"
    assert body == {"event_type": "delivered", "message_id": mid, "timestamp": "2026-10-01T12:00:00+00:00"}
    assert row.status == "delivered" and row.delivered_at and row.attempts == 1


def test_transient_failure_persists_backoff_and_retries_after_it(receiver):
    rcv = receiver(script=[503, 500])
    clock = [datetime(2026, 1, 1)]

    async def go(Session):
        mid = await fixture_dispatch(Session)
        await emit(Session, "bounced", mid)
        async with Session() as s:  # make the fake clock authoritative
            await s.execute(update(OutboundEvent).values(next_attempt_at=clock[0]))
            await s.commit()
        kw = dict(now=lambda: clock[0], base_delay=10)
        out = [await drain(Session, **kw)]  # 503
        r1 = (await outbox(Session))[0]
        out.append(await drain(Session, **kw))  # not due yet: no POST
        clock[0] += timedelta(seconds=10)
        out.append(await drain(Session, **kw))  # 500, backoff doubles
        r2 = (await outbox(Session))[0]
        clock[0] += timedelta(seconds=19)
        out.append(await drain(Session, **kw))  # still 1s early
        clock[0] += timedelta(seconds=1)
        out.append(await drain(Session, **kw))  # 200
        return out, r1, r2, (await outbox(Session))[0]
    out, r1, r2, done = run(go)
    assert out == [0, 0, 0, 0, 1] and len(rcv.requests) == 3
    assert (r1.status, r1.attempts, r1.last_error) == ("pending", 1, "HTTP 503")
    assert r1.next_attempt_at == datetime(2026, 1, 1, 0, 0, 10)
    assert (r2.attempts, r2.next_attempt_at) == (2, datetime(2026, 1, 1, 0, 0, 30))
    assert (done.status, done.attempts) == ("delivered", 3)


def test_permanent_4xx_goes_dead_without_retry_and_other_4xx_retries(receiver):
    rcv = receiver(script=[422, 401])

    async def go(Session):
        a, b = await fixture_dispatch(Session), await fixture_dispatch(Session)
        await emit(Session, "bounced", a)
        await emit(Session, "bounced", b)
        await drain(Session, base_delay=0)
        return {r.message_id: r for r in await outbox(Session)}, a, b
    rows, a, b = run(go)
    assert rows[a].status == "dead" and rows[a].last_error == "HTTP 422"
    # 401 is a wrong shared secret: fixable, so it must not destroy the event
    assert rows[b].status in ("pending", "delivered") and rows[b].status != "dead"


def test_attempts_exhausted_goes_dead_and_stays_for_replay(receiver):
    receiver(script=[500] * 10)

    async def go(Session):
        await emit(Session, "bounced", await fixture_dispatch(Session))
        for _ in range(3):
            await drain(Session, max_attempts=3, base_delay=0)
        return (await outbox(Session))[0]
    row = run(go)
    assert (row.status, row.attempts, row.last_error) == ("dead", 3, "HTTP 500")


def test_event_survives_cancellation_after_claim_before_post_and_restart(receiver):
    """The old queue lost it at exactly this point (LPOP, then cancelled)."""
    rcv = receiver()

    async def go(Session):
        mid = await fixture_dispatch(Session)
        await emit(Session, "bounced", mid)
        stuck = asyncio.Event()

        class HangingClient:  # the worker is cancelled while "about to POST"
            async def post(self, *a, **kw):
                stuck.set()
                await asyncio.Event().wait()
        task = asyncio.create_task(oe.drain(Session, HangingClient()))
        await stuck.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        claimed = (await outbox(Session))[0]
        assert not rcv.requests
        # lease still held: a second worker right now must not deliver it (no double send)
        assert await drain(Session) == 0 and not rcv.requests
        # "restart": brand new session factory, after the lease expires
        from sqlalchemy.ext.asyncio import async_sessionmaker
        Session2 = async_sessionmaker(Session.kw["bind"], expire_on_commit=False)
        later = datetime.utcnow() + timedelta(seconds=oe.LEASE_S + 1)
        n = await drain(Session2, now=lambda: later)
        return claimed, n, (await outbox(Session2))[0]
    claimed, n, final = run(go)
    assert (claimed.status, claimed.attempts) == ("leased", 1) and claimed.lease_expires_at
    assert n == 1 and len(rcv.requests) == 1
    assert (final.status, final.attempts) == ("delivered", 2)


def test_crashed_worker_mid_post_is_reclaimed_and_counts_the_attempt(receiver):
    receiver(script=[200])

    async def go(Session):
        mid = await fixture_dispatch(Session)
        await emit(Session, "clicked", mid)
        assert await oe._claim(Session, datetime.utcnow(), 30, 5)  # claimed, then the process "died"
        assert await drain(Session) == 0  # lease live
        n = await drain(Session, now=lambda: datetime.utcnow() + timedelta(seconds=31))
        return n, (await outbox(Session))[0]
    n, row = run(go)
    assert n == 1 and row.attempts == 2


def test_lease_expired_on_final_attempt_is_dead_not_retried_forever(receiver):
    rcv = receiver()

    async def go(Session):
        await emit(Session, "clicked", await fixture_dispatch(Session))
        await oe._claim(Session, datetime.utcnow(), 30, 1)
        n = await drain(Session, max_attempts=1, now=lambda: datetime.utcnow() + timedelta(seconds=31))
        return n, (await outbox(Session))[0]
    n, row = run(go)
    assert n == 0 and not rcv.requests and row.status == "dead"


def test_two_workers_never_post_the_same_event_twice(receiver):
    rcv = receiver()

    async def go(Session):
        for _ in range(6):
            await emit(Session, "opened", await fixture_dispatch(Session))
        got = await asyncio.gather(*[drain(Session) for _ in range(4)])
        return sum(got)
    assert run(go) == 6
    assert len({r[1]["message_id"] for r in rcv.requests}) == 6 == len(rcv.requests)


def test_lost_acknowledgement_means_redelivery_not_exactly_once(receiver):
    """Documented limit: the receiver applied the event, the ack never arrived, so we send it again."""
    rcv = receiver(lose_ack=True)

    async def go(Session):
        await emit(Session, "bounced", await fixture_dispatch(Session))
        await drain(Session, base_delay=0)
        first = (await outbox(Session))[0]
        rcv.lose_ack = False
        await drain(Session, base_delay=0)
        return first, (await outbox(Session))[0]
    first, final = run(go)
    assert first.status == "pending" and final.status == "delivered"
    assert len(rcv.requests) == 2  # at-least-once: same event twice, same Idempotency-Key both times
    assert rcv.requests[0][0]["Idempotency-Key"] == rcv.requests[1][0]["Idempotency-Key"]
    assert rcv.requests[0][1] == rcv.requests[1][1]


def test_without_client_url_events_stay_pending(monkeypatch):
    monkeypatch.setattr(get_settings(), "champmail_client_url", "")

    async def go(Session):
        await emit(Session, "bounced", await fixture_dispatch(Session))
        return await drain(Session), (await outbox(Session))[0]
    n, row = run(go)
    assert n == 0 and (row.status, row.attempts) == ("pending", 0)
