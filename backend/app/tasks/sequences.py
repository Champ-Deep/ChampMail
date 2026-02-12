from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.postgres import async_session
from datetime import datetime, timedelta
import asyncio


@shared_task(bind=True, queue="sequences")
def execute_pending_steps(self):
    async def _execute():
        from app.services.sequence_service import sequence_service
        from app.services.mail_engine_client import mail_engine_client
        from app.services.domain_rotation import domain_rotator

        async with async_session() as session:
            pending_steps = await sequence_service.get_pending_steps(session)

            for step in pending_steps:
                try:
                    domain_id = await domain_rotator.select_domain(step.get("team_id"))

                    result = await mail_engine_client.send_email(
                        recipient=step.get("prospect_email"),
                        recipient_name=step.get("prospect_name"),
                        subject=step.get("subject"),
                        html_body=step.get("body"),
                        domain_id=domain_id,
                        track_opens=True,
                        track_clicks=True,
                    )

                    await sequence_service.mark_step_sent(session, step.get("id"), result.message_id)

                    await sequence_service.schedule_next_step(
                        session,
                        step.get("sequence_id"),
                        step.get("prospect_id"),
                        step.get("step_order") + 1,
                    )

                except Exception as e:
                    await sequence_service.mark_step_failed(session, step.get("id"), str(e))

    asyncio.run(_execute())


@shared_task(bind=True, queue="sequences")
def pause_sequence(self, sequence_id: str, prospect_id: str = None, reason: str = "manual"):
    async def _pause():
        from app.services.sequence_service import sequence_service

        async with async_session() as session:
            await sequence_service.pause(session, sequence_id, prospect_id, reason)

    asyncio.run(_pause())


@shared_task(bind=True, queue="sequences")
def resume_sequence(self, sequence_id: str, prospect_id: str = None):
    async def _resume():
        from app.services.sequence_service import sequence_service

        async with async_session() as session:
            await sequence_service.resume(session, sequence_id, prospect_id)

    asyncio.run(_resume())


@shared_task(bind=True, queue="sequences")
def check_replies_and_pause(self):
    async def _check():
        from app.services.sequence_service import sequence_service
        from app.services.mail_engine_client import mail_engine_client

        async with async_session() as session:
            active_sequences = await sequence_service.get_active_sequences(session)

            for seq in active_sequences:
                prospect_ids = await sequence_service.get_enrolled_prospect_ids(session, seq.id)

                for prospect_id in prospect_ids:
                    has_replied = await mail_engine_client.check_for_replies(
                        prospect_email=seq.prospect_email
                    )

                    if has_replied:
                        await sequence_service.pause(
                            session, seq.id, prospect_id, reason="reply_detected"
                        )

    asyncio.run(_check())