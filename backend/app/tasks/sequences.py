from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.postgres import async_session_maker
from datetime import datetime, timedelta
import asyncio


@shared_task(bind=True, queue="sequences")
def execute_pending_steps(self):
    async def _execute():
        from app.services.sequence_service import sequence_service
        from app.services.mail_engine_client import mail_engine_client
        from app.services.domain_rotation import domain_rotator

        async with async_session_maker() as session:
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

        async with async_session_maker() as session:
            await sequence_service.pause(session, sequence_id, prospect_id, reason)

    asyncio.run(_pause())


@shared_task(bind=True, queue="sequences")
def resume_sequence(self, sequence_id: str, prospect_id: str = None):
    async def _resume():
        from app.services.sequence_service import sequence_service

        async with async_session_maker() as session:
            await sequence_service.resume(session, sequence_id, prospect_id)

    asyncio.run(_resume())


@shared_task(bind=True, queue="sequences")
def check_replies_and_pause(self):
    async def _check():
        from sqlalchemy import select
        from app.models import Prospect
        from app.services.sequence_service import sequence_service
        from app.services.mail_engine_client import mail_engine_client
        from app.services.ai.openrouter_service import reply_classification_service
        from app.services.champiq_emit import emit_email_event

        async with async_session_maker() as session:
            # get_active_sequences returns plain dicts (_sequence_to_dict), not
            # ORM rows, and has no per-enrollment prospect_email - look up each
            # enrolled prospect's own address instead of the sequence's.
            active_sequences = await sequence_service.get_active_sequences(session)

            for seq in active_sequences:
                prospect_ids = await sequence_service.get_enrolled_prospect_ids(session, seq["id"])
                if not prospect_ids:
                    continue

                result = await session.execute(select(Prospect).where(Prospect.id.in_(prospect_ids)))
                prospects_by_id = {str(p.id): p for p in result.scalars().all()}

                for prospect_id in prospect_ids:
                    prospect = prospects_by_id.get(prospect_id)
                    if not prospect or not prospect.email:
                        continue

                    reply = await mail_engine_client.check_for_replies(prospect_email=prospect.email)

                    if reply.has_replied:
                        classification = await reply_classification_service.classify_reply(
                            subject=reply.reply_subject,
                            body=reply.reply_body,
                        )

                        await sequence_service.pause(
                            session,
                            seq["id"],
                            prospect_id,
                            reason=f"reply_detected:{classification['category']}",
                        )

                        # REPLIED edge write-back: rides the same email.* event
                        # path GraphWritebackConsumer already drains into
                        # Cham_Graph (champiq_emit.emit_email_event), with the
                        # classification carried as extra edge properties.
                        await emit_email_event(
                            "email.replied",
                            to_email=seq.get("from_address") or "",
                            from_email=prospect.email,
                            subject=reply.reply_subject,
                            body=reply.reply_body,
                            direction="inbound",
                            extra={
                                "classification": classification["category"],
                                "classification_confidence": classification["confidence"],
                            },
                        )

    asyncio.run(_check())