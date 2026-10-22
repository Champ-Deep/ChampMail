"""POST /api/v1/send: idempotent dispatch, Redis gate, refusal semantics, SMTP ambiguity.

Real Postgres (TEST_DATABASE_URL) and the real endpoint; only aiosmtplib.send is replaced by a
recorder that can fail, stall, or "accept and then lose the ack".
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import aiosmtplib
import httpx
import pytest
from sqlalchemy import func, select, update

import app.db.redis as redis_mod
from app.api.v1 import send as send_api
from app.main import app
from app.models import EmailAccount, SendDispatch
from app.services import send as svc
from tests.test_send import HARBINGER, RedisUp, run, seed

pytestmark = pytest.mark.skipif(not __import__("os").environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")

BODY = {**HARBINGER, "brand_id": "b1", "unsubscribe_url": "https://u.example/x"}


class Smtp:
    """Stands in for aiosmtplib.send. `sent` is what a real server would hold."""

    def __init__(self, fail=None, lose_ack=None, delay=0.0):
        self.sent, self.fail, self.lose_ack, self.delay = [], fail, lose_ack, delay

    async def send(self, msg, **kw):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise self.fail
        self.sent.append(msg["Message-ID"])
        if self.lose_ack:  # server took the message, the client never heard
            raise self.lose_ack


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("EMAIL_ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setattr(send_api, "redis_client", RedisUp())
    yield
    app.dependency_overrides.clear()


def install(Session, monkeypatch, smtp):
    async def session_dep():
        async with Session() as s:
            yield s
    app.dependency_overrides[send_api.get_session] = session_dep
    monkeypatch.setattr(svc.aiosmtplib, "send", smtp.send)


async def post(body, headers=None):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.post("/api/v1/send", json=body, headers=headers)


async def state(Session):
    async with Session() as s:
        rows = (await s.execute(select(SendDispatch).order_by(SendDispatch.created_at))).scalars().all()
        sent_today = (await s.execute(select(func.coalesce(func.sum(EmailAccount.sent_today), 0)))).scalar_one()
        return rows, sent_today


async def unthrottle(Session):
    async with Session() as s:
        await s.execute(update(EmailAccount).values(next_send_at=None))
        await s.commit()


def key(k, body=None, header=True, field=True):
    return ({**(body or BODY), **({"idempotency_key": k} if field else {})}, {"Idempotency-Key": k} if header else None)


# --- idempotency --------------------------------------------------------------

@pytest.mark.parametrize("header,field", [(True, True), (True, False), (False, True)])
def test_same_key_same_payload_returns_identical_response_without_second_send(monkeypatch, header, field):
    smtp = Smtp()

    async def go(Session):
        dom, ids = await seed(Session, n=2)
        install(Session, monkeypatch, smtp)
        a = await post(*key("sledgehammer:e1:1", header=header, field=field))
        b = await post(*key("sledgehammer:e1:1", header=header, field=field))
        return dom, ids, a, b, await state(Session)
    dom, ids, a, b, (rows, sent_today) = run(go)
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
    assert len(smtp.sent) == 1 and sent_today == 1  # no second SMTP, no second cap slot
    (row,) = rows
    assert row.status == "sent" and row.idempotency_key == "sledgehammer:e1:1"
    assert row.message_id == a.json()["message_id"] and f"<{row.message_id}>" == smtp.sent[0]
    assert row.domain_id == dom and row.mailbox_id in ids and row.response == a.json()
    assert row.payload_hash and "pw" not in str(row.response)


def test_header_and_field_mismatch_is_422_and_nothing_happens(monkeypatch):
    smtp = Smtp()

    async def go(Session):
        await seed(Session)
        install(Session, monkeypatch, smtp)
        r = await post({**BODY, "idempotency_key": "k1"}, {"Idempotency-Key": "k2"})
        blank = await post({**BODY, "idempotency_key": "  "})
        return r, blank, await state(Session)
    r, blank, (rows, sent_today) = run(go)
    assert r.status_code == 422 and blank.status_code == 422
    assert smtp.sent == [] and rows == [] and sent_today == 0


def test_changed_payload_under_same_key_is_409_conflict(monkeypatch):
    smtp = Smtp()

    async def go(Session):
        await seed(Session, n=2)
        install(Session, monkeypatch, smtp)
        a = await post(*key("k1"))
        b = await post(*key("k1", {**BODY, "subject": "different"}))
        return a, b, await state(Session)
    a, b, (rows, sent_today) = run(go)
    assert a.status_code == 200 and b.status_code == 409 and b.json()["code"] == "idempotency_conflict"
    assert len(smtp.sent) == 1 and sent_today == 1 and len(rows) == 1


def test_keyless_requests_are_never_deduplicated_and_still_leave_a_dispatch_row(monkeypatch):
    smtp = Smtp()

    async def go(Session):
        dom, ids = await seed(Session, n=2)
        install(Session, monkeypatch, smtp)
        a, b = await post(BODY), await post(BODY)  # identical content, no key (Harbinger)
        return dom, a, b, await state(Session)
    dom, a, b, (rows, sent_today) = run(go)
    assert a.status_code == b.status_code == 200 and a.json()["message_id"] != b.json()["message_id"]
    assert len(smtp.sent) == 2 and sent_today == 2
    assert [r.idempotency_key for r in rows] == [None, None]
    assert {r.message_id for r in rows} == {a.json()["message_id"], b.json()["message_id"]}
    assert {r.domain_id for r in rows} == {dom}


@pytest.mark.parametrize("selector", ["pooled", "named"])
def test_concurrent_same_key_submits_at_most_once(monkeypatch, selector):
    smtp = Smtp(delay=0.3)  # hold the first request inside SMTP so the others overlap it

    async def go(Session):
        _, ids = await seed(Session, n=3)  # pooled: three mailboxes a loser could grab
        install(Session, monkeypatch, smtp)
        body = {**BODY, **({"mailbox_id": str(ids[0])} if selector == "named" else {})}
        rs = await asyncio.gather(*[post(*key("k-conc", body)) for _ in range(8)])
        again = await post(*key("k-conc", body))
        return rs, again, await state(Session)
    rs, again, (rows, sent_today) = run(go)
    codes = sorted(r.status_code for r in rs)
    assert codes.count(200) == 1 and set(codes) <= {200, 503}, codes
    assert {r.json()["code"] for r in rs if r.status_code == 503} <= {"dispatch_in_progress"}
    assert len(smtp.sent) == 1 and sent_today == 1 and len(rows) == 1  # losers gave their slots back
    winner = next(r for r in rs if r.status_code == 200)
    assert again.status_code == 200 and again.json() == winner.json()


# --- SMTP ambiguity -----------------------------------------------------------

def test_accepted_then_timeout_is_unknown_and_never_retransmitted(monkeypatch):
    smtp = Smtp(lose_ack=aiosmtplib.SMTPReadTimeoutError("ack lost"))

    async def go(Session):
        await seed(Session, n=2)
        install(Session, monkeypatch, smtp)
        first = await post(*key("k-amb"))
        await unthrottle(Session)
        retry = await post(*key("k-amb"))
        await unthrottle(Session)
        again = await post(*key("k-amb"))
        return first, retry, again, await state(Session)
    first, retry, again, (rows, sent_today) = run(go)
    for r in (first, retry, again):
        assert r.status_code == 503 and r.json()["code"] == "smtp_outcome_unknown" and r.headers["retry-after"]
        assert r.json()["message_id"] == rows[0].message_id
    assert len(smtp.sent) == 1  # the one real submission; retries did not resend
    assert [r.status for r in rows] == ["unknown"] and sent_today == 1  # slot stays spent


def test_operator_reconciliation_paths(monkeypatch):
    """unknown -> sent (operator saw the mail) replays; unknown -> failed (operator saw none) retries."""
    smtp = Smtp(lose_ack=aiosmtplib.SMTPServerDisconnected("reset"))

    async def go(Session):
        await seed(Session, n=1)
        install(Session, monkeypatch, smtp)
        assert (await post(*key("k-op"))).status_code == 503
        rows, _ = await state(Session)
        done = {"message_id": rows[0].message_id, "status": "sent", "domain_id": str(rows[0].domain_id),
                "sent_at": datetime.utcnow().isoformat()}
        async with Session() as s:
            await s.execute(update(SendDispatch).values(status="sent", response=done))
            await s.commit()
        replay = await post(*key("k-op"))
        async with Session() as s:  # operator checked the provider: nothing was delivered
            await s.execute(update(SendDispatch).values(status="failed", response=None))
            await s.execute(update(EmailAccount).values(next_send_at=None, sent_today=0))
            await s.commit()
        smtp.lose_ack = None
        retried = await post(*key("k-op"))
        return replay, done, retried, await state(Session)
    replay, done, retried, (rows, sent_today) = run(go)
    assert replay.status_code == 200 and replay.json() == done
    assert retried.status_code == 200 and len(rows) == 1 and rows[0].status == "sent"  # same row reused
    assert rows[0].message_id == retried.json()["message_id"] and sent_today == 1


def test_claim_without_outcome_survives_restart_as_in_progress(monkeypatch):
    """Process died after the claim committed and before SMTP resolved: state is in Postgres, not memory."""
    smtp = Smtp()

    async def go(Session):
        await seed(Session)
        install(Session, monkeypatch, smtp)
        h = svc.payload_fingerprint(send_api.SendRequest(**BODY).model_dump(mode="json", exclude={"idempotency_key"}))
        async with Session() as s:
            await svc.claim_mailbox(s, brand_id="b1", idempotency_key="k-crash", payload_hash=h)
        await unthrottle(Session)
        r = await post(*key("k-crash"))
        return r, await state(Session)
    r, (rows, sent_today) = run(go)
    assert r.status_code == 503 and r.json()["code"] == "dispatch_in_progress" and r.json()["message_id"] == rows[0].message_id
    assert smtp.sent == [] and rows[0].status == "sending" and sent_today == 1


def test_definite_refusal_releases_the_slot_and_the_same_key_may_retry(monkeypatch):
    smtp = Smtp(fail=aiosmtplib.SMTPConnectError("refused"))

    async def go(Session):
        await seed(Session, n=1)
        install(Session, monkeypatch, smtp)
        bad = await post(*key("k-retry"))
        mid_rows, mid_sent = await state(Session)
        smtp.fail = None
        await unthrottle(Session)  # the post-failure throttle is a backoff; let it elapse
        good = await post(*key("k-retry"))
        return bad, mid_rows[0].status, mid_sent, good, await state(Session)
    bad, mid_status, mid_sent, good, (rows, sent_today) = run(go)
    assert bad.status_code == 502 and mid_status == "failed" and mid_sent == 0
    assert good.status_code == 200 and len(rows) == 1 and rows[0].status == "sent" and sent_today == 1
    assert len(smtp.sent) == 1


# --- Redis gate ---------------------------------------------------------------

class RedisDown:
    async def ping(self):
        raise ConnectionError("redis down")


def test_redis_down_is_503_before_claim_or_smtp(monkeypatch):
    smtp = Smtp()

    async def go(Session):
        await seed(Session)
        install(Session, monkeypatch, smtp)
        monkeypatch.setattr(send_api, "redis_client", RedisDown())
        keyed, keyless = await post(*key("k-r")), await post(BODY)
        return keyed, keyless, await state(Session)
    keyed, keyless, (rows, sent_today) = run(go)
    for r in (keyed, keyless):
        assert r.status_code == 503 and r.json()["code"] == "redis_unavailable"
    assert smtp.sent == [] and rows == [] and sent_today == 0


def test_real_unreachable_redis_blocks_send(monkeypatch):
    """No fakes on the Redis side: the app's own client pointed at a closed port."""
    smtp = Smtp()

    class S:
        redis_url = "redis://127.0.0.1:1/0"
    monkeypatch.setattr(redis_mod, "get_settings", lambda: S)

    async def go(Session):
        await seed(Session)
        install(Session, monkeypatch, smtp)
        monkeypatch.setattr(send_api, "redis_client", redis_mod.RedisClient())
        return await post(BODY), await state(Session)
    r, (rows, sent_today) = run(go)
    assert r.status_code == 503 and r.json()["code"] == "redis_unavailable"
    assert smtp.sent == [] and rows == [] and sent_today == 0


