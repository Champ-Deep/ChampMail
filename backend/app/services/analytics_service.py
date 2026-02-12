"""
Analytics service for tracking and aggregating email metrics.
"""

from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta
from dateutil import parser

from app.models import SendLog, DailyStats, Campaign, Domain


class AnalyticsService:
    """Service for analytics and metrics."""

    async def get_campaign_stats(
        self,
        session: AsyncSession,
        campaign_id: str,
    ) -> Dict[str, Any]:
        """Get statistics for a campaign."""
        result = await session.execute(
            select(
                func.count(SendLog.id).label("total_sent"),
                func.sum(func.cast(SendLog.status == "opened", func.count())).label("total_opened"),
                func.sum(func.cast(SendLog.status == "clicked", func.count())).label("total_clicked"),
                func.sum(func.cast(SendLog.status == "bounced", func.count())).label("total_bounced"),
            ).where(SendLog.campaign_id == campaign_id)
        )

        row = result.first()
        total_sent = row.total_sent or 0
        total_opened = row.total_opened or 0
        total_clicked = row.total_clicked or 0
        total_bounced = row.total_bounced or 0

        return {
            "campaign_id": campaign_id,
            "total_sent": total_sent,
            "total_opened": total_opened,
            "total_clicked": total_clicked,
            "total_bounced": total_bounced,
            "open_rate": round(total_opened / total_sent * 100, 2) if total_sent > 0 else 0,
            "click_rate": round(total_clicked / total_sent * 100, 2) if total_sent > 0 else 0,
            "bounce_rate": round(total_bounced / total_sent * 100, 2) if total_sent > 0 else 0,
        }

    async def get_domain_stats(
        self,
        session: AsyncSession,
        domain_id: str,
    ) -> Dict[str, Any]:
        """Get statistics for a domain."""
        result = await session.execute(
            select(
                func.count(SendLog.id).label("total_sent"),
                func.sum(func.cast(SendLog.status == "opened", func.count())).label("total_opened"),
                func.sum(func.cast(SendLog.status == "clicked", func.count())).label("total_clicked"),
                func.sum(func.cast(SendLog.status == "bounced", func.count())).label("total_bounced"),
            ).where(SendLog.domain_id == domain_id)
        )

        row = result.first()
        total_sent = row.total_sent or 0
        total_opened = row.total_opened or 0
        total_clicked = row.total_clicked or 0
        total_bounced = row.total_bounced or 0

        return {
            "domain_id": domain_id,
            "total_sent": total_sent,
            "total_opened": total_opened,
            "total_clicked": total_clicked,
            "total_bounced": total_bounced,
            "open_rate": round(total_opened / total_sent * 100, 2) if total_sent > 0 else 0,
            "click_rate": round(total_clicked / total_sent * 100, 2) if total_sent > 0 else 0,
            "bounce_rate": round(total_bounced / total_sent * 100, 2) if total_sent > 0 else 0,
        }

    async def get_team_stats(
        self,
        session: AsyncSession,
        team_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Get aggregated statistics for a team."""
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()

        result = await session.execute(
            select(
                func.count(SendLog.id).label("total_sent"),
                func.sum(func.cast(SendLog.status == "opened", func.count())).label("total_opened"),
                func.sum(func.cast(SendLog.status == "clicked", func.count())).label("total_clicked"),
                func.sum(func.cast(SendLog.status == "bounced", func.count())).label("total_bounced"),
                func.sum(func.cast(SendLog.status == "replied", func.count())).label("total_replied"),
            ).where(
                and_(
                    SendLog.team_id == team_id,
                    SendLog.sent_at >= start_date,
                    SendLog.sent_at <= end_date,
                )
            )
        )

        row = result.first()
        total_sent = row.total_sent or 0
        total_opened = row.total_opened or 0
        total_clicked = row.total_clicked or 0
        total_bounced = row.total_bounced or 0
        total_replied = row.total_replied or 0

        return {
            "team_id": team_id,
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
            },
            "total_sent": total_sent,
            "total_opened": total_opened,
            "total_clicked": total_clicked,
            "total_bounced": total_bounced,
            "total_replied": total_replied,
            "open_rate": round(total_opened / total_sent * 100, 2) if total_sent > 0 else 0,
            "click_rate": round(total_clicked / total_sent * 100, 2) if total_sent > 0 else 0,
            "bounce_rate": round(total_bounced / total_sent * 100, 2) if total_sent > 0 else 0,
            "reply_rate": round(total_replied / total_sent * 100, 2) if total_sent > 0 else 0,
        }

    async def get_daily_stats(
        self,
        session: AsyncSession,
        domain_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """Get daily statistics for the specified period."""
        start_date = datetime.utcnow() - timedelta(days=days)

        query = select(DailyStats).where(DailyStats.date >= start_date)
        if domain_id:
            query = query.where(DailyStats.domain_id == domain_id)
        if campaign_id:
            query = query.where(DailyStats.campaign_id == campaign_id)

        query = query.order_by(DailyStats.date)

        result = await session.execute(query)
        stats = result.scalars().all()

        return [
            {
                "date": stat.date.isoformat() if hasattr(stat.date, 'isoformat') else str(stat.date),
                "total_sent": stat.total_sent,
                "total_opened": stat.total_opened,
                "total_clicked": stat.total_clicked,
                "total_bounced": stat.total_bounced,
                "open_rate": stat.open_rate,
                "click_rate": stat.click_rate,
            }
            for stat in stats
        ]

    async def aggregate_daily_stats(
        self,
        session: AsyncSession,
        target_date: datetime,
    ) -> bool:
        """Aggregate daily statistics for all domains and campaigns."""
        date_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        date_end = target_date.replace(hour=23, minute=59, second=59, microsecond=999)

        domain_ids = await session.execute(
            select(Domain.id).where(Domain.status == "verified")
        )
        domain_ids = [row[0] for row in domain_ids.fetchall()]

        for domain_id in domain_ids:
            result = await session.execute(
                select(
                    func.count(SendLog.id).label("total_sent"),
                    func.sum(func.cast(SendLog.status == "opened", func.count())).label("total_opened"),
                    func.sum(func.cast(SendLog.status == "clicked", func.count())).label("total_clicked"),
                    func.sum(func.cast(SendLog.status == "bounced", func.count())).label("total_bounced"),
                ).where(
                    and_(
                        SendLog.domain_id == domain_id,
                        SendLog.sent_at >= date_start,
                        SendLog.sent_at <= date_end,
                    )
                )
            )

            row = result.first()
            total_sent = row.total_sent or 0
            total_opened = row.total_opened or 0
            total_clicked = row.total_clicked or 0
            total_bounced = row.total_bounced or 0

            open_rate = round(total_opened / total_sent * 100, 2) if total_sent > 0 else 0
            click_rate = round(total_clicked / total_sent * 100, 2) if total_sent > 0 else 0
            bounce_rate = round(total_bounced / total_sent * 100, 2) if total_sent > 0 else 0

            existing = await session.execute(
                select(DailyStats).where(
                    and_(
                        DailyStats.domain_id == domain_id,
                        func.date(DailyStats.date) == target_date.date(),
                    )
                )
            )
            existing_stat = existing.scalar_one_or_none()

            if existing_stat:
                existing_stat.total_sent = total_sent
                existing_stat.total_opened = total_opened
                existing_stat.total_clicked = total_clicked
                existing_stat.total_bounced = total_bounced
                existing_stat.open_rate = open_rate
                existing_stat.click_rate = click_rate
                existing_stat.bounce_rate = bounce_rate
            else:
                daily_stat = DailyStats(
                    id=domain_id,
                    domain_id=domain_id,
                    date=target_date,
                    total_sent=total_sent,
                    total_opened=total_opened,
                    total_clicked=total_clicked,
                    total_bounced=total_bounced,
                    open_rate=open_rate,
                    click_rate=click_rate,
                    bounce_rate=bounce_rate,
                )
                session.add(daily_stat)

        await session.commit()
        return True


analytics_service = AnalyticsService()