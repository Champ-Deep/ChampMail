"""Ramp-governor Celery task.

Runs on a schedule (e.g. hourly via Celery beat). For each active sending domain
it reads recent reputation metrics, asks `ramp_governor.evaluate_domain` for a
decision, and applies it: advance/throttle the daily cap, or pause the domain.
The decision logic is pure + unit-tested (test_outreach_core.py); this task is
the thin DB-bound wrapper.
"""
from __future__ import annotations

import logging

from celery import shared_task
from sqlalchemy import select

from app.db.postgres import async_session
from app.models.domain import Domain
from app.services.ramp_governor import DomainMetrics, RampAction, evaluate_domain

logger = logging.getLogger(__name__)


@shared_task(bind=True, queue="sending")
def run_ramp_governor(self):
    import asyncio

    async def _run():
        async with async_session() as session:
            result = await session.execute(select(Domain))
            domains = result.scalars().all()
            for d in domains:
                metrics = DomainMetrics(
                    bounce_rate=float(getattr(d, "bounce_rate", 0.0) or 0.0),
                    complaint_rate=float(getattr(d, "complaint_rate", 0.0) or 0.0),
                    seed_placement=float(getattr(d, "seed_placement", 1.0) or 1.0),
                    warmup_day=int(getattr(d, "warmup_day", 0) or 0),
                    sent_today=int(getattr(d, "sent_today", 0) or 0),
                    sample_size=int(getattr(d, "messages_sampled", 0) or 0),
                )
                decision = evaluate_domain(metrics)

                if decision.action == RampAction.PAUSE:
                    d.warmup_enabled = False
                    d.daily_send_limit = 0
                elif decision.action == RampAction.ADVANCE:
                    d.warmup_day = min(int(getattr(d, "warmup_day", 0) or 0) + 1, 7)
                    d.daily_send_limit = decision.new_cap
                elif decision.action == RampAction.THROTTLE:
                    d.daily_send_limit = decision.new_cap
                # HOLD: leave as-is
                logger.info("ramp[%s]: %s -> cap=%s (%s)",
                            getattr(d, "domain_name", d.id), decision.action.value,
                            decision.new_cap, decision.reason)
            await session.commit()

    asyncio.run(_run())
