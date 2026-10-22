"""poll_all: one broken mailbox must not stop the others (real session, sqlite stand-in for Postgres)."""
import asyncio
import imaplib

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.db.postgres as pg
from app.crypto import encrypt_secret
from app.models.email_account import EmailAccount
from app.services import outbound_events as oe
from app.services.bounce_poller import poll_all
from tests.test_outbound_events_bounces import FakeRedis, dsn


class FakeImap:
    """Stands in for IMAP4_SSL: host 'bad' fails login, anything else serves one unseen DSN."""
    opened: list[str] = []

    def __init__(self, host, port):
        self.host = host
        FakeImap.opened.append(host)

    def login(self, user, password):
        if self.host == "bad.test":
            raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")

    def select(self, mailbox):
        pass

    def uid(self, cmd, *args):
        if cmd == "SEARCH":
            return "OK", [b"7"]
        if cmd == "FETCH":
            return "OK", [(b"7 (BODY[])", dsn("5.1.1", orig_id="<second-box-1@champmail.test>"))]
        return "OK", [b""]

    def logout(self):
        pass


def test_broken_first_mailbox_does_not_stop_the_second(tmp_path, monkeypatch):
    monkeypatch.setenv("EMAIL_ENCRYPTION_KEY", "test-key")
    monkeypatch.setattr(imaplib, "IMAP4_SSL", FakeImap)
    FakeImap.opened = []

    async def go():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/t.db")
        async with engine.begin() as c:
            await c.run_sync(pg.Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            for name, host in (("a", "bad.test"), ("b", "good.test")):  # bad one is polled first
                s.add(EmailAccount(name=name, email=f"{name}@x.test", imap_host=host,
                                   imap_password_encrypted=encrypt_secret("pw")))
                await s.commit()
            r = FakeRedis()
            return await poll_all(s, r), r

    total, r = asyncio.run(go())
    assert FakeImap.opened == ["bad.test", "good.test", "good.test"]  # good: fetch, then mark seen
    assert total == 1
    assert len(r.lists[oe.QUEUE]) == 1 and "second-box-1@champmail.test" in r.lists[oe.QUEUE][0]
