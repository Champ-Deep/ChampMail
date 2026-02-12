from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.postgres import async_session
from datetime import date
import asyncio


@shared_task(bind=True, queue="default")
def aggregate_daily_stats(self):
    async def _aggregate():
        from app.services.analytics_service import analytics_service

        async with async_session() as session:
            yesterday = date.today() - timedelta(days=1)

            await analytics_service.aggregate_daily_stats(session, yesterday)

    asyncio.run(_aggregate())


@shared_task(bind=True, queue="default")
def calculate_campaign_metrics(self, campaign_id: str):
    async def _calculate():
        from app.services.campaigns import campaign_service

        async with async_session() as session:
            metrics = await campaign_service.calculate_metrics(session, campaign_id)

            return metrics

    return asyncio.run(_calculate())


@shared_task(bind=True, queue="default")
def cleanup_old_logs(self, days: int = 90):
    async def _cleanup():
        from app.services.log_service import log_service

        async with async_session() as session:
            await log_service.delete_old_logs(session, days)

    asyncio.run(_cleanup())