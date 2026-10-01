import logging

from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.postgres import async_session_maker as async_session
import asyncio

logger = logging.getLogger(__name__)


@shared_task(bind=True, queue="sending")
def process_bounce_queue(self):
    async def _process():
        from app.services.mail_engine_client import mail_engine_client
        from app.services.prospect_service import prospect_service
        from app.services.domain_service import domain_service

        from app.services.suppression_service import suppression_service

        async with async_session() as session:
            bounces = await mail_engine_client.get_bounces(limit=100)

            for bounce in bounces:
                try:
                    await prospect_service.mark_as_bounced(
                        session, bounce["email"], bounce["type"]
                    )

                    # Hard bounces and complaints permanently suppress the address
                    # across all of the team's campaigns.
                    btype = (bounce.get("type") or "").lower()
                    if btype in ("hard", "complaint", "spam_complaint"):
                        await suppression_service.add(
                            session, bounce.get("team_id"), bounce["email"],
                            reason=("complaint" if "complaint" in btype else "bounce_hard"),
                            source="bounce_processor",
                        )

                    await domain_service.update_bounce_count(session, bounce["domain_id"])

                    try:
                        from app.services.events import EmailEventType, emit
                        evt = (EmailEventType.COMPLAINED if "complaint" in btype
                               else EmailEventType.BOUNCED)
                        await emit(evt, email=bounce["email"],
                                   team_id=str(bounce.get("team_id") or ""),
                                   payload={"type": btype})
                    except Exception:
                        pass

                    await mail_engine_client.acknowledge_bounce(bounce["id"])

                except Exception as e:
                    logger.error("Failed to process bounce %s: %s", bounce['id'], e)

    asyncio.run(_process())


@shared_task(bind=True, queue="sending")
def update_bounce_reputation(self, domain_id: str):
    async def _update():
        from app.services.domain_service import domain_service

        async with async_session() as session:
            await domain_service.recalculate_reputation(session, domain_id)

    asyncio.run(_update())