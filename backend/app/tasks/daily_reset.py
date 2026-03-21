"""
Daily reset task — runs at midnight UTC.

Syncs Redis daily send counters back to Postgres Domain.sent_today
for dashboard display, then lets the Redis keys expire naturally.
"""

import asyncio
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, queue="domain")
def reset_daily_counters(self):
    """Sync Redis counters → Postgres and reset for the new day."""

    async def _reset():
        from app.db.postgres import async_session_maker
        from app.models.domain import Domain
        from app.services.deliverability.rate_limiter import rate_limiter
        from app.services.domain_service import domain_service
        from sqlalchemy import select, update

        async with async_session_maker() as session:
            result = await session.execute(select(Domain))
            domains = result.scalars().all()

            for domain in domains:
                domain_id = str(domain.id)

                # Read final daily count from Redis
                final_count = await rate_limiter.get_daily_count(domain_id)

                # Write to Postgres for historical reference
                if final_count > 0:
                    logger.info(
                        "Domain %s sent %d emails today",
                        domain.domain_name, final_count,
                    )

                # Reset Postgres counter for the new day
                await session.execute(
                    update(Domain)
                    .where(Domain.id == domain.id)
                    .values(sent_today=0)
                )

                # Clear the Redis meta cache so fresh limits are loaded
                await rate_limiter.invalidate_meta_cache(domain_id)

            await session.commit()

        logger.info("Daily counters reset for %d domains", len(domains))

    asyncio.run(_reset())
