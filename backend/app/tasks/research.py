"""
Prospect research Celery tasks.

- Single prospect research
- Campaign-wide batch research (all enrolled prospects)
"""

import asyncio
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, queue="research", max_retries=2, default_retry_delay=60)
def research_prospect_task(self, prospect_id: str):
    """Research a single prospect asynchronously."""

    async def _run():
        from app.services.prospect_research import prospect_research_service
        return await prospect_research_service.research_prospect(prospect_id)

    result = asyncio.run(_run())
    logger.info("Research task complete for prospect %s", prospect_id)
    return result


@shared_task(bind=True, queue="research", max_retries=1, default_retry_delay=120)
def research_campaign_prospects_task(self, campaign_id: str):
    """Research all enrolled prospects for a campaign.

    Loads CampaignProspect enrollments, then researches each prospect
    that hasn't been researched yet (research_status == 'pending').
    """

    async def _run():
        from app.db.postgres import async_session_maker
        from app.models.campaign import Campaign, CampaignProspect, Prospect
        from app.services.prospect_research import prospect_research_service
        from sqlalchemy import select

        async with async_session_maker() as session:
            result = await session.execute(
                select(Prospect.id)
                .join(CampaignProspect, CampaignProspect.prospect_id == Prospect.id)
                .where(CampaignProspect.campaign_id == campaign_id)
                .where(CampaignProspect.status == "enrolled")
                .where(
                    (Prospect.research_status == "pending")
                    | (Prospect.research_status.is_(None))
                )
            )
            prospect_ids = [str(row[0]) for row in result.fetchall()]

        if not prospect_ids:
            logger.info("Campaign %s: no prospects need research", campaign_id)
            return {"campaign_id": campaign_id, "researched": 0}

        logger.info(
            "Campaign %s: researching %d prospects",
            campaign_id, len(prospect_ids),
        )

        results = await prospect_research_service.research_batch(
            prospect_ids,
            concurrency=3,
            delay_seconds=2.0,
        )

        success = sum(1 for r in results if not r.get("error"))
        failed = len(results) - success

        logger.info(
            "Campaign %s research complete: %d success, %d failed",
            campaign_id, success, failed,
        )

        return {
            "campaign_id": campaign_id,
            "researched": success,
            "failed": failed,
            "total": len(prospect_ids),
        }

    return asyncio.run(_run())
