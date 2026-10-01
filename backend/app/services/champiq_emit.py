"""Event egress to ChampIQ (SUGGESTIONS 2.2, mirrors Harbinger's emit.ts).

ChampMail is the suite's send-of-record; ChampIQ's graph write-back and
run_ledger consumers subscribe to email.* topics but nothing here ever
published them (2026-07-23 live run, finding #7 — a real send was invisible
to both). Fire-and-forget: a down or unset ChampIQ must never fail a send.
"""
import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


async def emit_email_event(
    topic: str,
    *,
    to_email: str,
    from_email: str,
    subject: str = "",
    body: str = "",
    direction: str = "outbound",
    message_id: Optional[str] = None,
    occurred_at: Optional[datetime] = None,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    """Publish one email.* event to ChampIQ's webhook ingress.

    Receiver: POST /api/webhooks/tools/champmail -> ChampMailDriver.parse_webhook
    -> event bus -> GraphWritebackConsumer (Cham_Graph episode) + LedgerConsumer
    (run_ledger row). No-op when CHAMPIQ_URL is unset.

    `extra` merges additional top-level fields into the payload (e.g. reply
    classification) - GraphWritebackConsumer's `_field()` helper already reads
    arbitrary top-level keys, but note its `_email_hook_payload()` currently
    only forwards a fixed field set to Cham_Graph, so anything passed here
    lands in run_ledger's raw payload immediately and reaches the graph edge
    only once that consumer is updated to pass it through too.
    """
    if not settings.champiq_url:
        return

    body_payload: dict[str, Any] = {
        "type": topic,
        "to_address": to_email,
        "from_address": from_email,
        "subject": subject,
        "body": body,
        "direction": direction,
        "occurred_at": (occurred_at or datetime.now(timezone.utc)).isoformat(),
    }
    if message_id:
        body_payload["message_id"] = message_id
    if extra:
        body_payload.update(extra)

    import json

    raw = json.dumps(body_payload).encode()
    headers = {"Content-Type": "application/json", "X-ChampIQ-Event": topic}
    if settings.champiq_webhook_secret:
        headers["X-ChampIQ-Signature"] = hmac.new(
            settings.champiq_webhook_secret.encode(), raw, hashlib.sha256
        ).hexdigest()

    url = f"{settings.champiq_url.rstrip('/')}/api/webhooks/tools/champmail"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, content=raw, headers=headers)
        if resp.status_code >= 400:
            logger.warning("champiq emit %s -> HTTP %s", topic, resp.status_code)
    except Exception:
        logger.exception("champiq emit %s failed", topic)