# --- refusal semantics and constraints ---------------------------------------

@pytest.mark.parametrize("box_kw,dom_kw", [({"status": "paused"}, {}), ({"status": "retired"}, {}), ({}, {"paused": True}),
                                           ({}, {"status": "retired"}), ({}, {"blacklisted": True})])
def test_paused_or_retired_is_409_and_never_reaches_smtp(monkeypatch, box_kw, dom_kw):
    smtp = Smtp()

    async def go(Session):
        _, (mb,) = await seed(Session, box_kw=box_kw, dom_kw=dom_kw)
        install(Session, monkeypatch, smtp)
        return await post({**BODY, "mailbox_id": str(mb)}), await state(Session)
    r, (rows, sent_today) = run(go)
    assert r.status_code == 409 and smtp.sent == [] and rows == [] and sent_today == 0


def test_authentication_is_still_401(monkeypatch):
    class S:
        champmail_api_key = "secret"
        champmail_env = "development"
    monkeypatch.setattr(send_api, "get_settings", lambda: S)
    smtp = Smtp()

    async def go(Session):
        await seed(Session)
        install(Session, monkeypatch, smtp)
        return await post(BODY), await post(BODY, {"X-API-Key": "nope"})
    a, b = run(go)
    assert a.status_code == b.status_code == 401 and smtp.sent == []


