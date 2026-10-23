"""canary: true sends, against real Postgres, Redis and Mailpit.

A canary is the one send allowed through a policy pause, so the tests that matter most are the ones
where it must NOT go out: a recipient outside the seed registry, a retired domain or mailbox.
"""
import asyncio
import os
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.models import Domain, EmailAccount, SendDispatch
from tests.test_send import HARBINGER, run, seed
from tests.test_send_mailpit_live import API, SMTP, total

pytestmark = pytest.mark.skipif(not (os.environ.get("TEST_DATABASE_URL") and SMTP and API),
                                reason="needs TEST_DATABASE_URL, TEST_MAILPIT_SMTP and TEST_MAILPIT_API")
SEED = "seed1@gmail.com"
CANARY = {**HARBINGER, "to": SEED, "brand_id": "b1", "canary": True, "subject": "canary",
          "headers": {"X-Sledgehammer-Canary": "run-42"}}


async def world(Session, c, *, n=1, register=(SEED,), box_kw=None, dom_kw=None, limit=30):
    host, port = SMTP.rsplit(":", 1)
    dom, boxes = await seed(Session, n=n, limit=limit, dom_kw=dom_kw,
                            box_kw={"smtp_host": host, "smtp_port": int(port), "smtp_use_tls": False,
                                    "imap_host": None, **(box_kw or {})})
    for a in register:
        assert (await c.post("/api/v1/seeds", json={"address": a, "provider": "gmail"})).status_code == 201
    return dom, boxes


async def hold(c, dom, status="paused"):
    r = await c.patch(f"/api/v1/domains/{dom}", json={"status": status, "reason": "policy"})
    assert r.status_code == 200, r.text


async def state(Session, dom, mb):
    async with Session() as s:
        d, b = await s.get(Domain, dom), await s.get(EmailAccount, mb)
        rows = list((await s.execute(select(SendDispatch))).scalars())
        return d, b, rows


def test_paused_domain_refuses_normal_send_but_takes_a_canary_to_a_seed(client):
    async def go(Session):
        async def scenario(c):
            dom, (mb,) = await world(Session, c)
            await hold(c, dom)
            before = total()
            normal = await c.post("/api/v1/send", json={**HARBINGER, "to": SEED, "brand_id": "b1"})
            assert normal.status_code == 409 and normal.json()["code"] == "domain_paused"
            assert total() == before

            r = await c.post("/api/v1/send", json=CANARY)
            assert r.status_code == 200, r.text
            assert r.json()["status"] == "sent" and r.json()["domain_id"] == str(dom)
            assert total() == before + 1
            hdrs = httpx.get(f"{API}/api/v1/message/latest/headers").json()
            assert hdrs["X-Sledgehammer-Canary"] == ["run-42"]

            d, b, rows = await state(Session, dom, mb)
            assert [(x.canary, x.status) for x in rows] == [(True, "sent")]
            assert (b.sent_today, b.next_send_at, b.last_send_at) == (0, None, None)  # campaign cap and gap untouched
            assert d.canary_sends_today == 1 and d.send_status == "paused"
            listed = (await c.get("/api/v1/domains")).json()[0]
            assert listed["canary_sends_today"] == 1
        await client(Session, scenario)
    run(go)


@pytest.mark.parametrize("to", ["stranger@corp.com", f'"{SEED}" <evil@corp.com>', f"{SEED}.evil.com", f"x{SEED}"])
def test_canary_to_a_non_seed_is_422_and_never_goes_out(client, to):
    async def go(Session):
        async def scenario(c):
            dom, (mb,) = await world(Session, c)
            await hold(c, dom)
            before = total()
            r = await c.post("/api/v1/send", json={**CANARY, "to": to})
            assert r.status_code == 422, r.text
            assert total() == before
            d, b, rows = await state(Session, dom, mb)
            assert rows == [] and d.canary_sends_today in (0, None) and b.sent_today == 0
        await client(Session, scenario)
    run(go)


def test_seed_match_ignores_case(client):
    async def go(Session):
        async def scenario(c):
            dom, _ = await world(Session, c)
            await hold(c, dom)
            assert (await c.post("/api/v1/send", json={**CANARY, "to": "SEED1@Gmail.com"})).status_code == 200
        await client(Session, scenario)
    run(go)


def test_seventh_canary_is_429_and_campaign_cap_is_unchanged(client):
    async def go(Session):
        async def scenario(c):
            dom, (mb,) = await world(Session, c, limit=30)
            await hold(c, dom)
            before = total()
            for i in range(6):  # no 45 s gap between them
                r = await c.post("/api/v1/send", json={**CANARY, "subject": f"c{i}"})
                assert r.status_code == 200, (i, r.text)
            r = await c.post("/api/v1/send", json=CANARY)
            assert r.status_code == 429 and r.json()["code"] == "canary_cap", r.text
            assert total() == before + 6
            d, b, rows = await state(Session, dom, mb)
            assert d.canary_sends_today == 6 and len(rows) == 6
            assert (b.sent_today, b.daily_send_limit, b.next_send_at) == (0, 30, None)
            await c.patch(f"/api/v1/domains/{dom}", json={"status": "active"})
            normal = await c.post("/api/v1/send", json={**HARBINGER, "to": "lead@corp.com", "brand_id": "b1"})
            assert normal.status_code == 200  # the full campaign allowance is still there
        await client(Session, scenario)
    run(go)


