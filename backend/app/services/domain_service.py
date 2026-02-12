"""
Domain service for managing sending domains.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload
from uuid import uuid4
from datetime import datetime

from app.models import Domain, DNSCheckLog, Team
from app.services.cloudflare_client import cloudflare_client


class DomainService:
    """Service for managing sending domains."""

    async def get_by_id(self, session: AsyncSession, domain_id: str) -> Optional[Dict[str, Any]]:
        """Get domain by ID."""
        result = await session.execute(
            select(Domain).where(Domain.id == domain_id)
        )
        domain = result.scalar_one_or_none()
        if domain:
            return self._domain_to_dict(domain)
        return None

    async def get_by_name(self, session: AsyncSession, domain_name: str) -> Optional[Dict[str, Any]]:
        """Get domain by name."""
        result = await session.execute(
            select(Domain).where(Domain.domain_name == domain_name)
        )
        domain = result.scalar_one_or_none()
        if domain:
            return self._domain_to_dict(domain)
        return None

    async def get_by_team(
        self, session: AsyncSession, team_id: str, status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all domains for a team."""
        query = select(Domain).where(Domain.team_id == team_id)
        if status:
            query = query.where(Domain.status == status)

        result = await session.execute(query)
        domains = result.scalars().all()
        return [self._domain_to_dict(d) for d in domains]

    async def get_verified_domains(
        self, session: AsyncSession, team_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all verified domains available for sending."""
        query = select(Domain).where(Domain.status == "verified")
        if team_id:
            query = query.where(Domain.team_id == team_id)

        result = await session.execute(query)
        domains = result.scalars().all()
        return [self._domain_to_dict(d) for d in domains]

    async def get_domains_with_warmup(self, session: AsyncSession) -> List[Dict[str, Any]]:
        """Get domains that need warmup sends."""
        result = await session.execute(
            select(Domain).where(
                Domain.warmup_enabled == True,
                Domain.warmup_day < 30,
                Domain.status == "verified"
            ).order_by(Domain.warmup_day)
        )
        domains = result.scalars().all()
        return [self._domain_to_dict(d) for d in domains]

    async def create(
        self,
        session: AsyncSession,
        name: str,
        team_id: Optional[str] = None,
        cloudflare_zone_id: Optional[str] = None,
        dkim_selector: str = "champmail",
        dkim_public_key: Optional[str] = None,
        dkim_private_key: Optional[str] = None,
        daily_send_limit: int = 50,
    ) -> Dict[str, Any]:
        """Create a new domain."""
        domain = Domain(
            id=uuid4(),
            domain_name=name,
            status="pending",
            dkim_selector=dkim_selector,
            dkim_public_key=dkim_public_key,
            dkim_private_key=dkim_private_key,
            daily_send_limit=daily_send_limit,
            team_id=team_id,
            cloudflare_zone_id=cloudflare_zone_id,
        )

        session.add(domain)
        await session.commit()
        await session.refresh(domain)

        return self._domain_to_dict(domain)

    async def update_status(self, session: AsyncSession, domain_id: str, status: str) -> bool:
        """Update domain verification status."""
        await session.execute(
            update(Domain).where(Domain.id == domain_id).values(status=status)
        )
        await session.commit()
        return True

    async def update_dns_status(
        self,
        session: AsyncSession,
        domain_id: str,
        mx_verified: bool = False,
        spf_verified: bool = False,
        dkim_verified: bool = False,
        dmarc_verified: bool = False,
    ) -> bool:
        """Update DNS verification status."""
        await session.execute(
            update(Domain).where(Domain.id == domain_id).values(
                mx_verified=mx_verified,
                spf_verified=spf_verified,
                dkim_verified=dkim_verified,
                dmarc_verified=dmarc_verified,
                updated_at=datetime.utcnow(),
            )
        )
        await session.commit()
        return True

    async def update_health_score(self, session: AsyncSession, domain_id: str, score: float) -> bool:
        """Update domain health score."""
        await session.execute(
            update(Domain).where(Domain.id == domain_id).values(
                health_score=score,
                last_health_check=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        await session.commit()
        return True

    async def increment_sent_count(self, session: AsyncSession, domain_id: str) -> bool:
        """Increment sent count for a domain."""
        await session.execute(
            update(Domain).where(Domain.id == domain_id).values(
                sent_today=Domain.sent_today + 1,
                updated_at=datetime.utcnow(),
            )
        )
        await session.commit()
        return True

    async def increment_warmup_day(self, session: AsyncSession, domain_id: str) -> bool:
        """Increment warmup day for a domain."""
        await session.execute(
            update(Domain).where(Domain.id == domain_id).values(
                warmup_day=Domain.warmup_day + 1,
                sent_today=0,
                updated_at=datetime.utcnow(),
            )
        )
        await session.commit()
        return True

    async def update_bounce_count(self, session: AsyncSession, domain_id: str) -> bool:
        """Update bounce count and recalculate health score."""
        await session.execute(
            update(Domain).where(Domain.id == domain_id).values(
                bounce_rate=Domain.bounce_rate + 0.01,
                updated_at=datetime.utcnow(),
            )
        )
        await session.commit()
        return True

    async def recalculate_reputation(self, session: AsyncSession, domain_id: str) -> float:
        """Recalculate domain reputation based on recent activity."""
        result = await session.execute(
            select(func.count(Domain.id)).where(
                Domain.id == domain_id,
                Domain.sent_today > 0
            )
        )
        count = result.scalar()

        new_score = 100.0
        result = await session.execute(
            select(Domain.bounce_rate).where(Domain.id == domain_id)
        )
        bounce_rate = result.scalar_one_or_none() or 0.0

        new_score -= bounce_rate * 100
        new_score = max(0, min(100, new_score))

        await self.update_health_score(session, domain_id, new_score)
        return new_score

    async def check_warmup_status(self, session: AsyncSession, domain_id: str) -> bool:
        """Check if domain has completed warmup."""
        result = await session.execute(
            select(Domain).where(Domain.id == domain_id)
        )
        domain = result.scalar_one_or_none()

        if domain and domain.warmup_day >= 30 and domain.warmup_enabled:
            await session.execute(
                update(Domain).where(Domain.id == domain_id).values(
                    warmup_enabled=False,
                    updated_at=datetime.utcnow(),
                )
            )
            await session.commit()
            return True

        return False

    async def delete(self, session: AsyncSession, domain_id: str) -> bool:
        """Delete a domain."""
        result = await session.execute(
            select(Domain).where(Domain.id == domain_id)
        )
        domain = result.scalar_one_or_none()

        if domain:
            await session.delete(domain)
            await session.commit()
            return True

        return False

    def _domain_to_dict(self, domain: Domain) -> Dict[str, Any]:
        """Convert domain model to dictionary."""
        return {
            "id": str(domain.id),
            "domain_name": domain.domain_name,
            "status": domain.status,
            "mx_verified": domain.mx_verified,
            "spf_verified": domain.spf_verified,
            "dkim_verified": domain.dkim_verified,
            "dmarc_verified": domain.dmarc_verified,
            "dkim_selector": domain.dkim_selector,
            "daily_send_limit": domain.daily_send_limit,
            "sent_today": domain.sent_today,
            "warmup_enabled": domain.warmup_enabled,
            "warmup_day": domain.warmup_day,
            "health_score": domain.health_score,
            "bounce_rate": domain.bounce_rate,
            "cloudflare_zone_id": domain.cloudflare_zone_id,
            "team_id": str(domain.team_id) if domain.team_id else None,
            "created_at": domain.created_at.isoformat() if domain.created_at else None,
            "updated_at": domain.updated_at.isoformat() if domain.updated_at else None,
        }


domain_service = DomainService()