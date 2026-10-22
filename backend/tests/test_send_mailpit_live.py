"""Idempotent send against a real Mailpit over real SMTP: same key + concurrent requests = exactly +1 message.

Needs TEST_DATABASE_URL, TEST_MAILPIT_SMTP=host:port (SMTP) and TEST_MAILPIT_API=http://host:port (HTTP API),
plus a reachable Redis at REDIS_URL (the Redis gate is NOT faked here). Wipes the Mailpit inbox it is pointed at.
"""
from __future__ import annotations

import asyncio
import os

import httpx
import pytest

from app.api.v1 import send as send_api
from app.db.redis import RedisClient
from app.main import app
from tests.test_send import HARBINGER, run, seed

SMTP, API = os.environ.get("TEST_MAILPIT_SMTP"), os.environ.get("TEST_MAILPIT_API")
pytestmark = pytest.mark.skipif(not (os.environ.get("TEST_DATABASE_URL") and SMTP and API),
                                reason="needs TEST_DATABASE_URL, TEST_MAILPIT_SMTP and TEST_MAILPIT_API")

BODY = {**HARBINGER, "brand_id": "b1", "subject": "live-idem", "unsubscribe_url": "https://u.example/x"}


def total() -> int:
    return httpx.get(f"{API}/api/v1/messages").json()["total"]


def test_same_key_and_concurrent_requests_deliver_exactly_one_message(monkeypatch):
    monkeypatch.setenv("EMAIL_ENCRYPTION_KEY", "test-encryption-key")
    host, port = SMTP.rsplit(":", 1)
    assert httpx.delete(f"{API}/api/v1/messages").status_code == 200 and total() == 0

    async def go(Session):
        await seed(Session, n=3, box_kw={"smtp_host": host, "smtp_port": int(port), "smtp_use_tls": False})
        redis = RedisClient()
        monkeypatch.setattr(send_api, "redis_client", redis)

        async def session_dep():
            async with Session() as s:
                yield s
        app.dependency_overrides[send_api.get_session] = session_dep

        async def post(body):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", timeout=30) as c:
                return await c.post("/api/v1/send", json=body, headers={"Idempotency-Key": "sledgehammer:live:1"})
        keyed = {**BODY, "idempotency_key": "sledgehammer:live:1"}
        try:
            burst = await asyncio.gather(*[post(keyed) for _ in range(8)])
            after_burst = total()
            replay = await post(keyed)
            changed = await post({**keyed, "subject": "changed"})
            return burst, after_burst, replay, changed, total()
        finally:
            app.dependency_overrides.clear()
            await redis.close()
    burst, after_burst, replay, changed, final = run(go)
    winners = [r for r in burst if r.status_code == 200]
    # Requests observing the completed dispatch replay 200, without another SMTP submission.
    assert winners and all(r.status_code in (200, 503) for r in burst), [r.status_code for r in burst]
    assert all(r.json() == winners[0].json() for r in winners)
    assert {r.json()["code"] for r in burst if r.status_code == 503} <= {"dispatch_in_progress"}
    assert after_burst == 1 and final == 1  # one real delivery for 8 concurrent + 1 replay + 1 conflicting request
    assert replay.status_code == 200 and replay.json() == winners[0].json()
    assert changed.status_code == 409
    msg = httpx.get(f"{API}/api/v1/messages").json()["messages"][0]
    headers = httpx.get(f"{API}/api/v1/message/{msg['ID']}/headers").json()
    assert headers["Message-Id"] == [f"<{winners[0].json()['message_id']}>"]
    assert headers["List-Unsubscribe-Post"] == ["List-Unsubscribe=One-Click"]
