"""InboxKit webhook import boundary against real Postgres: retryable failures, atomic upsert, no credential loss."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.postgres as pg
from app.api.v1 import inboxkit_webhooks as wh
from app.crypto import decrypt_secret
from app.main import app
from app.models import EmailAccount
from app.services.inboxkit.client import InboxKitAPIError
from app.services.mail_infra import MailboxCredentials, MailboxRecord
from tests.test_send import run

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL not set")

UID = "mb_1"


def record(**kw):
    return MailboxRecord(**{"uid": UID, "email": "alex@acme.test", "status": "ready", "native_status": "active",
                            "platform": "google", **kw})


def creds(**kw):
    return MailboxCredentials(**{"email": "alex@acme.test", "username": "alex@acme.test", "password": "app-pw",
                                 "smtp_host": "smtp.gmail.com", "smtp_port": 587, "imap_host": "imap.gmail.com",
                                 "imap_port": 993, "platform": "google", **kw})


class Provider:
    """Scripted InboxKit: `rec`/`cred` are values or exceptions; `calls` counts authoritative re-fetches."""
    rec, cred, delay, calls = None, None, 0.0, 0

    def __init__(self):
        type(self).calls += 0

    async def get_mailbox(self, uid, *, strict=False):
        type(self).calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if isinstance(self.rec, Exception):
            raise self.rec
        return self.rec

    async def get_credentials(self, uid):
        if isinstance(self.cred, Exception):
            raise self.cred
        return self.cred

    async def get_domain(self, uid, *, strict=False):
        if isinstance(self.rec, Exception):
            raise self.rec
        return self.rec


@pytest.fixture
def provider(monkeypatch):
    class P(Provider):
        calls = 0
    monkeypatch.setattr(wh, "InboxKitProvider", P)
    return P


@pytest.fixture
def seen(monkeypatch):
    marked = set()

    async def already(key):
        return key in marked

    async def mark(key):
        marked.add(key)
    monkeypatch.setattr(wh, "_already_seen", already)
    monkeypatch.setattr(wh, "_mark_seen", mark)
    return marked


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("EMAIL_ENCRYPTION_KEY", "test-encryption-key")


def install(Session, monkeypatch):
    monkeypatch.setattr(pg, "async_session_maker", Session)


def signature(key=None):
    return "sha256=" + hashlib.sha256((key or wh.settings.inboxkit_api_key).encode()).hexdigest()


async def hook(event="mailbox.status_changed", data=None, *, ts=None, sig=None):
    body = {"event": event, "timestamp": (ts or datetime.now(timezone.utc)).isoformat(),
            "data": data or {"mailbox": {"uid": UID, "status": "active"}}}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.post("/api/v1/webhooks/inboxkit", content=json.dumps(body),
                            headers={"X-InboxKit-Signature": sig or signature()})


async def accounts(Session):
    async with Session() as s:
        return (await s.execute(select(EmailAccount))).scalars().all()


def test_first_event_imports_one_row_with_encrypted_credentials(monkeypatch, provider, seen):
    provider.rec, provider.cred = record(), creds()

    async def go(Session):
        install(Session, monkeypatch)
        return await hook(), await accounts(Session)
    r, (acc,) = run(go)
    assert r.status_code == 200 and r.json()["result"]["status"] == "updated"
    assert acc.inboxkit_uid == UID and acc.is_active and acc.credentials_persisted
    assert acc.smtp_host == "smtp.gmail.com" and acc.smtp_username == "alex@acme.test"
    assert decrypt_secret(acc.smtp_password_encrypted) == "app-pw" and "app-pw" not in acc.smtp_password_encrypted
    assert len(seen) == 1


@pytest.mark.parametrize("fail", ["refetch", "credentials"])
def test_provider_failure_is_503_nothing_written_and_not_deduped(monkeypatch, provider, seen, fail):
    provider.rec = InboxKitAPIError(503, "upstream down") if fail == "refetch" else record()
    provider.cred = InboxKitAPIError(500, "creds down") if fail == "credentials" else creds()

    async def go(Session):
        install(Session, monkeypatch)
        down = await hook()
        provider.rec, provider.cred = record(), creds()  # InboxKit recovers; same event is redelivered
        return down, await hook(), await accounts(Session)
    down, up, rows = run(go)
    assert down.status_code == 503 and up.status_code == 200 and len(rows) == 1 and rows[0].credentials_persisted
    assert len(seen) == 1


def test_network_error_is_503_too(monkeypatch, provider, seen):
    provider.rec = httpx.ConnectError("no route")

    async def go(Session):
        install(Session, monkeypatch)
        return await hook(), await accounts(Session)
    r, rows = run(go)
    assert r.status_code == 503 and rows == [] and not seen


def test_failed_commit_is_retryable_then_identical_retry_succeeds_without_loss(monkeypatch, provider, seen):
    provider.rec, provider.cred = record(), creds()
    real_commit, calls = AsyncSession.commit, []

    async def flaky(self):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("connection reset during commit")
        return await real_commit(self)
    monkeypatch.setattr(AsyncSession, "commit", flaky)

    async def go(Session):
        install(Session, monkeypatch)
        first = await hook()
        after_failure = (await accounts(Session), set(seen))
        second = await hook()
        return first, after_failure, second, await accounts(Session)
    first, (rows_mid, seen_mid), second, rows = run(go)
    assert first.status_code == 503 and rows_mid == [] and not seen_mid  # atomic: no half-imported row, no dedupe mark
    assert second.status_code == 200 and len(rows) == 1
    assert decrypt_secret(rows[0].smtp_password_encrypted) == "app-pw" and rows[0].credentials_persisted
    assert len(seen) == 1


def test_duplicate_after_commit_is_deduped(monkeypatch, provider, seen):
    provider.rec, provider.cred = record(), creds()

    async def go(Session):
        install(Session, monkeypatch)
        return await hook(), await hook()
    a, b = run(go)
    assert a.json()["result"]["status"] == "updated" and b.json()["result"]["status"] == "duplicate"
    assert provider.calls == 1


def test_concurrent_duplicate_import_yields_one_row_with_credentials(monkeypatch, provider, seen):
    provider.rec, provider.cred, provider.delay = record(), creds(), 0.1  # all six pass the "no row yet" check together

    async def go(Session):
        install(Session, monkeypatch)
        rs = await asyncio.gather(*[hook() for _ in range(6)])
        async with Session() as s:
            n = (await s.execute(select(func.count()).select_from(EmailAccount))).scalar_one()
        return rs, n, await accounts(Session)
    rs, n, rows = run(go)
    assert [r.status_code for r in rs] == [200] * 6 and n == 1
    assert decrypt_secret(rows[0].smtp_password_encrypted) == "app-pw" and rows[0].credentials_persisted


def test_inboxkit_uid_is_unique_in_the_schema(monkeypatch):
    async def go(Session):
        async with Session() as s:
            for _ in range(2):
                s.add(EmailAccount(name="a", email="a@x.test", inboxkit_uid="dup"))
            with pytest.raises(IntegrityError):
                await s.commit()
    run(go)


def test_partial_provider_records_never_blank_stored_credentials(monkeypatch, provider, seen):
    provider.rec, provider.cred = record(), creds()

    async def go(Session):
        install(Session, monkeypatch)
        await hook()
        before = (await accounts(Session))[0]
        snap = (before.smtp_host, before.smtp_port, before.imap_host, before.smtp_username, before.imap_username,
                before.smtp_password_encrypted, before.imap_password_encrypted)
        # a later event for the same ready mailbox whose credentials come back blank (new status = not a duplicate)
        provider.cred = creds(password="", smtp_host="", imap_host="", username="")
        r = await hook(data={"mailbox": {"uid": UID, "status": "resynced"}})
        after = (await accounts(Session))[0]
        return r, snap, (after.smtp_host, after.smtp_port, after.imap_host, after.smtp_username, after.imap_username,
                         after.smtp_password_encrypted, after.imap_password_encrypted), after
    r, snap, now, after = run(go)
    assert r.status_code == 200 and now == snap and after.credentials_persisted


def test_status_only_event_after_import_keeps_credentials(monkeypatch, provider, seen):
    provider.rec, provider.cred = record(), creds()

    async def go(Session):
        install(Session, monkeypatch)
        await hook()
        provider.rec, provider.cred = record(status="warming", native_status="warmup"), None
        await hook(data={"mailbox": {"uid": UID, "status": "warmup"}})
        return (await accounts(Session))[0]
    acc = run(go)
    assert decrypt_secret(acc.smtp_password_encrypted) == "app-pw" and acc.credentials_persisted


def test_blank_password_on_a_new_mailbox_is_not_imported(monkeypatch, provider, seen):
    provider.rec, provider.cred = record(), creds(password="")

    async def go(Session):
        install(Session, monkeypatch)
        return await hook(), await accounts(Session)
    r, rows = run(go)
    assert r.status_code == 503 and rows == [] and not seen


def test_unknown_mailbox_is_a_definitive_not_found_not_an_error(monkeypatch, provider, seen):
    provider.rec = None

    async def go(Session):
        install(Session, monkeypatch)
        return await hook(), await accounts(Session)
    r, rows = run(go)
    assert r.status_code == 200 and r.json()["result"]["status"] == "not_found" and rows == [] and not seen


def test_domain_event_provider_failure_is_503(monkeypatch, provider, seen):
    provider.rec = InboxKitAPIError(502, "bad gateway")

    async def go(Session):
        install(Session, monkeypatch)
        return await hook("domain.status_changed", {"domain": {"uid": "d1", "status": "active"}})
    r = run(go)
    assert r.status_code == 503 and not seen


def test_stale_and_unauthorized_replays_are_permanent_4xx_and_touch_nothing(monkeypatch, provider, seen):
    provider.rec, provider.cred = record(), creds()

    async def go(Session):
        install(Session, monkeypatch)
        stale = await hook(ts=datetime.now(timezone.utc) - timedelta(minutes=10))
        forged = await hook(sig=signature("some-other-key"))
        missing = await hook(sig="sha256=")
        return stale, forged, missing, await accounts(Session)
    stale, forged, missing, rows = run(go)
    assert stale.status_code == 400 and forged.status_code == 401 and missing.status_code == 401
    assert rows == [] and provider.calls == 0 and not seen
