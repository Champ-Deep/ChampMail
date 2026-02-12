from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.postgres import async_session
import asyncio


@shared_task(bind=True, queue="sending")
def process_bounce_queue(self):
    async def _process():
        from app.services.mail_engine_client import mail_engine_client
        from app.services.prospect_service import prospect_service
        from app.services.domain_service import domain_service

        async with async_session() as session:
            bounces = await mail_engine_client.get_bounces(limit=100)

            for bounce in bounces:
                try:
                    await prospect_service.mark_as_bounced(
                        session, bounce["email"], bounce["type"]
                    )

                    await domain_service.update_bounce_count(session, bounce["domain_id"])

                    await mail_engine_client.acknowledge_bounce(bounce["id"])

                except Exception as e:
                    print(f"Failed to process bounce {bounce['id']}: {e}")

    asyncio.run(_process())


@shared_task(bind=True, queue="sending")
def update_bounce_reputation(self, domain_id: str):
    async def _update():
        from app.services.domain_service import domain_service

        async with async_session() as session:
            await domain_service.recalculate_reputation(session, domain_id)

    asyncio.run(_update())