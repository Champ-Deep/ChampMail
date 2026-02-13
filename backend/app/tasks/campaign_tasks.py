"""
Celery tasks for asynchronous campaign pipeline execution.

These tasks wrap the async CampaignPipeline methods so they can run in the
Celery worker process. Each task follows the established pattern:
  - shared_task with bind=True
  - Inner async function using async_session_maker
  - asyncio.run() to bridge sync Celery -> async service code

All tasks publish progress to Redis so the frontend can poll in real-time.
"""

import asyncio
import logging
from typing import Dict, List, Optional

from celery import shared_task

from app.db.postgres import async_session_maker
from app.db.redis import redis_client

logger = logging.getLogger(__name__)


@shared_task(bind=True, queue="default", max_retries=2, default_retry_delay=120)
def run_campaign_pipeline_task(
    self,
    campaign_id: str,
    prospect_list_id: str,
    description: str,
    target_audience: str = None,
    style: dict = None,
) -> dict:
    """Run the full AI campaign pipeline asynchronously via Celery.

    This is the primary entry point. It delegates to CampaignPipeline.run_full_pipeline
    which handles all six steps: essence -> research -> segment -> pitch -> personalize -> html.

    Parameters
    ----------
    campaign_id : str
        UUID of the Campaign to process.
    prospect_list_id : str
        Team or list ID to load prospects from.
    description : str
        User's campaign description for essence extraction.
    target_audience : str, optional
        Free-text target audience description.
    style : dict, optional
        HTML style overrides (primary_color, company_name, etc.).

    Returns
    -------
    dict
        Full pipeline results including generated emails.
    """

    async def _run():
        from app.services.campaign_pipeline import campaign_pipeline

        try:
            result = await campaign_pipeline.run_full_pipeline(
                campaign_id=campaign_id,
                prospect_list_id=prospect_list_id,
                description=description,
                target_audience=target_audience,
                style=style,
            )
            return result
        except Exception as exc:
            logger.error(
                "Pipeline task failed for campaign %s: %s",
                campaign_id,
                str(exc),
                exc_info=True,
            )
            # Store failure status in Redis for frontend
            await redis_client.set_json(
                f"pipeline:{campaign_id}:status",
                {
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {str(exc)}",
                    "task_id": self.request.id,
                },
                ex=86400,
            )
            raise

    try:
        return asyncio.run(_run())
    except Exception as exc:
        # Only retry on transient errors (API timeouts, rate limits)
        if _is_retryable(exc):
            logger.warning(
                "Retrying pipeline task for campaign %s (attempt %d/%d)",
                campaign_id,
                self.request.retries + 1,
                self.max_retries,
            )
            raise self.retry(exc=exc)
        raise


@shared_task(bind=True, queue="default", max_retries=3, default_retry_delay=60)
def research_prospects_task(
    self,
    prospect_ids: List[str],
    campaign_id: str = None,
) -> list:
    """Research a batch of prospects via the AI research service.

    Can be called independently of the full pipeline for on-demand research.

    Parameters
    ----------
    prospect_ids : list[str]
        UUIDs of prospects to research.
    campaign_id : str, optional
        If provided, stores progress in Redis under the campaign's pipeline keys.

    Returns
    -------
    list[dict]
        Research results with prospect_id, prospect_email, and research_data.
    """

    async def _research():
        from app.services.campaign_pipeline import campaign_pipeline

        if campaign_id:
            await redis_client.set_json(
                f"pipeline:{campaign_id}:status",
                {
                    "status": "running",
                    "current_step": "research_prospects",
                    "task_id": self.request.id,
                },
                ex=86400,
            )

        results = await campaign_pipeline.research_prospects(
            prospect_ids=prospect_ids,
            campaign_id=campaign_id,
        )

        if campaign_id:
            await redis_client.set_json(
                f"pipeline:{campaign_id}:research_prospects",
                results,
                ex=86400,
            )

        return results

    try:
        return asyncio.run(_research())
    except Exception as exc:
        if _is_retryable(exc):
            raise self.retry(exc=exc)
        raise


