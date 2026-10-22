"""poll_all against real Postgres with a scripted IMAP client: isolation, timeout bound, auth-failure pause.

The real-server version of this lives in test_gate5_imap.py.
"""
import imaplib
import os
import uuid

import pytest
from sqlalchemy import select

from app.crypto import encrypt_secret
from app.models import EmailAccount, Domain
from app.services import bounce_poller as bp
from app.services import send as svc
from tests.helpers import add_dispatch, outbox
from tests.test_outbound_events_bounces import dsn
from tests.test_send import run, seed

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")


class FakeImap:
    """Hosts: bad.test refuses the login, down.test is unreachable, anything else serves one unseen DSN."""
    opened: list = []
    timeouts: list = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        FakeImap.opened.append(host)
        FakeImap.timeouts.append(timeout)
        if host == "down.test":
            raise ConnectionRefusedError("down")

    def login(self, user, password):
        if self.host == "bad.test":
            raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")

    def shutdown(self):
        pass

    def select(self, mailbox):
        pass

    def uid(self, cmd, *args):
        if cmd == "SEARCH":
            return "OK", [b"7"]
        if cmd == "FETCH":
            return "OK", [(b"7 (BODY[])", dsn("5.1.1", orig_id=f"<{self.host}-1@champmail.test>"))]
        return "OK", [b""]

    def logout(self):
        pass


@pytest.fixture(autouse=True)
def fake_imap(monkeypatch):
    monkeypatch.setattr(imaplib, "IMAP4_SSL", FakeImap)
    FakeImap.opened, FakeImap.timeouts = [], []


async def add_box(Session, dom, name, host, **kw):
    async with Session() as s:
        b = EmailAccount(id=uuid.uuid4(), name=name, email=f"{name}@x.test", domain_id=dom, imap_host=host,
                         imap_password_encrypted=encrypt_secret("pw"), smtp_host="smtp.test",
                         smtp_password_encrypted=encrypt_secret("pw"), **kw)
        s.add(b)
        await s.commit()
        return b.id


async def poll(Session):
    async with Session() as s:
        return await bp.poll_all(s)


async def box(Session, id):
    async with Session() as s:
        return (await s.execute(select(EmailAccount).where(EmailAccount.id == id))).scalar_one()


async def world(Session, hosts):
    """A domain whose mailboxes polled in order `hosts`, each with a dispatch for the DSN its host serves."""
    dom, (_,) = await seed(Session)  # its mailbox has no IMAP settings, so it is never polled
    ids = {}
    for i, h in enumerate(hosts):
        ids[h] = await add_box(Session, dom, f"b{i}", h)
        await add_dispatch(Session, dom, ids[h], message_id=f"{h}-1@champmail.test")
    return dom, ids


def test_broken_first_mailbox_does_not_stop_the_second_and_is_paused_only_on_auth_failure():
    async def go(Session):
        dom, ids = await world(Session, ["bad.test", "down.test", "good.test"])
        total = await poll(Session)
        return total, {h: await box(Session, i) for h, i in ids.items()}, await outbox(Session)
    total, boxes, rows = run(go)
    assert FakeImap.opened[:3] == ["bad.test", "down.test", "good.test"]
    assert total == 1 and [(r.event_type, r.message_id) for r in rows] == [("bounced", "good.test-1@champmail.test")]
    bad = boxes["bad.test"]
    assert bad.status == "paused" and bad.status_reason.startswith("imap_auth_failed: ")
    assert "AUTHENTICATIONFAILED" in bad.status_reason
    # unreachable server is NOT an auth failure; healthy box untouched
    assert (boxes["down.test"].status, boxes["down.test"].status_reason) == ("active", None)
    assert (boxes["good.test"].status, boxes["good.test"].status_reason) == ("active", None)


def test_imap_connection_uses_a_timeout():
    async def go(Session):
        await world(Session, ["good.test"])
        await poll(Session)
    run(go)
    assert FakeImap.timeouts and set(FakeImap.timeouts) == {bp.IMAP_TIMEOUT_S}


def test_auth_failure_pauses_the_mailboxs_sending_only():
    async def go(Session):
        dom, ids = await world(Session, ["bad.test", "good.test"])
        await poll(Session)
        async with Session() as s:
            with pytest.raises(svc.SendRefused) as e:
                await svc.claim_mailbox(s, mailbox_id=ids["bad.test"])
        async with Session() as s:
            ok = await svc.claim_mailbox(s, mailbox_id=ids["good.test"])  # sibling on the same domain still sends
        async with Session() as s:
            d = (await s.execute(select(Domain).where(Domain.id == dom))).scalar_one()
        return (e.value.status, e.value.code), ok.mailbox.id == ids["good.test"], (d.paused, d.status, d.send_status)
    assert run(go) == ((409, "mailbox_paused"), True, (False, "verified", "active"))


@pytest.mark.parametrize("status,reason", [("paused", "operator: investigating"), ("retired", "decommissioned")])
def test_manual_pause_or_retire_is_never_overwritten_by_an_auth_failure(status, reason):
    async def go(Session):
        dom, _ = await world(Session, [])
        id = await add_box(Session, dom, "m", "bad.test", status=status, status_reason=reason)
        await poll(Session)
        await poll(Session)
        return await box(Session, id)
    b = run(go)
    assert (b.status, b.status_reason) == (status, reason)


def test_auth_paused_mailbox_is_left_alone_until_an_operator_resumes_it():
    async def go(Session):
        dom, ids = await world(Session, ["bad.test"])
        await poll(Session)
        n1 = FakeImap.opened.count("bad.test")
        await poll(Session)
        n2 = FakeImap.opened.count("bad.test")  # not retried while paused by auth failure
        paused = await box(Session, ids["bad.test"])
        # operator PATCH /mailboxes/{id} {status: active, reason: ...}: polled again, and the worker never resumed it itself
        async with Session() as s:
            m = await s.get(EmailAccount, ids["bad.test"])
            m.status, m.status_reason = "active", "credentials rotated"
            await s.commit()
        await poll(Session)
        return n1, n2, paused.status, FakeImap.opened.count("bad.test"), (await box(Session, ids["bad.test"])).status
    n1, n2, status, n3, after = run(go)
    assert (n1, n2, status) == (1, 1, "paused")
    assert n3 == 2 and after == "paused"  # fails again with the same bad credentials, paused again with a fresh reason


def test_a_manually_paused_mailbox_is_still_polled_so_its_bounces_are_not_lost():
    async def go(Session):
        dom, _ = await world(Session, [])
        id = await add_box(Session, dom, "m", "good.test", status="paused", status_reason="operator")
        await add_dispatch(Session, dom, id, message_id="good.test-1@champmail.test")
        return await poll(Session), await outbox(Session), (await box(Session, id)).status
    total, rows, status = run(go)
    assert total == 1 and len(rows) == 1 and status == "paused"