def test_forged_from_address_and_brand_mismatch_are_refused(monkeypatch):
    smtp = Smtp()

    async def go(Session):
        d1, (mine,) = await seed(Session, brand="b1")
        d2, (theirs,) = await seed(Session, brand="b2")
        install(Session, monkeypatch, smtp)
        out = {
            "unknown_from": await post({**BODY, "from_address": "ceo@victim.example"}),
            "other_brand_from": await post({**BODY, "from_address": await _email(Session, theirs)}),  # brand_id is b1
            "mailbox_of_other_brand": await post({**BODY, "mailbox_id": str(theirs)}),
            "domain_of_other_brand": await post({**BODY, "domain_id": str(d2)}),
            "mailbox_in_other_domain": await post({**BODY, "mailbox_id": str(mine), "domain_id": str(d2)}),
        }
        return out, await state(Session)
    out, (rows, sent_today) = run(go)
    assert {k: r.status_code for k, r in out.items()} == {k: 404 for k in out}
    assert smtp.sent == [] and rows == [] and sent_today == 0  # nothing reached SMTP or burned a slot


async def _email(Session, mailbox_id):
    async with Session() as s:
        return (await s.execute(select(EmailAccount.email).where(EmailAccount.id == mailbox_id))).scalar_one()


def test_from_header_is_the_mailboxes_own_address_whatever_the_request_claims(monkeypatch):
    captured = []

    async def send(msg, **kw):
        captured.append(msg)
    smtp = Smtp()
    smtp.send = send

    async def go(Session):
        _, (mb,) = await seed(Session)
        install(Session, monkeypatch, smtp)
        own = await _email(Session, mb)
        r = await post({**BODY, "from_name": "Evil (evil@x.example)", "from_address": own.upper()})  # case-insensitive match
        return own, r
    own, r = run(go)
    assert r.status_code == 200
    assert captured[0]["From"].endswith(f"<{own}>") and captured[0]["From"].count("@") == 2  # name text + real address