@shared_task(bind=True, queue="default", max_retries=2, default_retry_delay=90)
def generate_emails_task(
    self,
    campaign_id: str,
    description: str,
    prospect_ids: List[str],
    target_audience: str = None,
    style: dict = None,
) -> list:
    """Generate and personalize emails for a set of prospects.

    This is a lighter-weight alternative to the full pipeline. It assumes
    research has already been done and cached. It runs:
    essence -> (cached research) -> segment -> pitch -> personalize -> html.

    Parameters
    ----------
    campaign_id : str
        Campaign UUID.
    description : str
        Campaign description for essence extraction.
    prospect_ids : list[str]
        Prospect UUIDs to generate emails for.
    target_audience : str, optional
        Target audience description.
    style : dict, optional
        HTML style overrides.

    Returns
    -------
    list[dict]
        Generated email payloads with html_body, subject, etc.
    """

    async def _generate():
        from app.services.campaign_pipeline import campaign_pipeline
        from app.services.ai.openrouter_service import research_service
        from sqlalchemy import select
        from app.models.campaign import Prospect

        # Update status
        await redis_client.set_json(
            f"pipeline:{campaign_id}:status",
            {
                "status": "running",
                "current_step": "extract_essence",
                "task_id": self.request.id,
            },
            ex=86400,
        )

        # Step 1: Essence
        essence = await campaign_pipeline.extract_essence(description, target_audience)

        # Load prospects from DB
        async with async_session_maker() as session:
            result = await session.execute(
                select(Prospect).where(Prospect.id.in_(prospect_ids))
            )
            db_prospects = result.scalars().all()

        prospect_dicts = [
            {
                "id": str(p.id),
                "email": p.email,
                "first_name": p.first_name,
                "last_name": p.last_name,
                "company_name": p.company_name,
                "company_domain": p.company_domain,
                "industry": p.industry,
                "job_title": p.job_title,
                "title": p.job_title,
                "company_size": p.company_size,
            }
            for p in db_prospects
        ]

        if not prospect_dicts:
            raise ValueError("No valid prospects found for the given IDs")

        # Step 2: Research (will use cache if available)
        await redis_client.set_json(
            f"pipeline:{campaign_id}:status",
            {"status": "running", "current_step": "research_prospects", "task_id": self.request.id},
            ex=86400,
        )
        research_results = await research_service.research_batch(prospect_dicts, concurrency=3)

        # Step 3: Segment
        await redis_client.set_json(
            f"pipeline:{campaign_id}:status",
            {"status": "running", "current_step": "segment_prospects", "task_id": self.request.id},
            ex=86400,
        )
        segments = await campaign_pipeline.segment_prospects(
            research_results=research_results,
            campaign_goals=description,
            essence=essence,
        )

        # Step 4: Pitches
        await redis_client.set_json(
            f"pipeline:{campaign_id}:status",
            {"status": "running", "current_step": "generate_pitches", "task_id": self.request.id},
            ex=86400,
        )
        pitches = await campaign_pipeline.generate_pitches(segments, essence, research_results)

        # Step 5: Personalize
        await redis_client.set_json(
            f"pipeline:{campaign_id}:status",
            {"status": "running", "current_step": "personalize_emails", "task_id": self.request.id},
            ex=86400,
        )
        research_lookup = campaign_pipeline._build_research_lookup(research_results)
        personalized = await campaign_pipeline.personalize_emails(pitches, prospect_dicts, research_lookup)

        # Step 6: HTML
        await redis_client.set_json(
            f"pipeline:{campaign_id}:status",
            {"status": "running", "current_step": "generate_html", "task_id": self.request.id},
            ex=86400,
        )
        html_emails = await campaign_pipeline.generate_html_emails(personalized, style=style)

        # Persist results
        await campaign_pipeline._persist_results(campaign_id, html_emails)

        # Mark complete
        await redis_client.set_json(
            f"pipeline:{campaign_id}:status",
            {
                "status": "completed",
                "task_id": self.request.id,
                "total_emails": len(html_emails),
            },
            ex=86400,
        )

        return html_emails

    try:
        return asyncio.run(_generate())
    except Exception as exc:
        logger.error(
            "Email generation task failed for campaign %s: %s",
            campaign_id,
            str(exc),
            exc_info=True,
        )
        asyncio.run(
            redis_client.set_json(
                f"pipeline:{campaign_id}:status",
                {
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {str(exc)}",
                    "task_id": self.request.id,
                },
                ex=86400,
            )
        )
        if _is_retryable(exc):
            raise self.retry(exc=exc)
        raise


