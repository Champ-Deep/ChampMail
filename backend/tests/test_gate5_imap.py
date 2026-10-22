"""Original M1 gate 5, for real: DSNs travel through an actual IMAP server and the event reaches an actual HTTP socket.

No process_dsn shortcut, no respx. Needs a local GreenMail (docker run greenmail/standalone) and Postgres:
  TEST_IMAP=127.0.0.1:53143 TEST_GREENMAIL_SMTP=127.0.0.1:53025 TEST_GREENMAIL_API=http://127.0.0.1:53080
GreenMail users: a1,a2,a3 (password pw) and locked (password realpw), domain x.test.
Skipped when TEST_IMAP is unset. Runtime IMAP is local-only; nothing here touches a real mailbox.
"""
from __future__ import annotations

import imaplib
import os
import smtplib
import uuid
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, update

from app import worker
from app.config import get_settings
from app.crypto import encrypt_secret
from app.models import Bounce, EmailAccount, OutboundEvent
from tests.helpers import Receiver, add_dispatch, outbox
from tests.test_outbound_events_bounces import dsn
from tests.test_send import run, seed

IMAP, SMTP, API = os.environ.get("TEST_IMAP"), os.environ.get("TEST_GREENMAIL_SMTP"), os.environ.get("TEST_GREENMAIL_API")
pytestmark = pytest.mark.skipif(not (IMAP and SMTP and API and os.environ.get("TEST_DATABASE_URL")),
                                reason="TEST_IMAP / TEST_GREENMAIL_SMTP / TEST_GREENMAIL_API / TEST_DATABASE_URL not set")


@pytest.fixture(autouse=True)
def clean_greenmail():
    httpx.post(f"{API}/api/mail/purge").raise_for_status()


@pytest.fixture
def receiver(monkeypatch):
    made = []

    def make(**kw):
        r = Receiver(**kw)
        made.append(r)
        s = get_settings()
        monkeypatch.setattr(s, "champmail_client_url", r.url)
        monkeypatch.setattr(s, "champmail_webhook_secret", "gate5-secret")
        return r
    yield make
    for r in made:
        r.close()


def deliver(user: str, raw: bytes) -> None:
    """Put a DSN into the mailbox the way a remote MTA would: SMTP to GreenMail, which files it in IMAP INBOX."""
    host, port = SMTP.split(":")
    with smtplib.SMTP(host, int(port), timeout=10) as c:
        c.sendmail("MAILER-DAEMON@mx.test", [f"{user}@x.test"], raw)


def mark_all_unseen(user: str) -> None:
    """Replay: the poll stored the DSNs but died before marking them seen, so IMAP serves the same bytes again."""
    host, port = IMAP.split(":")
    c = imaplib.IMAP4(host, int(port))
    c.login(user, "pw")
    c.select("INBOX")
    c.uid("STORE", "1:*", "-FLAGS", "(\\Seen)")
    c.logout()


async def add_box(Session, dom, user, password="pw"):
    host, port = IMAP.split(":")
    async with Session() as s:
        b = EmailAccount(id=uuid.uuid4(), name=user, email=f"{user}@x.test", domain_id=dom, imap_host=host,
                         imap_port=int(port), imap_use_ssl=False, imap_username=user,
                         imap_password_encrypted=encrypt_secret(password), smtp_host="smtp.test",
                         smtp_password_encrypted=encrypt_secret("pw"))
        s.add(b)
        await s.commit()
        return b.id


async def tick(Session, monkeypatch):
    monkeypatch.setattr(worker, "async_session_maker", Session)  # the real worker tick: poll_all, then drain
    async with httpx.AsyncClient(timeout=5) as c:
        await worker.tick(c)


async def stored(Session):
    async with Session() as s:
        return sorted((b.kind, b.status_code, b.message_id) for b in (await s.execute(select(Bounce))).scalars())


