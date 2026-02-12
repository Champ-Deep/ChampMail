"""
Prospect service for managing email recipients.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, text
from sqlalchemy.orm import selectinload
from uuid import uuid4
from datetime import datetime

from app.models import Prospect


class ProspectService:
    """Service for managing prospects."""

    async def get_by_id(self, session: AsyncSession, prospect_id: str) -> Optional[Dict[str, Any]]:
        """Get prospect by ID."""
        result = await session.execute(
            select(Prospect).where(Prospect.id == prospect_id)
        )
        prospect = result.scalar_one_or_none()
        if prospect:
            return self._prospect_to_dict(prospect)
        return None

    async def get_by_email(self, session: AsyncSession, email: str) -> Optional[Dict[str, Any]]:
        """Get prospect by email."""
        result = await session.execute(
            select(Prospect).where(Prospect.email == email)
        )
        prospect = result.scalar_one_or_none()
        if prospect:
            return self._prospect_to_dict(prospect)
        return None

    async def get_by_ids(self, session: AsyncSession, prospect_ids: List[str]) -> List[Dict[str, Any]]:
        """Get multiple prospects by IDs."""
        result = await session.execute(
            select(Prospect).where(Prospect.id.in_(prospect_ids))
        )
        prospects = result.scalars().all()
        return [self._prospect_to_dict(p) for p in prospects]

    async def get_by_team(
        self,
        session: AsyncSession,
        team_id: str,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get all prospects for a team."""
        query = select(Prospect).where(Prospect.team_id == team_id)
        if status:
            query = query.where(Prospect.status == status)

        query = query.offset(offset).limit(limit)
        result = await session.execute(query)
        prospects = result.scalars().all()
        return [self._prospect_to_dict(p) for p in prospects]

    async def create(
        self,
        session: AsyncSession,
        email: str,
        team_id: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        company_name: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Create a new prospect."""
        prospect = Prospect(
            id=uuid4(),
            email=email,
            first_name=first_name,
            last_name=last_name,
            full_name=f"{first_name or ''} {last_name or ''}".strip(),
            company_name=company_name,
            team_id=team_id,
            **kwargs,
        )

        session.add(prospect)
        await session.commit()
        await session.refresh(prospect)

        return self._prospect_to_dict(prospect)

    async def bulk_create(
        self,
        session: AsyncSession,
        prospects_data: List[Dict[str, Any]],
        team_id: str,
        created_by: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Bulk create prospects from a list."""
        prospects = []
        for data in prospects_data:
            prospect = Prospect(
                id=uuid4(),
                email=data["email"],
                first_name=data.get("first_name"),
                last_name=data.get("last_name"),
                full_name=f"{data.get('first_name', '') or ''} {data.get('last_name', '') or ''}".strip(),
                company_name=data.get("company_name"),
                company_domain=data.get("company_domain"),
                job_title=data.get("job_title"),
                industry=data.get("industry"),
                team_id=team_id,
                created_by=created_by,
                source=data.get("source"),
            )
            prospects.append(prospect)

        session.add_all(prospects)
        await session.commit()

        return [self._prospect_to_dict(p) for p in prospects]

    async def update(
        self,
        session: AsyncSession,
        prospect_id: str,
        **kwargs,
    ) -> Optional[Dict[str, Any]]:
        """Update a prospect."""
        result = await session.execute(
            select(Prospect).where(Prospect.id == prospect_id)
        )
        prospect = result.scalar_one_or_none()

        if not prospect:
            return None

        for key, value in kwargs.items():
            if hasattr(prospect, key):
                setattr(prospect, key, value)

        prospect.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(prospect)

        return self._prospect_to_dict(prospect)

    async def update_send_status(
        self,
        session: AsyncSession,
        prospect_id: str,
        message_id: str,
    ) -> bool:
        """Update prospect after sending email."""
        await session.execute(
            update(Prospect).where(Prospect.id == prospect_id).values(
                last_contacted_at=datetime.utcnow(),
            )
        )
        await session.commit()
        return True

    async def mark_as_bounced(
        self,
        session: AsyncSession,
        email: str,
        bounce_type: str = "hard",
    ) -> bool:
        """Mark a prospect as bounced."""
        await session.execute(
            update(Prospect).where(Prospect.email == email).values(
                status="bounced",
                updated_at=datetime.utcnow(),
            )
        )
        await session.commit()
        return True

    async def mark_as_replied(
        self,
        session: AsyncSession,
        prospect_id: str,
    ) -> bool:
        """Mark a prospect as having replied."""
        result = await session.execute(
            select(Prospect).where(Prospect.id == prospect_id)
        )
        prospect = result.scalar_one_or_none()

        if prospect:
            await session.execute(
                update(Prospect).where(Prospect.id == prospect_id).values(
                    status="active",
                    last_contacted_at=datetime.utcnow(),
                )
            )
            await session.commit()

        return True

    async def delete(self, session: AsyncSession, prospect_id: str) -> bool:
        """Delete a prospect."""
        result = await session.execute(
            select(Prospect).where(Prospect.id == prospect_id)
        )
        prospect = result.scalar_one_or_none()

        if prospect:
            await session.delete(prospect)
            await session.commit()
            return True

        return False

    async def search(
        self,
        session: AsyncSession,
        team_id: str,
        query: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Search prospects by name, email, or company."""
        search_pattern = f"%{query}%"

        result = await session.execute(
            select(Prospect).where(
                and_(
                    Prospect.team_id == team_id,
                    or_(
                        Prospect.email.ilike(search_pattern),
                        Prospect.full_name.ilike(search_pattern),
                        Prospect.company_name.ilike(search_pattern),
                    )
                )
            ).limit(limit)
        )

        prospects = result.scalars().all()
        return [self._prospect_to_dict(p) for p in prospects]

    def _prospect_to_dict(self, prospect: Prospect) -> Dict[str, Any]:
        """Convert prospect model to dictionary."""
        return {
            "id": str(prospect.id),
            "email": prospect.email,
            "first_name": prospect.first_name,
            "last_name": prospect.last_name,
            "full_name": prospect.full_name,
            "company_name": prospect.company_name,
            "company_domain": prospect.company_domain,
            "company_size": prospect.company_size,
            "industry": prospect.industry,
            "job_title": prospect.job_title,
            "linkedin_url": prospect.linkedin_url,
            "personalized_subject": prospect.personalized_subject,
            "personalized_body": prospect.personalized_body,
            "status": prospect.status,
            "source": prospect.source,
            "team_id": str(prospect.team_id) if prospect.team_id else None,
            "created_by": str(prospect.created_by) if prospect.created_by else None,
            "created_at": prospect.created_at.isoformat() if prospect.created_at else None,
            "updated_at": prospect.updated_at.isoformat() if prospect.updated_at else None,
            "last_contacted_at": prospect.last_contacted_at.isoformat() if prospect.last_contacted_at else None,
        }


prospect_service = ProspectService()