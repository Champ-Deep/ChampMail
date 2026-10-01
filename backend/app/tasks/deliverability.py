"""
Deliverability maintenance tasks — scheduled via Celery Beat.

- Suppression list sync (every 15 min)
- Bounce rate monitoring (every 30 min)
- DNSBL blacklist checks (every 6 hours)
"""

import asyncio
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, queue="domain")
def sync_suppression_list_task(self):
    """Rebuild the global suppression Redis SET from Postgres."""

    async def _sync():
        from app.services.deliverability.send_gate import send_gate
        count = await send_gate.sync_suppression_from_db()
        logger.info("Suppression list synced: %d entries", count)

    asyncio.run(_sync())


@shared_task(bind=True, queue="domain")
def check_bounce_rates_task(self):
    """Check bounce rates for all active sending domains."""

    async def _check():
        from app.db.postgres import async_session_maker
        from app.models.domain import Domain
        from app.services.deliverability.bounce_monitor import bounce_monitor
        from sqlalchemy import select

        async with async_session_maker() as session:
            result = await session.execute(
                select(Domain.id).where(
                    Domain.status.in_(["verified", "active", "warning"])
                )
            )
            domain_ids = [str(row[0]) for row in result.fetchall()]

        for domain_id in domain_ids:
            health = await bounce_monitor.check_domain_health(domain_id)
            if health["status"] != "healthy":
                logger.warning(
                    "Domain %s health: %s (bounce_rate: %.1f%%)",
                    domain_id, health["status"], health["bounce_rate"] * 100,
                )

    asyncio.run(_check())


@shared_task(bind=True, queue="domain")
def check_domain_blacklists_task(self):
    """Check all active domains against DNS-based blacklists."""

    async def _check():
        from app.db.postgres import async_session_maker
        from app.models.domain import Domain
        from app.services.deliverability.blacklist_checker import blacklist_checker
        from sqlalchemy import select

        async with async_session_maker() as session:
            result = await session.execute(
                select(Domain.id, Domain.domain_name).where(
                    Domain.status.in_(["verified", "active"])
                )
            )
            domains = [(str(row[0]), row[1]) for row in result.fetchall()]

        for domain_id, domain_name in domains:
            bl_result = await blacklist_checker.check_domain_by_id(domain_id)
            if bl_result.get("listed"):
                logger.error(
                    "ALERT: Domain %s (%s) is BLACKLISTED: %s",
                    domain_name, domain_id, bl_result["listings"],
                )

    asyncio.run(_check())
