import logging

from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.postgres import async_session
import asyncio

logger = logging.getLogger(__name__)


@shared_task(bind=True, queue="warmup")
def execute_warmup_sends(self):
    async def _execute():
        from app.services.domain_service import domain_service
        from app.services.mail_engine_client import mail_engine_client

        async with async_session() as session:
            domains = await domain_service.get_domains_with_warmup(session)

            for domain in domains:
                if domain.warmup_enabled and domain.warmup_day < 30:
                    daily_limit = get_warmup_limit(domain.warmup_day)

                    if domain.sent_today >= daily_limit:
                        continue

                    remaining = daily_limit - domain.sent_today

                    warmup_emails = await get_warmup_emails(remaining)

                    for email_data in warmup_emails:
                        try:
                            result = await mail_engine_client.send_email(
                                recipient=email_data["to"],
                                subject=email_data["subject"],
                                html_body=email_data["body"],
                                domain_id=domain.id,
                                track_opens=True,
                                track_clicks=False,
                            )

                            await domain_service.increment_sent_count(session, domain.id)

                        except Exception as e:
                            logger.error("Warmup send failed for %s: %s", domain.domain_name, e)

                    if domain.sent_today >= daily_limit:
                        await domain_service.increment_warmup_day(session, domain.id)

    asyncio.run(_execute())


@shared_task(bind=True, queue="warmup")
def update_warmup_status(self, domain_id: str):
    async def _update():
        from app.services.domain_service import domain_service

        async with async_session() as session:
            await domain_service.check_warmup_status(session, domain_id)

    asyncio.run(_update())


def get_warmup_limit(day: int) -> int:
    limits = [10, 25, 50, 100, 200, 500, 750, 1000]
    if day >= len(limits):
        return 1000
    return limits[day]


async def get_warmup_emails(count: int) -> list[dict]:
    warmup_seed_addresses = [
        "seed1@champions.dev",
        "seed2@champions.dev",
        "seed3@champions.dev",
        "seed4@champions.dev",
        "seed5@champions.dev",
    ]

    emails = []
    for i in range(min(count, len(warmup_seed_addresses))):
        emails.append({
            "to": warmup_seed_addresses[i],
            "subject": "Weekly Update",
            "body": f"<p>Hi there,</p><p>This is a warmup email for domain verification.</p><p>Best regards,<br>ChampMail Team</p>",
        })

    return emails