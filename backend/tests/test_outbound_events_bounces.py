"""DSN parsing and storage: hard/soft classification, delivery receipts, one transaction per DSN (real Postgres)."""
import os

import pytest
from sqlalchemy import select

from app.models import Bounce
from app.services.bounce_poller import parse_dsn, process_dsn
from tests.helpers import add_dispatch, outbox
from tests.test_send import run, seed

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")


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


def test_classifies_hard_soft_and_delivery_receipt():
    hard = parse_dsn(dsn("5.1.1"))
    soft = parse_dsn(dsn("4.2.2", action="delayed"))
    ok = parse_dsn(dsn("2.0.0", action="delivered"))
    assert (hard.kind, hard.status, hard.message_id, hard.recipient) == ("hard", "5.1.1", "orig-1@champmail.test", "bob@example.com")
    assert (soft.kind, soft.status) == ("soft", "4.2.2")
    assert (ok.kind, ok.status, ok.message_id) == ("delivered", "2.0.0", "orig-1@champmail.test")
    assert parse_dsn(dsn("2.0.0", action="relayed")) is None  # handed to another MTA: not a delivery fact


async def setup(Session, **ids):
    dom, (mb,) = await seed(Session)
    mids = {k: await add_dispatch(Session, dom, mb, message_id=v) for k, v in ids.items()}
    return mb, mids


async def bounces(Session):
    async with Session() as s:
        return [(b.kind, b.status_code, b.message_id) for b in (await s.execute(select(Bounce).order_by(Bounce.kind))).scalars()]


def test_hard_bounce_stored_and_queued_once_across_a_replay():
    async def go(Session):
        mb, _ = await setup(Session, h="orig-1@champmail.test")
        raw = dsn("5.1.1")
        out = []
        for _ in range(2):  # the second is the re-poll of the same DSN
            async with Session() as s:
                out.append(await process_dsn(s, mb, raw))
        return out, await bounces(Session), await outbox(Session)
    out, stored, rows = run(go)
    assert out == ["hard", "hard"] and stored == [("hard", "5.1.1", "orig-1@champmail.test")]
    assert [(r.event_type, r.message_id, r.status) for r in rows] == [("bounced", "orig-1@champmail.test", "pending")]


def test_soft_bounce_is_stored_and_never_queued():
    async def go(Session):
        mb, _ = await setup(Session, s="orig-1@champmail.test")
        async with Session() as s:
            return await process_dsn(s, mb, dsn("4.2.2", action="delayed")), await bounces(Session), await outbox(Session)
    kind, stored, rows = run(go)
    assert kind == "soft" and stored == [("soft", "4.2.2", "orig-1@champmail.test")] and rows == []


def test_dsn_for_a_message_we_never_dispatched_is_stored_but_not_forwarded():
    async def go(Session):
        mb, _ = await setup(Session)
        async with Session() as s:
            a = await process_dsn(s, mb, dsn("5.1.1", orig_id="<forged-by-someone@evil.test>"))
        async with Session() as s:
            b = await process_dsn(s, mb, dsn("5.7.1", orig_id="<>"))  # no Message-ID at all
        return a, b, await bounces(Session), await outbox(Session)
    a, b, stored, rows = run(go)
    assert (a, b) == ("hard", "hard") and len(stored) == 2 and rows == []


def test_delivery_receipt_queues_delivered_and_is_not_a_bounce():
    async def go(Session):
        mb, _ = await setup(Session, d="orig-1@champmail.test")
        raw = dsn("2.0.0", action="delivered")
        for _ in range(2):
            async with Session() as s:
                assert await process_dsn(s, mb, raw) == "delivered"
        async with Session() as s:
            assert await process_dsn(s, mb, dsn("2.0.0", action="relayed")) is None
        return await bounces(Session), await outbox(Session)
    stored, rows = run(go)
    assert stored == [] and [(r.event_type, r.message_id) for r in rows] == [("delivered", "orig-1@champmail.test")]