def test_gate5_hard_dsn_posts_one_bounced_webhook_soft_posts_none_and_polls_replay_cleanly(receiver, monkeypatch):
    rcv = receiver()

    async def go(Session):
        dom, _ = await seed(Session)
        a1 = await add_box(Session, dom, "a1")
        hard_id = await add_dispatch(Session, dom, a1, message_id=f"hard-{uuid.uuid4().hex[:8]}@champmail.test")
        soft_id = await add_dispatch(Session, dom, a1, message_id=f"soft-{uuid.uuid4().hex[:8]}@champmail.test")
        hard, soft = dsn("5.1.1", orig_id=f"<{hard_id}>"), dsn("4.2.2", action="delayed", orig_id=f"<{soft_id}>")
        deliver("a1", hard)
        deliver("a1", soft)
        await tick(Session, monkeypatch)  # poll 1: both DSNs fetched over IMAP, marked seen, one event posted
        after1 = (len(rcv.requests), await stored(Session))
        await tick(Session, monkeypatch)  # poll 2: nothing unseen
        after2 = len(rcv.requests)
        mark_all_unseen("a1")  # replay of both DSNs, byte for byte
        await tick(Session, monkeypatch)
        return hard_id, soft_id, after1, after2, len(rcv.requests), await stored(Session), await outbox(Session)
    hard_id, soft_id, after1, after2, final_posts, rows, events = run(go)
    assert after1[0] == 1 and after2 == 1 and final_posts == 1  # exactly one webhook, hard only
    (headers, body), = rcv.requests
    assert body["event_type"] == "bounced" and body["message_id"] == hard_id and set(body) == {"event_type", "message_id", "timestamp"}
    assert headers["x-webhook-secret"] == "gate5-secret" and headers["Idempotency-Key"] == f"bounced:{hard_id}"
    assert all(r[1] != soft_id for r in [(h, b["message_id"]) for h, b in rcv.requests])
    assert rows == sorted([("hard", "5.1.1", hard_id), ("soft", "4.2.2", soft_id)])  # both stored, once each (the replay hit the dsn_hash unique constraint)
    assert [(e.event_type, e.message_id, e.status) for e in events] == [("bounced", hard_id, "delivered")]


def test_gate5_event_survives_receiver_failure_over_real_imap_then_arrives(receiver, monkeypatch):
    rcv = receiver(script=[503])

    async def go(Session):
        dom, _ = await seed(Session)
        a2 = await add_box(Session, dom, "a2")
        mid = await add_dispatch(Session, dom, a2, message_id=f"hard-{uuid.uuid4().hex[:8]}@champmail.test")
        deliver("a2", dsn("5.1.1", orig_id=f"<{mid}>"))
        await tick(Session, monkeypatch)  # receiver answers 503; the DSN is already seen, only the outbox holds the event
        mid_state = (await outbox(Session))[0]
        await tick(Session, monkeypatch)  # not due yet
        n_before = len(rcv.requests)
        async with Session() as s:  # time passes
            await s.execute(update(OutboundEvent).values(next_attempt_at=datetime.utcnow() - timedelta(seconds=1)))
            await s.commit()
        await tick(Session, monkeypatch)
        return mid, mid_state, n_before, (await outbox(Session))[0]
    mid, mid_state, n_before, final = run(go)
    assert (mid_state.status, mid_state.attempts, mid_state.last_error) == ("pending", 1, "HTTP 503")
    assert n_before == 1 and len(rcv.requests) == 2  # 503, then 200
    assert [r[1]["message_id"] for r in rcv.requests] == [mid, mid]
    assert (final.status, final.attempts) == ("delivered", 2)


def test_gate5_auth_failure_on_the_real_server_pauses_only_that_mailbox_and_the_next_one_is_polled(receiver, monkeypatch):
    rcv = receiver()

    async def go(Session):
        dom, _ = await seed(Session)
        locked = await add_box(Session, dom, "locked", password="wrong-password")
        a3 = await add_box(Session, dom, "a3")
        mid = await add_dispatch(Session, dom, a3, message_id=f"hard-{uuid.uuid4().hex[:8]}@champmail.test")
        deliver("a3", dsn("5.1.1", orig_id=f"<{mid}>"))
        await tick(Session, monkeypatch)
        async with Session() as s:
            boxes = {b.name: b for b in (await s.execute(select(EmailAccount))).scalars() if b.imap_host}
        return mid, boxes
    mid, boxes = run(go)
    assert boxes["locked"].status == "paused" and boxes["locked"].status_reason.startswith("imap_auth_failed: ")
    assert boxes["a3"].status == "active" and boxes["a3"].status_reason is None
    assert [r[1]["message_id"] for r in rcv.requests] == [mid]
