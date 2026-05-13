"""
Domain health, DNS verification, blacklist checking, and provisioning tasks.
"""

import logging
import asyncio
import base64

from celery import shared_task
from app.db.postgres import async_session_maker as async_session

logger = logging.getLogger(__name__)


def _generate_dkim_keypair() -> tuple[str, str]:
    """
    Generate a 2048-bit RSA keypair for DKIM signing.
    Returns (private_key_pem, public_key_b64_for_dns).
    """
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    public_der = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_b64 = base64.b64encode(public_der).decode()
    return private_pem, public_b64


def _write_dkim_key_file(domain_name: str, private_pem: str, keys_path: str) -> str:
    """Write the private key to the shared OpenDKIM keys volume. Returns file path."""
    import os
    domain_dir = os.path.join(keys_path, domain_name)
    os.makedirs(domain_dir, exist_ok=True)
    key_path = os.path.join(domain_dir, "champmail.private")
    with open(key_path, "w") as f:
        f.write(private_pem)
    os.chmod(key_path, 0o600)
    return key_path


def _reload_opendkim(domain_name: str, keys_path: str) -> None:
    """Append new domain to KeyTable/SigningTable and send HUP to OpenDKIM."""
    import os
    import signal

    key_table = os.path.join(keys_path, "..", "KeyTable")
    signing_table = os.path.join(keys_path, "..", "SigningTable")

    kt_entry = f"champmail._domainkey.{domain_name}  {domain_name}:champmail:{keys_path}/{domain_name}/champmail.private\n"
    st_entry = f"*@{domain_name}  champmail._domainkey.{domain_name}\n"

    for path, entry in [(key_table, kt_entry), (signing_table, st_entry)]:
        existing = open(path).read() if os.path.exists(path) else ""
        if entry.split()[0] not in existing:
            with open(path, "a") as f:
                f.write(entry)

    # Signal OpenDKIM to reload config
    pid_file = "/run/opendkim/opendkim.pid"
    if os.path.exists(pid_file):
        with open(pid_file) as f:
            pid = int(f.read().strip())
        os.kill(pid, signal.SIGHUP)
        logger.info("OpenDKIM reloaded for %s", domain_name)


@shared_task(bind=True, queue="domain")
def check_all_domain_health(self):
    """
    Runs every 6 hours.
    Checks each domain/IP against DNS blacklists and applies health penalties.
    Auto-pauses domains that exceed bounce/complaint thresholds.
    """
    async def _check():
        from app.services.domain_service import domain_service
        from app.services.ip_blacklist import blacklist_checker
        from app.core.config import settings

        async with async_session() as session:
            domains = await domain_service.get_all_domains(session)
            vps_ip = settings.vps_public_ip or await blacklist_checker.get_vps_ip()

            for domain in domains:
                domain_id = domain["id"]
                try:
                    # Bounce rate auto-pause
                    if domain.get("bounce_rate", 0) > 0.02:
                        await domain_service.pause_domain(session, domain_id, "bounce_rate > 2%")
                        logger.warning("Auto-paused %s: bounce_rate=%.4f", domain["domain_name"], domain["bounce_rate"])
                        continue

                    # Complaint rate auto-pause
                    if domain.get("complaint_rate", 0) > 0.003:
                        await domain_service.pause_domain(session, domain_id, "complaint_rate > 0.3%")
                        logger.warning("Auto-paused %s: complaint_rate=%.4f", domain["domain_name"], domain["complaint_rate"])
                        continue

                    # Blacklist check on VPS IP
                    if vps_ip:
                        report = await blacklist_checker.check_ip(vps_ip)
                        await domain_service.update_blacklist_status(
                            session,
                            domain_id,
                            blacklisted=report.blacklisted,
                            hit_count=len(report.hits),
                            health_penalty=report.health_penalty(),
                        )
                        if report.blacklisted:
                            await domain_service.pause_domain(session, domain_id, f"blacklisted: {[h.name for h in report.hits]}")
                            logger.error(
                                "BLACKLIST: %s is listed on %s — domain auto-paused",
                                vps_ip,
                                [h.name for h in report.hits],
                            )

                except Exception as e:
                    logger.error("Health check failed for %s: %s", domain.get("domain_name"), e)

    asyncio.run(_check())


@shared_task(bind=True, queue="domain")
def verify_domain_dns(self, domain_id: str):
    """Verify SPF/DKIM/DMARC/MX DNS propagation for a domain."""
    async def _verify():
        from app.services.domain_service import domain_service
        from app.services.cloudflare_client import cloudflare_client

        async with async_session() as session:
            domain = await domain_service.get_by_id(session, domain_id)
            if not domain:
                raise ValueError(f"Domain {domain_id} not found")

            verification = await cloudflare_client.verify_dns_propagation(
                domain["cloudflare_zone_id"]
            )
            await domain_service.update_dns_status(
                session, domain_id,
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
    """
    Purchase domain, set up Cloudflare DNS, generate DKIM keypair,
    write key to shared OpenDKIM volume, and reload OpenDKIM.
    """
    async def _provision():
        from app.services.domain_service import domain_service
        from app.services.cloudflare_client import cloudflare_client
        from app.services.namecheap_client import namecheap_client
        from app.core.config import settings

        async with async_session() as session:
            available = await namecheap_client.check_availability([domain_name])
            if not available.get(domain_name):
                raise ValueError(f"Domain {domain_name} is not available")

            purchase_result = await namecheap_client.purchase_domain(domain_name)
            if not purchase_result["success"]:
                raise ValueError(f"Failed to purchase {domain_name}: {purchase_result}")

            zone = await cloudflare_client.add_zone(domain_name)

            # Generate DKIM keypair locally — no mail-engine dependency
            private_pem, public_b64 = _generate_dkim_keypair()

            # Write private key to shared OpenDKIM volume
            try:
                _write_dkim_key_file(domain_name, private_pem, settings.dkim_keys_path)
                _reload_opendkim(domain_name, settings.dkim_keys_path)
            except Exception as e:
                logger.warning("OpenDKIM key write failed (will need manual setup): %s", e)

            dns_result = await cloudflare_client.setup_email_dns(
                zone_id=zone["id"],
                server_ip=settings.vps_public_ip,
                dkim_public_key=public_b64,
                domain=domain_name,
            )

            domain = await domain_service.create(
                session,
                name=domain_name,
                team_id=team_id,
                cloudflare_zone_id=zone["id"],
                dkim_selector=settings.dkim_selector,
                dkim_public_key=public_b64,
                dkim_private_key=private_pem,
            )
            return domain

    return asyncio.run(_provision())
