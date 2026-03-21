"""
Domain rate limiter using Redis atomic counters.

Enforces warmup-day limits AND daily send limits in a single source of truth.
Both campaign sends and warmup sends use the same counter, preventing either
from exceeding the effective limit.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

from app.db.redis import redis_client

logger = logging.getLogger(__name__)

# Warmup progression table (day index → max sends that day)
# Shared with warmup.py — authoritative source.
WARMUP_LIMITS = [10, 25, 50, 100, 200, 500, 750, 1000]
MAX_WARMUP_LIMIT = 1000


def get_warmup_limit(day: int) -> int:
    """Return the max daily sends for a given warmup day."""
    if day >= len(WARMUP_LIMITS):
        return MAX_WARMUP_LIMIT
    return WARMUP_LIMITS[day]


def _seconds_until_midnight_utc() -> int:
    """Seconds remaining until the next midnight UTC."""
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    midnight_tomorrow = midnight.replace(day=now.day + 1) if now.hour > 0 or now.minute > 0 else midnight
    # Handle month rollover edge cases
    from datetime import timedelta
    tomorrow_midnight = (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
    diff = (tomorrow_midnight - now).total_seconds()
    return max(int(diff), 60)  # at least 60s to avoid edge-case zero TTL


class DomainRateLimiter:
    """Atomic domain-level rate limiting backed by Redis.

    Keys:
        domain:{id}:sent_today  — daily counter, auto-expires at midnight UTC
        domain:{id}:sent_hour   — hourly counter, 3600s TTL
        domain:{id}:meta        — cached domain metadata (5 min TTL)
    """

    # ------------------------------------------------------------------
    # Domain metadata cache (avoids hitting Postgres every send)
    # ------------------------------------------------------------------

    async def _get_domain_meta(self, domain_id: str) -> Optional[dict]:
        """Load domain metadata, cached in Redis for 5 minutes."""
        cache_key = f"domain:{domain_id}:meta"
        cached = await redis_client.get_json(cache_key)
        if cached:
            return cached

        # Fetch from Postgres
        from app.db.postgres import async_session_maker
        from app.models.domain import Domain
        from sqlalchemy import select

        try:
            async with async_session_maker() as session:
                result = await session.execute(
                    select(Domain).where(Domain.id == domain_id)
                )
                domain = result.scalar_one_or_none()
                if not domain:
                    return None

                meta = {
                    "domain_id": str(domain.id),
                    "domain_name": domain.domain_name,
                    "daily_send_limit": domain.daily_send_limit or 50,
                    "warmup_enabled": bool(domain.warmup_enabled),
                    "warmup_day": domain.warmup_day or 0,
                    "status": domain.status or "pending",
                }
                await redis_client.set_json(cache_key, meta, ex=300)  # 5 min cache
                return meta
        except Exception as e:
            logger.error("Failed to load domain meta for %s: %s", domain_id, e)
            return None

    # ------------------------------------------------------------------
    # Effective limit
    # ------------------------------------------------------------------

    async def get_effective_limit(self, domain_id: str) -> int:
        """Return the effective daily limit: min(daily_limit, warmup_limit) when warming up."""
        meta = await self._get_domain_meta(domain_id)
        if not meta:
            return 0  # unknown domain → block

        daily_limit = meta["daily_send_limit"]

        if meta["warmup_enabled"] and meta["warmup_day"] < len(WARMUP_LIMITS):
            warmup_limit = get_warmup_limit(meta["warmup_day"])
            return min(daily_limit, warmup_limit)

        return daily_limit

    # ------------------------------------------------------------------
    # Counter operations
    # ------------------------------------------------------------------

    async def _get_daily_count(self, domain_id: str) -> int:
        """Read today's send count for a domain."""
        raw = await redis_client.get(f"domain:{domain_id}:sent_today")
        return int(raw) if raw else 0

    async def _get_hourly_count(self, domain_id: str) -> int:
        """Read this hour's send count for a domain."""
        raw = await redis_client.get(f"domain:{domain_id}:sent_hour")
        return int(raw) if raw else 0

    async def can_send(self, domain_id: str) -> Tuple[bool, str]:
        """Check whether a domain has capacity for one more send (read-only).

        Returns (allowed, reason_if_denied).
        """
        if not domain_id or domain_id == "user_smtp":
            return True, ""  # user SMTP bypasses domain limits

        meta = await self._get_domain_meta(domain_id)
        if not meta:
            return False, "Domain not found"

        if meta["status"] in ("paused", "suspended", "failed"):
            return False, f"Domain is {meta['status']}"

        effective_limit = await self.get_effective_limit(domain_id)
        current = await self._get_daily_count(domain_id)

        if current >= effective_limit:
            return False, f"Daily limit reached ({current}/{effective_limit})"

        # Hourly velocity cap: max 60/hour as a safety net
        hourly = await self._get_hourly_count(domain_id)
        hourly_cap = min(effective_limit, 60)
        if hourly >= hourly_cap:
            return False, f"Hourly limit reached ({hourly}/{hourly_cap})"

        return True, ""

    async def record_send(self, domain_id: str) -> bool:
        """Atomically increment daily + hourly counters.

        Returns True if the send was within limits, False if it exceeded.
        Uses INCR which is atomic — safe for concurrent workers.
        """
        if not domain_id or domain_id == "user_smtp":
            return True

        effective_limit = await self.get_effective_limit(domain_id)

        daily_key = f"domain:{domain_id}:sent_today"
        hourly_key = f"domain:{domain_id}:sent_hour"

        # Atomic increment
        new_daily = await redis_client.incr(daily_key)

        # Set TTL on first increment
        if new_daily == 1:
            ttl = _seconds_until_midnight_utc()
            await redis_client.expire(daily_key, ttl)

        # Also track hourly
        new_hourly = await redis_client.incr(hourly_key)
        if new_hourly == 1:
            await redis_client.expire(hourly_key, 3600)

        if new_daily > effective_limit:
            # We went over — the send already happened, but log warning
            logger.warning(
                "Domain %s exceeded daily limit: %d/%d",
                domain_id, new_daily, effective_limit,
            )
            return False

        return True

    async def get_remaining(self, domain_id: str) -> int:
        """Return remaining daily capacity for a domain."""
        if not domain_id or domain_id == "user_smtp":
            return 999999  # user SMTP has no domain limit

        effective_limit = await self.get_effective_limit(domain_id)
        current = await self._get_daily_count(domain_id)
        return max(0, effective_limit - current)

    async def get_daily_count(self, domain_id: str) -> int:
        """Public accessor for today's count."""
        return await self._get_daily_count(domain_id)

    async def invalidate_meta_cache(self, domain_id: str) -> None:
        """Clear cached domain metadata (call after domain settings change)."""
        await redis_client.delete(f"domain:{domain_id}:meta")


# Module singleton
rate_limiter = DomainRateLimiter()