def test_concurrent_canaries_never_exceed_the_cap(client):
    async def go(Session):
        async def scenario(c):
            dom, _ = await world(Session, c, n=3)
            await hold(c, dom)
            before = total()
            rs = await asyncio.gather(*[c.post("/api/v1/send", json={**CANARY, "subject": f"p{i}"}) for i in range(10)])
            assert sorted(r.status_code for r in rs) == [200] * 6 + [429] * 4
            assert total() == before + 6
            assert (await state(Session, dom, (await world_box(Session, dom))))[0].canary_sends_today == 6
        await client(Session, scenario)
    run(go)


async def world_box(Session, dom):
    async with Session() as s:
        return (await s.execute(select(EmailAccount.id).where(EmailAccount.domain_id == dom).limit(1))).scalar_one()


def test_counter_resets_on_a_new_day(client):
    async def go(Session):
        async def scenario(c):
            dom, (mb,) = await world(Session, c)
            await hold(c, dom)
            async with Session() as s:
                d = await s.get(Domain, dom)
                d.canary_sends_today, d.canary_sends_date = 6, datetime.utcnow().date() - timedelta(days=1)
                await s.commit()
            assert (await c.post("/api/v1/send", json=CANARY)).status_code == 200
            assert (await state(Session, dom, mb))[0].canary_sends_today == 1
        await client(Session, scenario)
    run(go)


def test_retired_domain_canary_is_409(client):
    async def go(Session):
        async def scenario(c):
            dom, (mb,) = await world(Session, c)
            await hold(c, dom, "retired")
            before = total()
            r = await c.post("/api/v1/send", json=CANARY)
            assert r.status_code == 409 and r.json()["code"] == "domain_retired", r.text
            assert total() == before and (await state(Session, dom, mb))[2] == []
        await client(Session, scenario)
    run(go)


def test_retired_or_individually_paused_mailbox_canary_is_409(client):
    async def go(Session):
        async def scenario(c):
            dom, (mb,) = await world(Session, c)
            await hold(c, dom)
            before = total()
            for status, code in (("paused", "mailbox_paused"), ("retired", "mailbox_retired")):
                assert (await c.patch(f"/api/v1/mailboxes/{mb}", json={"status": status, "reason": "x"})).status_code == 200
                r = await c.post("/api/v1/send", json=CANARY)
                assert r.status_code == 409 and r.json()["code"] == code, r.text
            assert total() == before
        await client(Session, scenario)
    run(go)


def test_canary_works_on_an_active_domain_without_touching_the_campaign_cap(client):
    async def go(Session):
        async def scenario(c):
            dom, (mb,) = await world(Session, c)
            assert (await c.post("/api/v1/send", json=CANARY)).status_code == 200
            _, b, _ = await state(Session, dom, mb)
            assert (b.sent_today, b.next_send_at) == (0, None)
        await client(Session, scenario)
    run(go)


def test_only_the_canary_header_is_forwarded_and_it_cannot_inject(client):
    async def go(Session):
        async def scenario(c):
            dom, _ = await world(Session, c)
            await hold(c, dom)
            r = await c.post("/api/v1/send", json={**CANARY, "headers": {"X-Sledgehammer-Canary": "r1", "Bcc": "evil@corp.com",
                                                                          "x-other": "nope"}})
            assert r.status_code == 200, r.text
            hdrs = httpx.get(f"{API}/api/v1/message/latest/headers").json()
            assert hdrs["X-Sledgehammer-Canary"] == ["r1"]
            assert not {"Bcc", "X-Other"} & set(hdrs)
            msg = httpx.get(f"{API}/api/v1/message/latest").json()
            assert [t["Address"] for t in msg["To"]] == [SEED] and msg["Bcc"] == []
            r = await c.post("/api/v1/send", json={**CANARY, "headers": {"X-Sledgehammer-Canary": "r1\r\nBcc: evil@corp.com"}})
            assert r.status_code == 422
        await client(Session, scenario)
    run(go)


def test_canary_idempotency_follows_the_normal_rules(client):
    async def go(Session):
        async def scenario(c):
            dom, (mb,) = await world(Session, c)
            await hold(c, dom)
            before = total()
            h = {"Idempotency-Key": "sh:canary:1"}
            first = await c.post("/api/v1/send", json=CANARY, headers=h)
            again = await c.post("/api/v1/send", json=CANARY, headers=h)
            assert first.status_code == again.status_code == 200 and first.json() == again.json()
            assert total() == before + 1
            d, _, rows = await state(Session, dom, mb)
            assert d.canary_sends_today == 1 and len(rows) == 1
            # the same key on a request that differs (here: not a canary) is a conflict, never a second send
            other = await c.post("/api/v1/send", json={**CANARY, "canary": False}, headers=h)
            assert other.status_code == 409 and other.json()["code"] == "idempotency_conflict"
            assert total() == before + 1
        await client(Session, scenario)
    run(go)


def test_failed_smtp_gives_the_canary_slot_back(client):
    async def go(Session):
        async def scenario(c):
            dom, (mb,) = await world(Session, c, box_kw={"smtp_port": 1})  # nothing listens: definite refusal
            await hold(c, dom)
            r = await c.post("/api/v1/send", json=CANARY)
            assert r.status_code == 502, r.text
            d, b, rows = await state(Session, dom, mb)
            assert d.canary_sends_today == 0 and b.sent_today == 0 and [x.status for x in rows] == ["failed"]
        await client(Session, scenario)
    run(go)
