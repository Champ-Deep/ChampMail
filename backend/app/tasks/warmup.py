"""
Warmup task — daily seed sends and midnight counter reset.

Uses warmup_schedule.py as the single source of truth for send limits.
Graduation occurs at day 60 (WARMUP_GRADUATION_DAY).
"""

import logging

from celery import shared_task
from app.db.postgres import async_session_maker as async_session
import asyncio

from app.services.warmup_schedule import (
    WARMUP_GRADUATION_DAY,
    effective_daily_limit,
    get_daily_limit,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, queue="warmup")
def execute_warmup_sends(self):
    """Send to seed addresses for every domain currently in warmup."""
    async def _execute():
        from app.services.domain_service import domain_service
        from app.services.email_service import email_service
        from app.core.config import settings

        seed_emails = [
            e.strip()
            for e in settings.warmup_seed_emails.split(",")
            if e.strip()
        ]
        if not seed_emails:
            logger.warning("No warmup seed emails configured — set WARMUP_SEED_EMAILS")
            return

        async with async_session() as session:
            # get_domains_with_warmup now uses WARMUP_GRADUATION_DAY (60)
            domains = await domain_service.get_domains_with_warmup(session)

            for domain in domains:
                if not domain.get("warmup_enabled"):
                    continue
                if domain.get("paused") or domain.get("blacklisted"):
                    continue

                warmup_day = domain.get("warmup_day", 0)
                daily_cap = get_daily_limit(warmup_day)
                sent = domain.get("sent_today", 0)
                remaining = daily_cap - sent

                if remaining <= 0:
                    continue

                targets = seed_emails[:remaining]

                for seed_addr in targets:
                    try:
                        # Warmup sends go through local Postfix (no user creds needed)
                        await email_service.send_warmup_email(
                            to_email=seed_addr,
                            from_email=f"warmup@{domain['domain_name']}",
                            domain_name=domain["domain_name"],
                        )
                        await domain_service.increment_sent_count(session, domain["id"])
                    except Exception as e:
                        logger.error("Warmup send failed for %s: %s", domain["domain_name"], e)

    asyncio.run(_execute())


@shared_task(bind=True, queue="warmup")
def midnight_reset(self):
    """
    Runs daily at midnight UTC.
    1. Resets sent_today = 0 for every domain.
    2. Advances warmup_day +1 for all warming domains.
    3. Graduates domains that have reached day 60.
    """
    async def _reset():
        from app.services.domain_service import domain_service

        async with async_session() as session:
            reset_count = await domain_service.reset_all_sent_today(session)
            graduated = await domain_service.advance_warmup_days(session)
            logger.info(
                "Midnight reset complete: %d domains reset, %d graduated from warmup",
                reset_count,
                graduated,
            )

    asyncio.run(_reset())
