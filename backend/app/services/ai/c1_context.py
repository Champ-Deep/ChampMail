"""
Context builder for Thesys C1 Generative UI.
Enriches system prompts with real user/team data so C1 can
generate relevant, data-aware interactive UI components.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenData
from app.models.campaign import Campaign, Prospect
from app.models.send_log import SendLog

logger = logging.getLogger(__name__)

BASE_SYSTEM_PROMPT = """You are ChampMail AI, a B2B email campaign assistant. Generate interactive UI components to help users analyze and manage their email campaigns.

You have access to the user's real data. Use it to generate relevant, accurate visualizations and insights.

When asked about analytics, generate charts, tables, and metric cards.
When asked about campaigns, generate campaign cards with real metrics.
When asked to create something, generate interactive forms.
When comparing data, use bar charts or comparison tables.
Always use actual numbers from the data provided - never make up statistics."""

ANALYTICS_CONTEXT_TEMPLATE = """
CURRENT USER DATA:
- Emails sent today: {sent_today}
- Emails sent this week: {sent_week}
- Emails sent this month: {sent_month}
- Overall open rate (30d): {open_rate}%
- Overall click rate (30d): {click_rate}%
- Overall bounce rate (30d): {bounce_rate}%
- Overall reply rate (30d): {reply_rate}%

ACTIVE CAMPAIGNS:
{campaigns_list}

PROSPECT SUMMARY:
- Total prospects: {prospect_count}
"""

CAMPAIGN_CONTEXT_TEMPLATE = """
CAMPAIGN CONTEXT:
You are helping the user build and optimize email campaigns. Suggest improvements, A/B test ideas, and provide actionable insights.

ACTIVE CAMPAIGNS:
{campaigns_list}

RECENT PERFORMANCE:
- Average open rate: {open_rate}%
- Average click rate: {click_rate}%
"""


class C1ContextBuilder:
    """Builds data-enriched system prompts for C1 conversations."""

    async def build_system_prompt(
        self,
        user: TokenData,
        session: AsyncSession,
        context_type: str = "general",
    ) -> str:
        """Build system prompt with real user data injected."""
        base = BASE_SYSTEM_PROMPT

        if context_type == "analytics":
            context = await self._analytics_context(user, session)
            return base + "\n" + context
        elif context_type == "campaign":
            context = await self._campaign_context(user, session)
            return base + "\n" + context
        else:
            # General: include a lighter version of analytics
            context = await self._analytics_context(user, session)
            return base + "\n" + context

    async def _analytics_context(self, user: TokenData, session: AsyncSession) -> str:
        """Fetch analytics summary for system prompt."""
        try:
            now = datetime.utcnow()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=today_start.weekday())
            month_start = today_start.replace(day=1)
            thirty_days_ago = now - timedelta(days=30)

            # Send counts by period
            sent_today = (await session.execute(
                select(func.count(SendLog.id)).where(SendLog.sent_at >= today_start)
            )).scalar() or 0

            sent_week = (await session.execute(
                select(func.count(SendLog.id)).where(SendLog.sent_at >= week_start)
            )).scalar() or 0

            sent_month = (await session.execute(
                select(func.count(SendLog.id)).where(SendLog.sent_at >= month_start)
            )).scalar() or 0

            # Overall rates (last 30 days)
            agg = await session.execute(
                select(
                    func.count(SendLog.id).label("total"),
                    func.count(SendLog.first_open_at).label("opens"),
                    func.count(SendLog.first_click_at).label("clicks"),
                    func.count(SendLog.bounced_at).label("bounces"),
                    func.count(SendLog.replied_at).label("replies"),
                ).where(SendLog.sent_at >= thirty_days_ago)
            )
            row = agg.one()
            total = row.total or 1

            # Active campaigns
            campaigns_list = await self._campaigns_list(session)

            # Prospect count
            prospect_count = (await session.execute(
                select(func.count(Prospect.id))
            )).scalar() or 0

            return ANALYTICS_CONTEXT_TEMPLATE.format(
                sent_today=sent_today,
                sent_week=sent_week,
                sent_month=sent_month,
                open_rate=round(row.opens / total * 100, 1),
                click_rate=round(row.clicks / total * 100, 1),
                bounce_rate=round(row.bounces / total * 100, 1),
                reply_rate=round(row.replies / total * 100, 1),
                campaigns_list=campaigns_list,
                prospect_count=prospect_count,
            )
        except Exception as e:
            logger.warning(f"Failed to build analytics context: {e}")
            return "\nNote: Could not load user data. Answer based on general knowledge."

    async def _campaign_context(self, user: TokenData, session: AsyncSession) -> str:
        """Fetch campaign-focused context."""
        try:
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)

            agg = await session.execute(
                select(
                    func.count(SendLog.id).label("total"),
                    func.count(SendLog.first_open_at).label("opens"),
                    func.count(SendLog.first_click_at).label("clicks"),
                ).where(SendLog.sent_at >= thirty_days_ago)
            )
            row = agg.one()
            total = row.total or 1

            campaigns_list = await self._campaigns_list(session)

            return CAMPAIGN_CONTEXT_TEMPLATE.format(
                campaigns_list=campaigns_list,
                open_rate=round(row.opens / total * 100, 1),
                click_rate=round(row.clicks / total * 100, 1),
            )
        except Exception as e:
            logger.warning(f"Failed to build campaign context: {e}")
            return "\nNote: Could not load campaign data."

    async def _campaigns_list(self, session: AsyncSession, limit: int = 10) -> str:
        """Format active campaigns as text for the system prompt."""
        result = await session.execute(
            select(Campaign)
            .order_by(Campaign.created_at.desc())
            .limit(limit)
        )
        campaigns = result.scalars().all()
        if not campaigns:
            return "No campaigns yet."

        lines = []
        for c in campaigns:
            sent = c.sent_count or 0
            opened = c.opened_count or 0
            or_pct = round(opened / sent * 100, 1) if sent > 0 else 0
            lines.append(f"- {c.name} ({c.status}): {sent} sent, {or_pct}% open rate")
        return "\n".join(lines)


# Singleton
c1_context = C1ContextBuilder()