@shared_task(bind=True, queue="sending", max_retries=3, default_retry_delay=30)
def schedule_campaign_sends_task(
    self,
    campaign_id: str,
) -> dict:
    """Schedule all ready emails in a campaign for optimal send times.

    Reads the personalized emails from the database, computes optimal
    send windows using the SendScheduler, and enqueues individual
    send tasks with appropriate ETAs.

    Parameters
    ----------
    campaign_id : str
        Campaign UUID whose emails should be scheduled.

    Returns
    -------
    dict
        Summary with scheduled_count and schedule details.
    """

    async def _schedule():
        from app.services.send_scheduler import send_scheduler
        from sqlalchemy import select
        from app.models.campaign import Campaign, CampaignProspect, Prospect

        async with async_session_maker() as session:
            # Load campaign
            result = await session.execute(
                select(Campaign).where(Campaign.id == campaign_id)
            )
            campaign = result.scalar_one_or_none()
            if not campaign:
                raise ValueError(f"Campaign {campaign_id} not found")

            # Load active CampaignProspect enrollments that haven't been sent
            result = await session.execute(
                select(CampaignProspect, Prospect)
                .join(Prospect, CampaignProspect.prospect_id == Prospect.id)
                .where(CampaignProspect.campaign_id == campaign_id)
                .where(CampaignProspect.status == "active")
                .where(CampaignProspect.email_sent == False)  # noqa: E712
            )
            rows = result.all()

        # Build personalized email list for scheduling
        personalized_emails = []
        for cp, prospect in rows:
            personalized_emails.append({
                "prospect_id": str(prospect.id),
                "prospect_email": prospect.email,
                "first_name": prospect.first_name,
                "company_name": prospect.company_name,
                "company_domain": prospect.company_domain,
                "industry": prospect.industry,
                "subject": prospect.personalized_subject or "",
                "html_body": prospect.personalized_body or "",
                "campaign_prospect_id": str(cp.id),
            })

        if not personalized_emails:
            return {"scheduled_count": 0, "message": "No emails ready to send"}

        # Schedule sends
        scheduled = await send_scheduler.schedule_campaign_sends(
            campaign_id=campaign_id,
            personalized_emails=personalized_emails,
        )

        return {
            "scheduled_count": len(scheduled),
            "campaign_id": campaign_id,
            "schedule": scheduled,
        }

    try:
        return asyncio.run(_schedule())
    except Exception as exc:
        if _is_retryable(exc):
            raise self.retry(exc=exc)
        raise


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #

def _is_retryable(exc: Exception) -> bool:
    """Determine if an exception warrants a retry.

    Returns True for transient errors like HTTP timeouts, rate limiting,
    and temporary connection failures. Returns False for permanent errors
    like validation failures and missing data.
    """
    import httpx

    retryable_types = (
        httpx.TimeoutException,
        httpx.ConnectError,
        ConnectionError,
        TimeoutError,
        OSError,
    )

    if isinstance(exc, retryable_types):
        return True

    # Check for HTTP 429 (rate limit) or 5xx status codes
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or status >= 500

    # Check for Redis connection errors
    error_msg = str(exc).lower()
    if any(term in error_msg for term in ["timeout", "connection", "rate limit", "429"]):
        return True

    return False