def test_cap_one_two_concurrent_sends_one_wins_at_the_endpoint(monkeypatch):
    smtp = Smtp(delay=0.1)

    async def go(Session):
        _, (mb,) = await seed(Session, limit=1)
        install(Session, monkeypatch, smtp)
        rs = await asyncio.gather(post({**BODY, "mailbox_id": str(mb)}), post({**BODY, "mailbox_id": str(mb)}))
        return rs, await state(Session)
    rs, (rows, sent_today) = run(go)
    assert sorted(r.status_code for r in rs) == [200, 429]
    assert len(smtp.sent) == 1 and sent_today == 1 and len(rows) == 1


def test_gap_floor_and_jitter_survive_the_dispatch_claim(monkeypatch):
    smtp = Smtp()

    async def go(Session):
        _, (mb,) = await seed(Session)
        install(Session, monkeypatch, smtp)
        first = await post({**BODY, "mailbox_id": str(mb)})
        second = await post({**BODY, "mailbox_id": str(mb)})
        async with Session() as s:
            box = (await s.execute(select(EmailAccount))).scalar_one()
        return first, second, box.next_send_at - box.last_send_at
    first, second, gap = run(go)
    assert first.status_code == 200 and second.status_code == 429 and second.json()["code"] == "throttled"
    assert timedelta(seconds=45) <= gap < timedelta(seconds=135)
