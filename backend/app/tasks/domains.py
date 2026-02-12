from celery import shared_task
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.postgres import async_session
import asyncio


@shared_task(bind=True, queue="domain")
def check_all_domain_health(self):
    async def _check():
        from app.services.domain_service import domain_service
        from app.services.cloudflare_client import cloudflare_client

        async with async_session() as session:
            domains = await domain_service.get_all_domains(session)

            for domain in domains:
                try:
                    health_data = await cloudflare_client.check_domain_health(
                        domain.cloudflare_zone_id
                    )

                    await domain_service.update_health_score(
                        session, domain.id, health_data["score"]
                    )

                except Exception as e:
                    print(f"Health check failed for {domain.domain_name}: {e}")

    asyncio.run(_check())


@shared_task(bind=True, queue="domain")
def verify_domain_dns(self, domain_id: str):
    async def _verify():
        from app.services.domain_service import domain_service
        from app.services.cloudflare_client import cloudflare_client

        async with async_session() as session:
            domain = await domain_service.get_by_id(session, domain_id)

            if not domain:
                raise ValueError(f"Domain {domain_id} not found")

            verification = await cloudflare_client.verify_dns_propagation(
                domain.cloudflare_zone_id
            )

            await domain_service.update_dns_status(
                session,
                domain_id,
                mx_verified=verification["mx"],
                spf_verified=verification["spf"],
                dkim_verified=verification["dkim"],
                dmarc_verified=verification["dmarc"],
            )

            if verification["all_verified"]:
                await domain_service.update_status(session, domain_id, "verified")

            return verification

    return asyncio.run(_verify())


@shared_task(bind=True, queue="domain")
def provision_new_domain(self, domain_name: str, team_id: str):
    async def _provision():
        from app.services.domain_service import domain_service
        from app.services.cloudflare_client import cloudflare_client
        from app.services.namecheap_client import namecheap_client
        from app.services.mail_engine_client import mail_engine_client

        async with async_session() as session:
            available = await namecheap_client.check_availability([domain_name])
            if not available.get(domain_name):
                raise ValueError(f"Domain {domain_name} is not available")

            purchase_result = await namecheap_client.purchase_domain(domain_name)
            if not purchase_result["success"]:
                raise ValueError(f"Failed to purchase {domain_name}")

            zone = await cloudflare_client.add_zone(domain_name)

            dkim_keys = await mail_engine_client.generate_dkim_keys(
                domain_name, selector="champmail"
            )

            dns_result = await cloudflare_client.setup_email_dns(
                zone_id=zone["id"],
                server_ip="",
                dkim_public_key=dkim_keys["public_key"],
                domain=domain_name,
            )

            domain = await domain_service.create(
                session,
                name=domain_name,
                team_id=team_id,
                cloudflare_zone_id=zone["id"],
                dkim_selector="champmail",
                dkim_public_key=dkim_keys["public_key"],
                dkim_private_key=dkim_keys["private_key"],
            )

            return domain.__dict__

    return asyncio.run(_provision())