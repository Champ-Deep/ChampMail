"""Suite event bus — versioned `email.*` events on Redis Streams.

ChampMail's only event surface today is the n8n-shaped webhook. This adds the
suite's outbound nervous system: every meaningful email lifecycle event is
published as a versioned envelope to a Redis Stream that any Champ app
(ChampGraph, LakeB2B, Harbinger, sim-pack, analytics) can consume — decoupled,
replayable, ordered. The envelope is keyed by the identity-spine ids so consumers
can join across the suite without ChampMail's internal uuids.

The envelope builder is pure (unit-tested offline); `emit` does the Redis XADD
(best-effort — a bus failure must never block a send).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)

SCHEMA = "champ.email.v1"
STREAM = "champ:events:email"


class EmailEventType(str, Enum):
    SENT = "email.sent"
    DELIVERED = "email.delivered"
    OPENED = "email.opened"
    CLICKED = "email.clicked"
    BOUNCED = "email.bounced"
    COMPLAINED = "email.complained"
    REPLIED = "email.replied"
    UNSUBSCRIBED = "email.unsubscribed"
    FILE_VIEWED = "email.file_viewed"  # from ChampUTM file-share read receipts


def build_event(
    event_type: EmailEventType,
    *,
    person_id: Optional[str] = None,
    account_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    send_log_id: Optional[str] = None,
    team_id: Optional[str] = None,
    email: Optional[str] = None,
    payload: Optional[dict] = None,
    ts: Optional[str] = None,
) -> dict:
    """Construct the versioned event envelope. Pure — no I/O."""
    return {
        "schema": SCHEMA,
        "id": str(uuid.uuid4()),
        "type": event_type.value,
        "ts": ts or datetime.now(timezone.utc).isoformat(),
        "person_id": person_id or "",
        "account_id": account_id or "",
        "campaign_id": campaign_id or "",
        "send_log_id": send_log_id or "",
        "team_id": team_id or "",
        "email": email or "",
        "payload": payload or {},
    }


async def emit(event_type: EmailEventType, **kwargs: Any) -> None:
    """Publish an event to the bus. Best-effort: never raise into a send path."""
    try:
        from app.db.redis import redis_client

        envelope = build_event(event_type, **kwargs)
        await redis_client.xadd(STREAM, envelope)
    except Exception as exc:  # noqa: BLE001
        logger.warning("event emit failed (%s): %s", event_type.value, exc)
