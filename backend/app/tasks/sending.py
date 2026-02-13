from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.postgres import get_db
from app.services.mail_engine_client import mail_engine_client
from app.services.domain_rotation import domain_rotator
from app.services.tracking_service import tracking_service
import asyncio


async def _inject_tracking(html_body: str, campaign_id: str, prospect_id: str) -> str:
    """Inject tracking pixel, click wrappers, and unsubscribe URL into HTML."""
    tracking_urls = await tracking_service.generate_tracking_urls(campaign_id, prospect_id)
    html = tracking_service.wrap_links_in_html(
        html_body,
        tracking_urls["click_base_url"],
        tracking_urls["signature"],
    )
    html = html.replace("{{tracking_url}}", tracking_urls.get("pixel_url", ""))
    html = html.replace("{{unsubscribe_url}}", tracking_urls.get("unsubscribe_url", ""))
    return html


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_task(self, prospect_id: str, template_id: str, subject: str, html_body: str, domain_id: str = None, campaign_id: str = None):
    try:
        from app.db.postgres import async_session
        from app.services.prospect_service import prospect_service

        async def _send():
            async with async_session() as session:
                prospect = await prospect_service.get_by_id(session, prospect_id)
                if not prospect:
                    raise ValueError(f"Prospect {prospect_id} not found")

                to_email = prospect.get("email")
                to_name = prospect.get("name", "")

                selected_domain = domain_id
                if not selected_domain:
                    selected_domain = await domain_rotator.select_domain(prospect.get("team_id"))

                # Inject tracking: wrap links, add pixel, add unsubscribe
                final_html = html_body
                if campaign_id:
                    try:
                        final_html = await _inject_tracking(final_html, campaign_id, prospect_id)
                    except Exception:
                        pass  # Send even if tracking setup fails

                result = await mail_engine_client.send_email(
                    recipient=to_email,
                    recipient_name=to_name,
                    subject=subject,
                    html_body=final_html,
                    domain_id=selected_domain,
                    track_opens=True,
                    track_clicks=True,
                )

                await prospect_service.update_send_status(session, prospect_id, result.message_id)

                return result.__dict__

        return asyncio.run(_send())

    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_batch_task(self, campaign_id: str, prospect_ids: list[str], template_id: str, domain_id: str = None):
    try:
        from app.db.postgres import async_session
        from app.services.prospect_service import prospect_service
        from app.services.campaigns import campaign_service

        async def _send():
            async with async_session() as session:
                prospects = await prospect_service.get_by_ids(session, prospect_ids)
                if not prospects:
                    raise ValueError("No prospects found")

                selected_domain = domain_id
                if not selected_domain:
                    team_id = prospects[0].get("team_id") if prospects else None
                    selected_domain = await domain_rotator.select_domain(team_id)

                emails = []
                for prospect in prospects:
                    p_id = prospect.get("id", "")
                    html_body = prospect.get("personalized_body", "")

                    # Inject tracking per prospect
                    if campaign_id and html_body:
                        try:
                            html_body = await _inject_tracking(html_body, campaign_id, p_id)
                        except Exception:
                            pass  # Send even if tracking setup fails

                    emails.append({
                        "to": prospect.get("email"),
                        "to_name": prospect.get("name", ""),
                        "subject": prospect.get("personalized_subject", ""),
                        "html_body": html_body,
                        "track_opens": True,
                        "track_clicks": True,
                    })

                result = await mail_engine_client.send_batch(emails=emails, domain_id=selected_domain)

                await campaign_service.update_stats(session, campaign_id, result.successful, result.failed)

                return result.__dict__

        return asyncio.run(_send())

    except Exception as exc:
        raise self.retry(exc=exc)
