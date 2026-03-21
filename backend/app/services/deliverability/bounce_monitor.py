"""
Bounce rate monitor — auto-pauses domains when bounce rates spike.

Thresholds (rolling window of last 100 sends):
- > 5%  → warning logged, velocity reduced
- > 8%  → domain auto-paused, admin notified
- > 12% → domain suspended (requires manual reactivation)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from app.db.redis import redis_client

logger = logging.getLogger(__name__)

# Bounce rate thresholds
WARN_THRESHOLD = 0.05       # 5%
PAUSE_THRESHOLD = 0.08      # 8%
SUSPEND_THRESHOLD = 0.12    # 12%

# Rolling window size
BOUNCE_WINDOW = 100


class BounceMonitor:
    """Monitors domain bounce rates and takes protective action."""

    async def get_rolling_bounce_rate(
        self, domain_id: str, window: int = BOUNCE_WINDOW,
    ) -> float:
        """Calculate bounce rate from the last N sends for a domain.

        Queries SendLog table for the most recent sends and counts bounces.
        """
        from app.db.postgres import async_session_maker
        from app.models.send_log import SendLog
        from sqlalchemy import select, desc, func

        try:
            async with async_session_maker() as session:
                # Get total recent sends
                recent = await session.execute(
                    select(SendLog.status)
                    .where(SendLog.domain_id == domain_id)
                    .where(SendLog.status.in_(["sent", "delivered", "bounced", "opened", "clicked"]))
                    .order_by(desc(SendLog.sent_at))
                    .limit(window)
                )
                statuses = [row[0] for row in recent.fetchall()]

                if not statuses:
                    return 0.0

                bounced = sum(1 for s in statuses if s == "bounced")
                return bounced / len(statuses)

        except Exception as e:
            logger.error("Failed to calculate bounce rate for domain %s: %s", domain_id, e)
            return 0.0

    async def check_domain_health(self, domain_id: str) -> Dict:
        """Check a domain's bounce rate and take action if needed.

        Returns health status dict.
        """
        bounce_rate = await self.get_rolling_bounce_rate(domain_id)

        status = "healthy"
        action_taken = None

        if bounce_rate >= SUSPEND_THRESHOLD:
            status = "suspended"
            action_taken = await self._suspend_domain(
                domain_id,
                f"Bounce rate {bounce_rate:.1%} exceeds suspend threshold ({SUSPEND_THRESHOLD:.0%})",
            )
        elif bounce_rate >= PAUSE_THRESHOLD:
            status = "paused"
            action_taken = await self._pause_domain(
                domain_id,
                f"Bounce rate {bounce_rate:.1%} exceeds pause threshold ({PAUSE_THRESHOLD:.0%})",
            )
        elif bounce_rate >= WARN_THRESHOLD:
            status = "warning"
            logger.warning(
                "Domain %s bounce rate warning: %.1f%% (threshold: %.0f%%)",
                domain_id, bounce_rate * 100, WARN_THRESHOLD * 100,
            )

        result = {
            "domain_id": domain_id,
            "bounce_rate": round(bounce_rate, 4),
            "status": status,
            "action_taken": action_taken,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

        # Cache the health status for the send gate to read
        await redis_client.set_json(
            f"domain:{domain_id}:health", result, ex=1800,  # 30 min cache
        )

        return result

    async def _pause_domain(self, domain_id: str, reason: str) -> str:
        """Auto-pause a domain due to high bounce rate."""
        from app.db.postgres import async_session_maker
        from app.models.domain import Domain
        from sqlalchemy import update

        try:
            async with async_session_maker() as session:
                await session.execute(
                    update(Domain)
                    .where(Domain.id == domain_id)
                    .values(status="paused")
                )
                await session.commit()

            # Update Redis meta cache
            from app.services.deliverability.rate_limiter import rate_limiter
            await rate_limiter.invalidate_meta_cache(domain_id)

            logger.error("Domain %s AUTO-PAUSED: %s", domain_id, reason)
            return f"paused: {reason}"

        except Exception as e:
            logger.error("Failed to pause domain %s: %s", domain_id, e)
            return f"pause_failed: {e}"

    async def _suspend_domain(self, domain_id: str, reason: str) -> str:
        """Suspend a domain — requires manual reactivation."""
        from app.db.postgres import async_session_maker
        from app.models.domain import Domain
        from sqlalchemy import update

        try:
            async with async_session_maker() as session:
                await session.execute(
                    update(Domain)
                    .where(Domain.id == domain_id)
                    .values(status="suspended")
                )
                await session.commit()

            from app.services.deliverability.rate_limiter import rate_limiter
            await rate_limiter.invalidate_meta_cache(domain_id)

            logger.critical("Domain %s SUSPENDED: %s", domain_id, reason)
            return f"suspended: {reason}"

        except Exception as e:
            logger.error("Failed to suspend domain %s: %s", domain_id, e)
            return f"suspend_failed: {e}"


# Module singleton
bounce_monitor = BounceMonitor()
