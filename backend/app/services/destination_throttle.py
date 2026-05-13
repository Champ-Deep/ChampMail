"""Per-destination send-rate throttling using Redis counters.

Provider limits (conservative, based on known deliverability research):
  Gmail   : 3,000 recipients/day, no sub-hourly rate specified → cap 200/hr
  Outlook : ~500/day aggressively filtered → cap 50/hr
  Yahoo   : 100/hr hard limit
  Default : 500/hr (catch-all for other providers)
"""

from __future__ import annotations

import logging
from typing import Optional

from app.db.redis import redis_client

logger = logging.getLogger(__name__)

# (daily_limit, hourly_limit)  — None means "no cap at that granularity"
_PROVIDER_LIMITS: dict[str, tuple[Optional[int], Optional[int]]] = {
    "gmail.com":       (3000, 200),
    "googlemail.com":  (3000, 200),
    "outlook.com":     (500,   50),
    "hotmail.com":     (500,   50),
    "live.com":        (500,   50),
    "msn.com":         (500,   50),
    "yahoo.com":       (None, 100),
    "yahoo.co.uk":     (None, 100),
    "ymail.com":       (None, 100),
    "aol.com":         (None, 100),
    "icloud.com":      (1000, 150),
    "me.com":          (1000, 150),
}
_DEFAULT_LIMITS: tuple[Optional[int], Optional[int]] = (None, 500)

# Redis key TTLs (seconds)
_DAY_TTL  = 86400   # 24 h
_HOUR_TTL = 3600    # 1 h


def _provider(email: str) -> str:
    return email.split("@")[-1].lower() if "@" in email else ""


def _keys(provider: str) -> tuple[str, str]:
    """Return (daily_key, hourly_key) for a given provider."""
    return (
        f"throttle:daily:{provider}",
        f"throttle:hourly:{provider}",
    )


async def can_send(recipient_email: str) -> bool:
    """Return True if we are within rate limits for the recipient's provider.

    This is a non-blocking check+increment: if within limits, the counters are
    incremented atomically and True is returned.  Call once per email just before
    actually sending.
    """
    provider = _provider(recipient_email)
    daily_limit, hourly_limit = _PROVIDER_LIMITS.get(provider, _DEFAULT_LIMITS)
    day_key, hour_key = _keys(provider)

    try:
        # Increment both counters atomically using a pipeline
        pipe = redis_client.client.pipeline()
        pipe.incr(day_key)
        pipe.expire(day_key, _DAY_TTL)
        pipe.incr(hour_key)
        pipe.expire(hour_key, _HOUR_TTL)
        results = await pipe.execute()

        day_count  = results[0]
        hour_count = results[2]

        # If either counter exceeds its limit, decrement back and refuse
        over_daily  = daily_limit  is not None and day_count  > daily_limit
        over_hourly = hourly_limit is not None and hour_count > hourly_limit

        if over_daily or over_hourly:
            # Roll back
            pipe2 = redis_client.client.pipeline()
            pipe2.decr(day_key)
            pipe2.decr(hour_key)
            await pipe2.execute()

            reason = f"daily ({day_count}/{daily_limit})" if over_daily else f"hourly ({hour_count}/{hourly_limit})"
            logger.debug("Throttled %s: %s limit reached", provider, reason)
            return False

        return True

    except Exception as exc:
        # Redis failure → fail open (don't block sends due to throttle errors)
        logger.warning("Throttle check failed for %s, failing open: %s", provider, exc)
        return True


async def get_provider_usage(provider: str) -> dict:
    """Return current daily/hourly usage for a provider (for monitoring)."""
    day_key, hour_key = _keys(provider)
    daily_limit, hourly_limit = _PROVIDER_LIMITS.get(provider, _DEFAULT_LIMITS)

    try:
        day_count  = int(await redis_client.client.get(day_key)  or 0)
        hour_count = int(await redis_client.client.get(hour_key) or 0)
    except Exception:
        day_count = hour_count = -1

    return {
        "provider": provider,
        "daily_sent": day_count,
        "daily_limit": daily_limit,
        "hourly_sent": hour_count,
        "hourly_limit": hourly_limit,
    }
