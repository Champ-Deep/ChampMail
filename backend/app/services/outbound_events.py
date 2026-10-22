"""Outbound events webhook: durable Postgres outbox, at-least-once delivery.

Payload and header match Harbinger's receiver (src/app/api/email/track/route.ts):
POST <client_url>/api/email/track  {event_type, message_id, timestamp}  x-webhook-secret
plus a stable `Idempotency-Key: <event_type>:<message_id>` for receivers that use it.

emit() is one INSERT ... ON CONFLICT DO NOTHING inside the caller's transaction, so the pending
record and its uniqueness are atomic with whatever produced the event (e.g. the stored bounce).
drain() claims a row under a lease, POSTs, and marks it delivered only after a 2xx. A worker that
dies mid-flight leaves a lease that expires and is reclaimed. If the receiver applied an event but
the acknowledgement was lost, the retry delivers it AGAIN: this transport is at-least-once, never
exactly-once. Harbinger's route does not dedupe (see docs/outbound-events.md for what a repeat re-runs).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Callable, Optional

import httpx
from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.models.outbound_event import EVENT_TYPES, OutboundEvent
from app.models.send_dispatch import SendDispatch

log = logging.getLogger("champmail.events")

MAX_ATTEMPTS = 20  # with the 1h cap below: about a day of receiver downtime before an event goes dead
BASE_DELAY_S = 10.0
MAX_DELAY_S = 3600.0
LEASE_S = 120.0  # longer than the worker's HTTP timeout (10s)
PERMANENT = (400, 422)  # receiver says the payload itself is bad; every other failure is retried


class UnknownDispatch(Exception):
    """No send_dispatches row (that was not refused) carries this message_id."""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # columns are naive UTC


def to_naive_utc(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc).replace(tzinfo=None) if ts.tzinfo else ts


async def emit(session, event_type: str, message_id: str, timestamp: Optional[datetime] = None) -> bool:
    """Record the event as pending. False if (message_id, event_type) already exists. Caller commits."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event_type {event_type!r}")
    if not message_id:
        raise ValueError("message_id is required")
    known = await session.execute(
        select(SendDispatch.id).where(SendDispatch.message_id == message_id, SendDispatch.status != "failed")
    )
    if known.first() is None:
        raise UnknownDispatch(message_id)
    now = _now()
    res = await session.execute(
        pg_insert(OutboundEvent)
        .values(message_id=message_id, event_type=event_type, event_at=to_naive_utc(timestamp) if timestamp else now,
                status="pending", attempts=0, next_attempt_at=now, created_at=now, updated_at=now)
        .on_conflict_do_nothing(constraint="uq_outbound_events_message_event")
        .returning(OutboundEvent.id)
    )
    return res.scalar_one_or_none() is not None


async def _claim(Session, now: datetime, lease_s: float, max_attempts: int):
    """Lease the next due event (pending, or leased with an expired lease). One row, one short txn."""
    async with Session() as s:
        await s.execute(  # a lease that expired on the last allowed attempt is not retried again
            update(OutboundEvent)
            .where(OutboundEvent.status == "leased", OutboundEvent.lease_expires_at <= now,
                   OutboundEvent.attempts >= max_attempts)
            .values(status="dead", last_error="lease expired on final attempt", updated_at=now)
        )
        ev = (await s.execute(
            select(OutboundEvent)
            .where(or_(and_(OutboundEvent.status == "pending", OutboundEvent.next_attempt_at <= now),
                       and_(OutboundEvent.status == "leased", OutboundEvent.lease_expires_at <= now)))
            .order_by(OutboundEvent.next_attempt_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )).scalar_one_or_none()
        if ev is None:
            await s.commit()
            return None
        ev.status, ev.lease_expires_at, ev.attempts, ev.updated_at = "leased", now + timedelta(seconds=lease_s), ev.attempts + 1, now
        claimed = (ev.id, ev.message_id, ev.event_type, ev.event_at, ev.attempts)
        await s.commit()
        return claimed


async def _post(client: httpx.AsyncClient, ev) -> tuple[Optional[int], str]:
    _, message_id, event_type, event_at, _ = ev
    s = get_settings()
    body = {"event_type": event_type, "message_id": message_id,
            "timestamp": event_at.replace(tzinfo=timezone.utc).isoformat()}
    try:
        resp = await client.post(
            s.champmail_client_url.rstrip("/") + "/api/email/track", json=body,
            headers={"x-webhook-secret": s.champmail_webhook_secret, "Idempotency-Key": f"{event_type}:{message_id}"},
        )
        return resp.status_code, f"HTTP {resp.status_code}"
    except httpx.HTTPError as exc:
        return None, f"{type(exc).__name__}: {exc}"[:500]


async def drain(Session, client: httpx.AsyncClient, *, max_attempts: int = MAX_ATTEMPTS,
                base_delay: float = BASE_DELAY_S, lease_s: float = LEASE_S,
                now: Callable[[], datetime] = _now) -> int:
    """Deliver due events one at a time; returns how many were acknowledged.

    Stops at the first transient failure (the receiver is probably down; the rest wait for the
    next tick instead of each burning a timeout).
    """
    if not get_settings().champmail_client_url:
        log.warning("CHAMPMAIL_CLIENT_URL unset, events stay pending")
        return 0
    delivered = 0
    while ev := await _claim(Session, now(), lease_s, max_attempts):
        status, detail = await _post(client, ev)
        ok = status is not None and 200 <= status < 300
        permanent = status in PERMANENT
        dead = permanent or ev[4] >= max_attempts
        t = now()
        async with Session() as s:
            if ok:  # a fact, whatever else happened to the lease meanwhile
                await s.execute(update(OutboundEvent).where(OutboundEvent.id == ev[0]).values(
                    status="delivered", delivered_at=t, lease_expires_at=None, last_error=None, updated_at=t))
            else:
                delay = min(base_delay * 2 ** (ev[4] - 1), MAX_DELAY_S)
                # attempts == ours: a worker whose lease was reclaimed must not overwrite the new owner's state
                await s.execute(update(OutboundEvent)
                                .where(OutboundEvent.id == ev[0], OutboundEvent.status == "leased", OutboundEvent.attempts == ev[4])
                                .values(status="dead" if dead else "pending", last_error=detail, lease_expires_at=None,
                                        next_attempt_at=t + timedelta(seconds=delay), updated_at=t))
            await s.commit()
        if ok:
            delivered += 1
            continue
        log.warning("event %s:%s not acknowledged (%s, attempt %d)%s", ev[2], ev[1], detail, ev[4], " -> dead" if dead else "")
        if not permanent:
            break
    return delivered
