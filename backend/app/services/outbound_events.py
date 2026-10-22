"""Outbound events webhook: Redis queue, idempotent on (message_id, event_type), retry with backoff.

Payload and header match Harbinger's receiver (src/app/api/email/track/route.ts):
POST <client_url>/api/email/track  {event_type, message_id, timestamp}  x-webhook-secret
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging

import httpx

from app.config import get_settings

log = logging.getLogger("champmail.events")

EVENT_TYPES = ("delivered", "opened", "clicked", "replied", "bounced", "complained", "unsubscribed")
QUEUE = "champmail:events:outbound"
DEAD = "champmail:events:dead"  # gave up after retries; kept for manual replay


def _seen_key(message_id: str, event_type: str) -> str:
    return f"champmail:events:seen:{event_type}:{message_id}"


async def emit(r, event_type: str, message_id: str, timestamp: str | None = None) -> bool:
    """Queue an event. Returns False if (message_id, event_type) was already emitted or queued."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event_type {event_type!r}")
    if not message_id:
        raise ValueError("message_id is required")
    key = _seen_key(message_id, event_type)
    # SET NX is the idempotency gate: it is never cleared once the event is queued or sent.
    if not await r.set(key, "queued", nx=True):
        return False
    event = {
        "event_type": event_type,
        "message_id": message_id,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
    }
    try:
        await r.rpush(QUEUE, json.dumps(event))
    except Exception:
        await r.delete(key)  # nothing was queued, so allow a later emit
        raise
    return True


async def _post(client: httpx.AsyncClient, event: dict, max_attempts: int, base_delay: float, sleep) -> bool:
    s = get_settings()
    url = s.champmail_client_url.rstrip("/") + "/api/email/track"
    for attempt in range(max_attempts):
        try:
            resp = await client.post(url, json=event, headers={"x-webhook-secret": s.champmail_webhook_secret})
            if resp.status_code < 300:
                return True
            # 4xx (except 429) will not get better by retrying.
            if resp.status_code < 500 and resp.status_code != 429:
                log.error("event rejected %s: %s", resp.status_code, event)
                return False
            log.warning("event post got %s (attempt %d)", resp.status_code, attempt + 1)
        except httpx.HTTPError as exc:
            log.warning("event post failed: %s (attempt %d)", exc, attempt + 1)
        if attempt < max_attempts - 1:
            await sleep(base_delay * 2**attempt)
    return False


async def drain(r, client: httpx.AsyncClient, *, max_attempts: int = 5, base_delay: float = 1.0,
                sleep=asyncio.sleep) -> int:
    """Deliver queued events. Returns the number delivered.

    shortcut: retries block the drain loop and an event popped just before a crash is lost
    (never duplicated), upgrade to a delayed ZSET + processing list if volume grows.
    """
    if not get_settings().champmail_client_url:
        log.warning("CHAMPMAIL_CLIENT_URL unset, events stay queued")
        return 0
    sent = 0
    while raw := await r.lpop(QUEUE):
        event = json.loads(raw)
        if await _post(client, event, max_attempts, base_delay, sleep):
            await r.set(_seen_key(event["message_id"], event["event_type"]), "sent")
            sent += 1
        else:
            await r.rpush(DEAD, raw)
    return sent
