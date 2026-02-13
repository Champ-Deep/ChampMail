"""
Analytics API endpoints.

Provides campaign performance metrics, daily send/open/click trends,
domain performance stats, and an overview dashboard endpoint.

All data is sourced from SendLog, BounceLog, Campaign, and DailyStats tables
with Redis caching for high-traffic endpoints.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenData, require_auth
from app.db.postgres import get_db_session
from app.db.redis import redis_client
from app.models.campaign import Campaign, CampaignProspect, Prospect
from app.models.send_log import BounceLog, DailyStats, SendLog
from app.services.tracking_service import tracking_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


# ============================================================================
# Response Models
# ============================================================================


class OverviewStats(BaseModel):
    """High-level analytics overview for the dashboard."""
    emails_sent_today: int = 0
    emails_sent_this_week: int = 0
    emails_sent_this_month: int = 0
    open_rate: float = 0.0
    click_rate: float = 0.0
    bounce_rate: float = 0.0
    reply_rate: float = 0.0
    top_performing_domain: Optional[dict] = None
    recent_campaigns: list = []


class CampaignAnalytics(BaseModel):
    """Detailed analytics for a single campaign."""
    campaign_id: str
    campaign_name: str
    campaign_status: str
    total_prospects: int = 0
    sent: int = 0
    delivered: int = 0
    opens: dict = {}
    clicks: dict = {}
    bounces: dict = {}
    replies: dict = {}
    unsubscribes: int = 0
    delivery_rate: float = 0.0
    computed_at: str = ""


class DailyStatsItem(BaseModel):
    """Single day of email metrics."""
    date: str
    total_sent: int = 0
    total_opened: int = 0
    total_clicked: int = 0
    total_bounced: int = 0
    total_replied: int = 0
    open_rate: float = 0.0
    click_rate: float = 0.0


class DomainAnalytics(BaseModel):
    """Performance metrics for a sending domain."""
    domain: str
    total_sent: int = 0
    total_opened: int = 0
    total_clicked: int = 0
    total_bounced: int = 0
    open_rate: float = 0.0
    click_rate: float = 0.0
    bounce_rate: float = 0.0


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/overview", response_model=OverviewStats)
async def get_overview(
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Get analytics overview for the dashboard.

    Returns aggregated metrics across all campaigns: today's sends,
    weekly/monthly totals, overall rates, top domain, and recent campaigns.
    """
    # Check cache
    cache_key = f"analytics:overview:{user.team_id or user.user_id}"
    cached = await redis_client.get_json(cache_key)
    if cached:
        return OverviewStats(**cached)

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    # Total sends by period
    sent_today = await session.execute(
        select(func.count(SendLog.id))
        .where(SendLog.sent_at >= today_start)
    )
    sent_week = await session.execute(
        select(func.count(SendLog.id))
        .where(SendLog.sent_at >= week_start)
    )
    sent_month = await session.execute(
        select(func.count(SendLog.id))
        .where(SendLog.sent_at >= month_start)
    )

    # Overall rates (last 30 days)
    thirty_days_ago = now - timedelta(days=30)
    agg = await session.execute(
        select(
            func.count(SendLog.id).label("total"),
            func.count(SendLog.first_open_at).label("opens"),
            func.count(SendLog.first_click_at).label("clicks"),
            func.count(SendLog.bounced_at).label("bounces"),
            func.count(SendLog.replied_at).label("replies"),
        )
        .where(SendLog.sent_at >= thirty_days_ago)
    )
    row = agg.one()
    total = row.total or 1  # avoid division by zero

    # Top performing domain (by open rate, min 10 sends)
    domain_stats = await session.execute(
        select(
            SendLog.from_address,
            func.count(SendLog.id).label("cnt"),
            func.count(SendLog.first_open_at).label("opens"),
        )
        .where(SendLog.sent_at >= thirty_days_ago)
        .group_by(SendLog.from_address)
        .having(func.count(SendLog.id) >= 10)
        .order_by((func.count(SendLog.first_open_at) * 100.0 / func.count(SendLog.id)).desc())
        .limit(1)
    )
    top_domain_row = domain_stats.first()
    top_domain = None
    if top_domain_row:
        addr = top_domain_row.from_address or ""
        domain_name = addr.split("@")[1] if "@" in addr else addr
        top_domain = {
            "domain_name": domain_name,
            "open_rate": round((top_domain_row.opens / top_domain_row.cnt * 100) if top_domain_row.cnt else 0, 1),
        }

    # Recent campaigns (last 5)
    campaigns_result = await session.execute(
        select(Campaign)
        .order_by(Campaign.created_at.desc())
        .limit(5)
    )
    recent_campaigns = []
    for c in campaigns_result.scalars().all():
        sent = c.sent_count or 0
        opened = c.opened_count or 0
        recent_campaigns.append({
            "id": str(c.id),
            "name": c.name,
            "sent": sent,
            "open_rate": round((opened / sent * 100) if sent > 0 else 0.0, 1),
            "status": c.status,
        })

    overview = OverviewStats(
        emails_sent_today=sent_today.scalar() or 0,
        emails_sent_this_week=sent_week.scalar() or 0,
        emails_sent_this_month=sent_month.scalar() or 0,
        open_rate=round((row.opens / total * 100), 1),
        click_rate=round((row.clicks / total * 100), 1),
        bounce_rate=round((row.bounces / total * 100), 1),
        reply_rate=round((row.replies / total * 100), 1),
        top_performing_domain=top_domain,
        recent_campaigns=recent_campaigns,
    )

    # Cache for 5 minutes
    await redis_client.set_json(cache_key, overview.model_dump(), ex=300)

    return overview


