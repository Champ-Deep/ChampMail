"""
StalwartProvider — MailInfraProvider shim for the existing self-hosted stack.

ChampMail was built on Stalwart/Postfix + a Go mail-engine; domains are
purchased externally (Namecheap/Cloudflare) and mailboxes are configured
manually. This provider exists so the IAL factory can return *something*
for `Domain.infra_provider == "stalwart"` without forcing a rewrite of the
existing send path.

For now the send agent treats Stalwart domains specially: it keeps using
`mail_engine_client` directly (the proven path), and only InboxKit domains
route through the IAL's `get_credentials`. The methods below cover the
read-side so the domains UI can show provider-agnostic state; the write
methods raise NotImplementedError to make the contract honest rather than
silently faking a purchase.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from app.core.config import settings
from app.services.mail_infra import (
    MailInfraProvider,
    MailboxCredentials,
    MailboxRecord,
    DomainRecord,
    HealthSnapshot,
)

logger = logging.getLogger(__name__)


class StalwartProvider(MailInfraProvider):
    """Read-mostly IAL adapter for the legacy Stalwart stack."""

    name = "stalwart"

    # --- Domains ----------------------------------------------------------
    async def search_domains(self, keyword: str, tlds: Optional[list[str]] = None,
                             limit: int = 20) -> list[dict]:
        # Stalwart domains are purchased externally; the IAL doesn't sell.
        return []

    async def buy_domain(self, domain_name: str, registration_years: int = 1,
                         **opts) -> DomainRecord:
        raise NotImplementedError(
            "Stalwart domains are provisioned externally (Namecheap/Cloudflare); "
            "use the InboxKit provider for IAL-managed purchases."
        )

    async def get_domain(self, uid: str) -> Optional[DomainRecord]:
        # `uid` for Stalwart is the local Domain.id (UUID) — caller passes it.
        from app.db.postgres import async_session_maker
        from app.models.domain import Domain
        from sqlalchemy import select

        async with async_session_maker() as session:
            stmt = select(Domain).where(Domain.id == uid)
            result = await session.execute(stmt)
            d = result.scalar_one_or_none()
            if d is None:
                return None
            return DomainRecord(
                uid=str(d.id),
                name=d.domain_name,
                status=d.status or "pending",
                native_status=d.status,
                workspace_uid=None,
            )

    # --- Mailboxes --------------------------------------------------------
    async def buy_mailbox(self, domain_uid: str, username: str,
                          platform: str = "google",
                          first_name: str = "", last_name: str = "") -> MailboxRecord:
        raise NotImplementedError(
            "Stalwart mailboxes are created via the mail-engine admin UI; "
            "use the InboxKit provider for IAL-managed purchases."
        )

    async def get_mailbox(self, uid: str) -> Optional[MailboxRecord]:
        from app.db.postgres import async_session_maker
        from app.models.email_account import EmailAccount
        from sqlalchemy import select

        async with async_session_maker() as session:
            stmt = select(EmailAccount).where(EmailAccount.id == uid)
            result = await session.execute(stmt)
            acc = result.scalar_one_or_none()
            if acc is None:
                return None
            return MailboxRecord(
                uid=str(acc.id),
                email=getattr(acc, "email", ""),
                status="ready" if getattr(acc, "is_active", True) else "retired",
                native_status="active",
                platform="smtp",
            )

    async def get_credentials(self, uid: str) -> MailboxCredentials:
        """Return SMTP/IMAP creds from settings (Stalwart local)."""
        return MailboxCredentials(
            email=settings.smtp_username or settings.mail_from_email,
            username=settings.smtp_username,
            password=settings.smtp_password,
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            imap_host=settings.imap_host,
            imap_port=settings.imap_port,
            platform="smtp",
        )

    async def list_mailboxes(self, domain_uid: Optional[str] = None,
                             status: Optional[str] = None) -> list[MailboxRecord]:
        from app.db.postgres import async_session_maker
        from app.models.email_account import EmailAccount
        from sqlalchemy import select

        async with async_session_maker() as session:
            stmt = select(EmailAccount)
            if domain_uid:
                # EmailAccount has no domain_id FK in the legacy schema; the
                # domain filter is a no-op for Stalwart (callers list all).
                pass
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [
                MailboxRecord(
                    uid=str(r.id),
                    email=getattr(r, "email", ""),
                    status="ready" if getattr(r, "is_active", True) else "retired",
                    native_status="active",
                    platform="smtp",
                )
                for r in rows
            ]

    async def cancel_mailbox(self, uid: str) -> bool:
        logger.warning("StalwartProvider.cancel_mailbox(%s) is a no-op; "
                       "deactivate the mail-engine account manually.", uid)
        return False

    # --- Warmup -----------------------------------------------------------
    async def start_warmup(self, mailbox_uids: list[str]) -> bool:
        # Warmup for Stalwart is the internal seed-address loop in tasks/warmup.py.
        # Toggling is done via Domain.warmup_enabled; this is a no-op marker.
        logger.info("Stalwart warmup toggle requested for %s (handled by warmup task)",
                    mailbox_uids)
        return True

    async def pause_warmup(self, mailbox_uids: list[str]) -> bool:
        return True

    # --- Health -----------------------------------------------------------
    async def health(self, uid: str) -> HealthSnapshot:
        from app.db.postgres import async_session_maker
        from app.models.domain import Domain
        from sqlalchemy import select

        async with async_session_maker() as session:
            stmt = select(Domain).where(Domain.id == uid)
            result = await session.execute(stmt)
            d = result.scalar_one_or_none()
            if d is None:
                return HealthSnapshot()
            return HealthSnapshot(
                placement_pct=None,
                bounce_rate=(d.bounce_rate / 100.0) if d.bounce_rate else None,
                complaint_rate=None,
                infraguard_clean=(d.health_score or 100.0) >= 80.0,
                warmup_day=d.warmup_day,
                last_checked=d.last_health_check or datetime.utcnow(),
            )
