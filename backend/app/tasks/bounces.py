"""
Bounce processing — native VERP-based bounce handling.

Flow:
  Gmail/Outlook → DSN to bounce+{prospect_id}@mail.domain.com
  Postfix pipes DSN to bounce_handler.py (standalone script)
  bounce_handler.py enqueues process_single_bounce Celery task
  This task marks the prospect, updates domain bounce_rate, checks thresholds.
"""

import logging
import asyncio

from celery import shared_task
from app.db.postgres import async_session_maker as async_session

logger = logging.getLogger(__name__)

# Bounce rate thresholds from FINAL_PLAN.md
HARD_BOUNCE_PAUSE_THRESHOLD = 0.02   # > 2% → pause domain
SOFT_BOUNCE_REDUCE_THRESHOLD = 0.05  # > 5% → reduce send rate 50%
COMPLAINT_PAUSE_THRESHOLD = 0.003    # > 0.3% → pause domain permanently


@shared_task(bind=True, queue="sending")
def process_single_bounce(self, prospect_id: str, bounce_type: str, domain_id: str = None):
    """
    Process a single bounce event.
    Called by bounce_handler.py after parsing a Postfix DSN pipe.

    bounce_type: "hard" | "soft" | "complaint"
    """
    async def _process():
        from app.services.prospect_service import prospect_service
        from app.services.domain_service import domain_service
        from app.services.suppression_service import suppression_service

        async with async_session() as session:
            prospect = await prospect_service.get_by_id(session, prospect_id)
            if not prospect:
                logger.warning("Bounce for unknown prospect %s", prospect_id)
                return

            email = prospect.get("email", "")

            # Hard bounce → suppression list immediately
            if bounce_type == "hard":
                await suppression_service.add(session, email, "bounce")
                await prospect_service.mark_as_bounced(session, email, bounce_type)
                logger.info("Hard bounce: suppressed %s", email)

            # Soft bounce → mark on prospect, don't suppress yet
            elif bounce_type == "soft":
                await prospect_service.mark_as_bounced(session, email, bounce_type)
                logger.info("Soft bounce: marked %s", email)

            # Spam complaint → suppress + mark
            elif bounce_type == "complaint":
                await suppression_service.add(session, email, "complaint")
                await prospect_service.mark_as_bounced(session, email, "complaint")
                logger.warning("Spam complaint from %s — suppressed", email)

            # Update domain bounce rate and check thresholds
            if domain_id:
                await domain_service.update_bounce_count(session, domain_id)
                domain = await domain_service.get_by_id(session, domain_id)
                if domain:
                    bounce_rate = domain.get("bounce_rate", 0)
                    complaint_rate = domain.get("complaint_rate", 0)

                    if bounce_type == "hard" and bounce_rate > HARD_BOUNCE_PAUSE_THRESHOLD:
                        await domain_service.pause_domain(session, domain_id, f"hard bounce rate {bounce_rate:.2%}")
                        logger.error("AUTO-PAUSED %s: hard bounce rate %.2f%%", domain["domain_name"], bounce_rate * 100)

                    elif bounce_type == "complaint" and complaint_rate > COMPLAINT_PAUSE_THRESHOLD:
                        await domain_service.pause_domain(session, domain_id, f"complaint rate {complaint_rate:.2%}")
                        logger.error("AUTO-PAUSED %s: complaint rate %.4f%%", domain["domain_name"], complaint_rate * 100)

    asyncio.run(_process())


@shared_task(bind=True, queue="sending")
def process_bounce_queue(self):
    """
    Legacy compatibility — kept for any existing Celery schedules.
    Native bounce processing now goes through process_single_bounce
    triggered by the Postfix pipe handler.
    """
    logger.debug("process_bounce_queue: native VERP processing active, no queue polling needed")


@shared_task(bind=True, queue="sending")
def update_bounce_reputation(self, domain_id: str):
    async def _update():
        from app.services.domain_service import domain_service
        async with async_session() as session:
            await domain_service.recalculate_reputation(session, domain_id)

    asyncio.run(_update())