@router.get("/campaigns/{campaign_id}", response_model=CampaignAnalytics)
async def get_campaign_analytics(
    campaign_id: str,
    user: TokenData = Depends(require_auth),
):
    """Get detailed analytics for a specific campaign.

    Uses the tracking service which combines real-time Redis counters
    with database aggregates for comprehensive stats.
    """
    stats = await tracking_service.get_campaign_tracking_stats(campaign_id)

    if stats.get("error"):
        raise HTTPException(status_code=404, detail=stats["error"])

    return CampaignAnalytics(**stats)


@router.get("/daily")
async def get_daily_stats(
    days: int = Query(default=7, ge=1, le=90, description="Number of days to retrieve"),
    campaign_id: Optional[str] = Query(default=None, description="Filter by campaign"),
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Get daily send/open/click/bounce metrics for charting.

    Returns one entry per day for the requested period.
    """
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    # Build query based on SendLog aggregation by date
    conditions = [SendLog.sent_at >= start_date]
    if campaign_id:
        conditions.append(SendLog.campaign_id == campaign_id)

    daily = await session.execute(
        select(
            func.date(SendLog.sent_at).label("day"),
            func.count(SendLog.id).label("sent"),
            func.count(SendLog.first_open_at).label("opened"),
            func.count(SendLog.first_click_at).label("clicked"),
            func.count(SendLog.bounced_at).label("bounced"),
            func.count(SendLog.replied_at).label("replied"),
        )
        .where(and_(*conditions))
        .group_by(func.date(SendLog.sent_at))
        .order_by(func.date(SendLog.sent_at))
    )

    result = []
    for row in daily.all():
        sent = row.sent or 1
        result.append(DailyStatsItem(
            date=str(row.day),
            total_sent=row.sent or 0,
            total_opened=row.opened or 0,
            total_clicked=row.clicked or 0,
            total_bounced=row.bounced or 0,
            total_replied=row.replied or 0,
            open_rate=round((row.opened / sent * 100), 1),
            click_rate=round((row.clicked / sent * 100), 1),
        ).model_dump())

    return {"period": f"{days}d", "stats": result}


@router.get("/domains")
async def get_domain_stats(
    days: int = Query(default=30, ge=1, le=90),
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Get performance metrics grouped by sending domain.

    Useful for monitoring domain health and rotation strategy.
    """
    start_date = datetime.utcnow() - timedelta(days=days)

    result = await session.execute(
        select(
            SendLog.from_address,
            func.count(SendLog.id).label("total_sent"),
            func.count(SendLog.first_open_at).label("total_opened"),
            func.count(SendLog.first_click_at).label("total_clicked"),
            func.count(SendLog.bounced_at).label("total_bounced"),
        )
        .where(SendLog.sent_at >= start_date)
        .group_by(SendLog.from_address)
        .order_by(func.count(SendLog.id).desc())
    )

    domains = []
    for row in result.all():
        addr = row.from_address or ""
        domain_name = addr.split("@")[1] if "@" in addr else addr
        sent = row.total_sent or 1
        domains.append(DomainAnalytics(
            domain=domain_name,
            total_sent=row.total_sent or 0,
            total_opened=row.total_opened or 0,
            total_clicked=row.total_clicked or 0,
            total_bounced=row.total_bounced or 0,
            open_rate=round((row.total_opened / sent * 100), 1),
            click_rate=round((row.total_clicked / sent * 100), 1),
            bounce_rate=round((row.total_bounced / sent * 100), 1),
        ).model_dump())

    return {"domains": domains}


@router.get("/team")
async def get_team_stats(
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Get aggregated team-level analytics.

    Provides overall email performance for the user's team.
    """
    now = datetime.utcnow()

    if start_date:
        try:
            period_start = datetime.fromisoformat(start_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format (use ISO 8601)")
    else:
        period_start = now - timedelta(days=30)

    if end_date:
        try:
            period_end = datetime.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format (use ISO 8601)")
    else:
        period_end = now

    agg = await session.execute(
        select(
            func.count(SendLog.id).label("total_sent"),
            func.count(SendLog.first_open_at).label("total_opened"),
            func.count(SendLog.first_click_at).label("total_clicked"),
            func.count(SendLog.bounced_at).label("total_bounced"),
            func.count(SendLog.replied_at).label("total_replied"),
        )
        .where(SendLog.sent_at >= period_start)
        .where(SendLog.sent_at <= period_end)
    )
    row = agg.one()
    total = row.total_sent or 1

    return {
        "team_id": user.team_id or "",
        "period": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
        },
        "total_sent": row.total_sent or 0,
        "total_opened": row.total_opened or 0,
        "total_clicked": row.total_clicked or 0,
        "total_bounced": row.total_bounced or 0,
        "total_replied": row.total_replied or 0,
        "open_rate": round((row.total_opened / total * 100), 1),
        "click_rate": round((row.total_clicked / total * 100), 1),
        "bounce_rate": round((row.total_bounced / total * 100), 1),
        "reply_rate": round((row.total_replied / total * 100), 1),
    }
