"""
Campaign orchestration service.

Handles campaign CRUD, recipient management, and sending.
Uses PostgreSQL via SQLAlchemy as the source of truth.
"""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4, UUID

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignProspect, Prospect
from app.services.templates import template_service, substitute_variables
from app.services.email_provider import get_email_provider, EmailMessage, SendResult

logger = logging.getLogger(__name__)


class CampaignStatus(str, Enum):
    """Campaign status values."""
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class CampaignService:
    """Service for managing email campaigns using PostgreSQL."""

    async def create_campaign(
        self,
        session: AsyncSession,
        name: str,
        owner_id: str,
        template_id: Optional[str] = None,
        sequence_id: Optional[str] = None,
        description: Optional[str] = None,
        prospect_list_id: Optional[str] = None,
        from_name: Optional[str] = None,
        from_address: Optional[str] = None,
        daily_limit: int = 100,
    ) -> Campaign:
        """Create a new campaign."""
        campaign = Campaign(
            id=uuid4(),
            name=name,
            description=description,
            status="draft",
            subject_template=None,
            html_template=None,
            from_name=from_name,
            from_address=from_address,
            prospect_list_id=UUID(prospect_list_id) if prospect_list_id else None,
            daily_limit=daily_limit,
            created_by=UUID(owner_id),
        )
        session.add(campaign)
        await session.flush()
        return campaign

    async def get_campaign(self, session: AsyncSession, campaign_id: str) -> Optional[Campaign]:
        """Get campaign by ID."""
        try:
            uid = UUID(campaign_id)
        except ValueError:
            return None
        result = await session.execute(
            select(Campaign).where(Campaign.id == uid)
        )
        return result.scalar_one_or_none()

    async def list_campaigns(
        self,
        session: AsyncSession,
        owner_id: Optional[str] = None,
        status: Optional[CampaignStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Campaign]:
        """List campaigns with optional filtering."""
        query = select(Campaign)

        if owner_id:
            query = query.where(Campaign.created_by == UUID(owner_id))
        if status:
            query = query.where(Campaign.status == status.value)

        query = query.order_by(Campaign.created_at.desc()).offset(offset).limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all())

    async def update_campaign_status(
        self,
        session: AsyncSession,
        campaign_id: str,
        status: CampaignStatus,
    ) -> Optional[Campaign]:
        """Update campaign status."""
        campaign = await self.get_campaign(session, campaign_id)
        if not campaign:
            return None

        campaign.status = status.value
        campaign.updated_at = datetime.utcnow()

        if status == CampaignStatus.RUNNING:
            campaign.activated_at = datetime.utcnow()
        elif status == CampaignStatus.COMPLETED:
            campaign.completed_at = datetime.utcnow()

        await session.flush()
        return campaign

    async def add_recipients(
        self,
        session: AsyncSession,
        campaign_id: str,
        prospect_ids: list[str],
    ) -> int:
        """Add prospects as campaign recipients."""
        added = 0
        campaign_uid = UUID(campaign_id)

        for pid in prospect_ids:
            try:
                prospect_uid = UUID(pid)
            except ValueError:
                continue

            # Check prospect exists
            prospect = await session.execute(
                select(Prospect).where(Prospect.id == prospect_uid)
            )
            if not prospect.scalar_one_or_none():
                continue

            # Check not already enrolled
            existing = await session.execute(
                select(CampaignProspect).where(
                    CampaignProspect.campaign_id == campaign_uid,
                    CampaignProspect.prospect_id == prospect_uid,
                )
            )
            if existing.scalar_one_or_none():
                continue

            enrollment = CampaignProspect(
                id=uuid4(),
                campaign_id=campaign_uid,
                prospect_id=prospect_uid,
                status="enrolled",
            )
            session.add(enrollment)
            added += 1

        if added > 0:
            await session.flush()
            # Update total_prospects count
            await session.execute(
                update(Campaign)
                .where(Campaign.id == campaign_uid)
                .values(total_prospects=Campaign.total_prospects + added)
            )
            await session.flush()

        return added

    async def get_recipients(
        self,
        session: AsyncSession,
        campaign_id: str,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get campaign recipients with prospect details."""
        campaign_uid = UUID(campaign_id)
        query = (
            select(CampaignProspect, Prospect)
            .join(Prospect, CampaignProspect.prospect_id == Prospect.id)
            .where(CampaignProspect.campaign_id == campaign_uid)
        )
        if status:
            query = query.where(CampaignProspect.status == status)
        query = query.limit(limit)

        result = await session.execute(query)
        recipients = []
        for enrollment, prospect in result.all():
            recipients.append({
                "prospect_id": str(prospect.id),
                "email": prospect.email,
                "first_name": prospect.first_name or "",
                "last_name": prospect.last_name or "",
                "company": prospect.company_name or "",
                "title": prospect.job_title or "",
                "status": enrollment.status,
                "sent_at": enrollment.last_sent_at,
                "message_id": enrollment.last_message_id,
            })
        return recipients

    async def get_campaign_stats(self, session: AsyncSession, campaign_id: str) -> dict:
        """Get campaign statistics."""
        campaign = await self.get_campaign(session, campaign_id)
        if not campaign:
            return {}

        sent = campaign.sent_count or 0
        return {
            "sent": sent,
            "delivered": sent - (campaign.bounced_count or 0),
            "opened": campaign.opened_count or 0,
            "clicked": campaign.clicked_count or 0,
            "replied": campaign.replied_count or 0,
            "bounced": campaign.bounced_count or 0,
            "open_rate": (campaign.opened_count or 0) / sent * 100 if sent > 0 else 0,
            "click_rate": (campaign.clicked_count or 0) / sent * 100 if sent > 0 else 0,
            "reply_rate": (campaign.replied_count or 0) / sent * 100 if sent > 0 else 0,
        }

    async def increment_stat(
        self,
        session: AsyncSession,
        campaign_id: str,
        stat_name: str,
    ) -> None:
        """Increment a campaign statistic."""
        VALID_STATS = frozenset({
            "sent_count", "opened_count", "clicked_count",
            "replied_count", "bounced_count", "unsubscribed_count",
        })
        if stat_name not in VALID_STATS:
            raise ValueError(f"Invalid stat name: {stat_name}")

        campaign_uid = UUID(campaign_id)
        await session.execute(
            update(Campaign)
            .where(Campaign.id == campaign_uid)
            .values(**{stat_name: getattr(Campaign, stat_name) + 1})
        )
        await session.flush()


# Global service instance
campaign_service = CampaignService()
