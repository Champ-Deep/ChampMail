"""
UTM Tracking API endpoints.

Manages UTM presets, campaign UTM configurations, link click analytics,
and provides UTM-attribution breakdowns for campaign performance analysis.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenData, require_auth
from app.db.postgres import get_db_session
from app.db.redis import redis_client
from app.models.campaign import Campaign
from app.models.utm import CampaignUTMConfig, LinkClick, UTMPreset
from app.services.utm_service import utm_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/utm", tags=["UTM"])


# ============================================================================
# Request / Response Models
# ============================================================================


class UTMPresetCreate(BaseModel):
    """Create a new UTM preset."""
    name: str
    utm_source: str = "champmail"
    utm_medium: str = "email"
    utm_campaign: str = "{{campaign_name_slug}}"
    utm_content: Optional[str] = None
    utm_term: Optional[str] = None
    custom_params: Optional[dict] = None


class UTMPresetUpdate(BaseModel):
    """Update an existing UTM preset."""
    name: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    utm_term: Optional[str] = None
    custom_params: Optional[dict] = None


class UTMPresetResponse(BaseModel):
    """UTM preset response."""
    id: str
    team_id: str
    name: str
    is_default: bool = False
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    utm_term: Optional[str] = None
    custom_params: Optional[dict] = None
    created_by: Optional[str] = None
    created_at: str


class CampaignUTMConfigUpdate(BaseModel):
    """Create or update a campaign UTM config."""
    enabled: bool = True
    preset_id: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    utm_term: Optional[str] = None
    custom_params: Optional[dict] = None
    link_overrides: Optional[dict] = None
    preserve_existing_utm: bool = True


class CampaignUTMConfigResponse(BaseModel):
    """Campaign UTM config response."""
    id: str
    campaign_id: str
    preset_id: Optional[str] = None
    enabled: bool = True
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    utm_term: Optional[str] = None
    custom_params: Optional[dict] = None
    link_overrides: Optional[dict] = None
    preserve_existing_utm: bool = True
    team_id: str
    created_at: str
    updated_at: str


class UTMBreakdownItem(BaseModel):
    """Single item in a UTM breakdown."""
    group_key: str
    group_value: str
    total_links: int
    total_clicks: int
    unique_clicks: int
    click_rate: float


class LinkPerformanceItem(BaseModel):
    """Link-level performance metrics."""
    original_url: str
    anchor_text: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    utm_term: Optional[str] = None
    click_count: int = 0
    unique_clicks: int = 0
    first_clicked_at: Optional[str] = None


class UTMOverviewResponse(BaseModel):
    """UTM analytics overview."""
    total_tracked_links: int = 0
    total_clicks: int = 0
    unique_clicks: int = 0
    overall_click_rate: float = 0.0
    top_sources: list = []
    top_campaigns: list = []


# ============================================================================
# Helper to serialize a model to response dict
# ============================================================================


def _preset_to_response(preset: UTMPreset) -> dict:
    """Convert a UTMPreset ORM object to a response dict."""
    return {
        "id": str(preset.id),
        "team_id": str(preset.team_id),
        "name": preset.name,
        "is_default": preset.is_default or False,
        "utm_source": preset.utm_source,
        "utm_medium": preset.utm_medium,
        "utm_campaign": preset.utm_campaign,
        "utm_content": preset.utm_content,
        "utm_term": preset.utm_term,
        "custom_params": preset.custom_params,
        "created_by": str(preset.created_by) if preset.created_by else None,
        "created_at": preset.created_at.isoformat() if preset.created_at else "",
    }


def _config_to_response(config: CampaignUTMConfig) -> dict:
    """Convert a CampaignUTMConfig ORM object to a response dict."""
    return {
        "id": str(config.id),
        "campaign_id": str(config.campaign_id),
        "preset_id": str(config.preset_id) if config.preset_id else None,
        "enabled": config.enabled if config.enabled is not None else True,
        "utm_source": config.utm_source,
        "utm_medium": config.utm_medium,
        "utm_campaign": config.utm_campaign,
        "utm_content": config.utm_content,
        "utm_term": config.utm_term,
        "custom_params": config.custom_params,
        "link_overrides": config.link_overrides,
        "preserve_existing_utm": config.preserve_existing_utm if config.preserve_existing_utm is not None else True,
        "team_id": str(config.team_id),
        "created_at": config.created_at.isoformat() if config.created_at else "",
        "updated_at": config.updated_at.isoformat() if config.updated_at else "",
    }


# ============================================================================
# Preset Endpoints
# ============================================================================


@router.get("/presets", response_model=List[UTMPresetResponse])
async def list_presets(
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """List all UTM presets for the user's team."""
    result = await session.execute(
        select(UTMPreset)
        .where(UTMPreset.team_id == user.team_id)
        .order_by(UTMPreset.created_at.desc())
    )
    presets = result.scalars().all()
    return [_preset_to_response(p) for p in presets]


@router.post("/presets", response_model=UTMPresetResponse, status_code=201)
async def create_preset(
    data: UTMPresetCreate,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Create a new UTM preset."""
    from uuid import uuid4

    preset = UTMPreset(
        id=uuid4(),
        team_id=user.team_id,
        name=data.name,
        utm_source=data.utm_source,
        utm_medium=data.utm_medium,
        utm_campaign=data.utm_campaign,
        utm_content=data.utm_content,
        utm_term=data.utm_term,
        custom_params=data.custom_params,
        created_by=user.user_id,
    )
    session.add(preset)
    await session.flush()

    return _preset_to_response(preset)


@router.get("/presets/{preset_id}", response_model=UTMPresetResponse)
async def get_preset(
    preset_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Get a specific UTM preset."""
    result = await session.execute(
        select(UTMPreset).where(
            UTMPreset.id == preset_id,
            UTMPreset.team_id == user.team_id,
        )
    )
    preset = result.scalar_one_or_none()
    if not preset:
        raise HTTPException(status_code=404, detail="UTM preset not found")

    return _preset_to_response(preset)


@router.put("/presets/{preset_id}", response_model=UTMPresetResponse)
async def update_preset(
    preset_id: str,
    data: UTMPresetUpdate,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Update a UTM preset."""
    result = await session.execute(
        select(UTMPreset).where(
            UTMPreset.id == preset_id,
            UTMPreset.team_id == user.team_id,
        )
    )
    preset = result.scalar_one_or_none()
    if not preset:
        raise HTTPException(status_code=404, detail="UTM preset not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(preset, field, value)
    preset.updated_at = datetime.utcnow()

    await session.flush()
    return _preset_to_response(preset)


@router.delete("/presets/{preset_id}", status_code=204)
async def delete_preset(
    preset_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Delete a UTM preset."""
    result = await session.execute(
        select(UTMPreset).where(
            UTMPreset.id == preset_id,
            UTMPreset.team_id == user.team_id,
        )
    )
    preset = result.scalar_one_or_none()
    if not preset:
        raise HTTPException(status_code=404, detail="UTM preset not found")

    await session.delete(preset)
    await session.flush()


@router.post("/presets/{preset_id}/default", response_model=UTMPresetResponse)
async def set_default_preset(
    preset_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Set a preset as the team's default, clearing default on all others."""
    # Verify preset exists and belongs to team
    result = await session.execute(
        select(UTMPreset).where(
            UTMPreset.id == preset_id,
            UTMPreset.team_id == user.team_id,
        )
    )
    preset = result.scalar_one_or_none()
    if not preset:
        raise HTTPException(status_code=404, detail="UTM preset not found")

    # Clear is_default on all presets for this team
    await session.execute(
        update(UTMPreset)
        .where(UTMPreset.team_id == user.team_id)
        .values(is_default=False)
    )

    # Set this one as default
    preset.is_default = True
    preset.updated_at = datetime.utcnow()

    await session.flush()
    return _preset_to_response(preset)


# ============================================================================
# Campaign UTM Config Endpoints
# ============================================================================


@router.get("/campaigns/{campaign_id}", response_model=CampaignUTMConfigResponse)
async def get_campaign_utm_config(
    campaign_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Get the UTM configuration for a specific campaign."""
    result = await session.execute(
        select(CampaignUTMConfig).where(
            CampaignUTMConfig.campaign_id == campaign_id,
            CampaignUTMConfig.team_id == user.team_id,
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Campaign UTM config not found")

    return _config_to_response(config)


@router.put("/campaigns/{campaign_id}", response_model=CampaignUTMConfigResponse)
async def upsert_campaign_utm_config(
    campaign_id: str,
    data: CampaignUTMConfigUpdate,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Create or update the UTM configuration for a campaign."""
    from uuid import uuid4

    # Check if config exists
    result = await session.execute(
        select(CampaignUTMConfig).where(
            CampaignUTMConfig.campaign_id == campaign_id,
        )
    )
    config = result.scalar_one_or_none()

    if config:
        # Update existing
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(config, field, value)
        config.updated_at = datetime.utcnow()
    else:
        # Create new
        config = CampaignUTMConfig(
            id=uuid4(),
            campaign_id=campaign_id,
            preset_id=data.preset_id,
            enabled=data.enabled,
            utm_source=data.utm_source,
            utm_medium=data.utm_medium,
            utm_campaign=data.utm_campaign,
            utm_content=data.utm_content,
            utm_term=data.utm_term,
            custom_params=data.custom_params,
            link_overrides=data.link_overrides,
            preserve_existing_utm=data.preserve_existing_utm,
            team_id=user.team_id,
        )
        session.add(config)

    await session.flush()
    return _config_to_response(config)


@router.delete("/campaigns/{campaign_id}", status_code=204)
async def delete_campaign_utm_config(
    campaign_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Delete the UTM configuration for a campaign."""
    result = await session.execute(
        select(CampaignUTMConfig).where(
            CampaignUTMConfig.campaign_id == campaign_id,
            CampaignUTMConfig.team_id == user.team_id,
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Campaign UTM config not found")

    await session.delete(config)
    await session.flush()


@router.post("/campaigns/{campaign_id}/auto", response_model=CampaignUTMConfigResponse)
async def auto_generate_utm_config(
    campaign_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Auto-generate UTM config for a campaign from team's default preset."""
    config = await utm_service.auto_generate_config(
        campaign_id=campaign_id,
        team_id=user.team_id,
        session=session,
    )
    return _config_to_response(config)


@router.post("/campaigns/{campaign_id}/preview")
async def preview_utm_injection(
    campaign_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Preview UTM injection on a campaign's HTML template.

    Returns the list of links that would be modified along with their
    UTM parameters, without actually sending or modifying the campaign.
    """
    # Fetch campaign
    campaign_result = await session.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = campaign_result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if not campaign.html_template:
        raise HTTPException(status_code=400, detail="Campaign has no HTML template")

    # Resolve UTM params
    utm_params = await utm_service.resolve_utm_params(
        campaign_id=campaign_id,
        prospect_data=None,
        segment_name=None,
        session=session,
    )

    if not utm_params:
        return {
            "campaign_id": str(campaign_id),
            "utm_params": {},
            "links": [],
            "message": "No UTM configuration found for this campaign",
        }

    # Get config for preserve_existing and link_overrides
    config_result = await session.execute(
        select(CampaignUTMConfig).where(
            CampaignUTMConfig.campaign_id == campaign_id
        )
    )
    config = config_result.scalar_one_or_none()

    preserve_existing = config.preserve_existing_utm if config else True
    link_overrides = config.link_overrides if config else None

    # Inject UTM params into HTML
    _modified_html, links_metadata = utm_service.inject_utm_into_html(
        html_body=campaign.html_template,
        utm_params=utm_params,
        preserve_existing=preserve_existing,
        link_overrides=link_overrides,
    )

    return {
        "campaign_id": str(campaign_id),
        "utm_params": utm_params,
        "links": links_metadata,
        "total_links": len(links_metadata),
    }


# ============================================================================
# UTM Analytics Endpoints
# ============================================================================


@router.get("/analytics/overview", response_model=UTMOverviewResponse)
async def get_utm_overview(
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Get UTM analytics overview: total tracked links, clicks, top sources/campaigns.

    Results are cached in Redis for 5 minutes.
    """
    cache_key = f"utm:overview:{user.team_id or user.user_id}"
    cached = await redis_client.get_json(cache_key)
    if cached:
        return UTMOverviewResponse(**cached)

    # Total tracked links, clicks, unique clicks
    agg = await session.execute(
        select(
            func.count(LinkClick.id).label("total_links"),
            func.coalesce(func.sum(LinkClick.click_count), 0).label("total_clicks"),
            func.coalesce(func.sum(LinkClick.unique_clicks), 0).label("unique_clicks"),
        )
        .where(LinkClick.team_id == user.team_id)
    )
    row = agg.one()
    total_links = row.total_links or 0
    total_clicks = int(row.total_clicks) if row.total_clicks else 0
    unique_clicks = int(row.unique_clicks) if row.unique_clicks else 0
    overall_click_rate = round((unique_clicks / total_links * 100) if total_links > 0 else 0.0, 2)

    # Top 5 sources by total clicks
    source_result = await session.execute(
        select(
            LinkClick.utm_source,
            func.coalesce(func.sum(LinkClick.click_count), 0).label("total_clicks"),
        )
        .where(LinkClick.team_id == user.team_id)
        .where(LinkClick.utm_source.isnot(None))
        .group_by(LinkClick.utm_source)
        .order_by(func.sum(LinkClick.click_count).desc())
        .limit(5)
    )
    top_sources = [
        {"source": r.utm_source, "clicks": int(r.total_clicks)}
        for r in source_result.all()
    ]

    # Top 5 campaigns by total clicks
    campaign_result = await session.execute(
        select(
            LinkClick.utm_campaign,
            func.coalesce(func.sum(LinkClick.click_count), 0).label("total_clicks"),
        )
        .where(LinkClick.team_id == user.team_id)
        .where(LinkClick.utm_campaign.isnot(None))
        .group_by(LinkClick.utm_campaign)
        .order_by(func.sum(LinkClick.click_count).desc())
        .limit(5)
    )
    top_campaigns = [
        {"campaign": r.utm_campaign, "clicks": int(r.total_clicks)}
        for r in campaign_result.all()
    ]

    overview = UTMOverviewResponse(
        total_tracked_links=total_links,
        total_clicks=total_clicks,
        unique_clicks=unique_clicks,
        overall_click_rate=overall_click_rate,
        top_sources=top_sources,
        top_campaigns=top_campaigns,
    )

    # Cache for 5 minutes
    await redis_client.set_json(cache_key, overview.model_dump(), ex=300)

    return overview


@router.get("/analytics/campaigns/{campaign_id}")
async def get_campaign_utm_analytics(
    campaign_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Get UTM analytics for a specific campaign, grouped by source, medium, etc."""
    breakdowns = {}

    for utm_field, column in [
        ("source", LinkClick.utm_source),
        ("medium", LinkClick.utm_medium),
        ("campaign", LinkClick.utm_campaign),
        ("content", LinkClick.utm_content),
        ("term", LinkClick.utm_term),
    ]:
        result = await session.execute(
            select(
                column.label("group_value"),
                func.count(LinkClick.id).label("total_links"),
                func.coalesce(func.sum(LinkClick.click_count), 0).label("total_clicks"),
                func.coalesce(func.sum(LinkClick.unique_clicks), 0).label("unique_clicks"),
            )
            .where(
                LinkClick.campaign_id == campaign_id,
                LinkClick.team_id == user.team_id,
                column.isnot(None),
            )
            .group_by(column)
            .order_by(func.sum(LinkClick.click_count).desc())
        )

        items = []
        for row in result.all():
            total_links = row.total_links or 0
            unique = int(row.unique_clicks) if row.unique_clicks else 0
            items.append({
                "group_key": utm_field,
                "group_value": row.group_value,
                "total_links": total_links,
                "total_clicks": int(row.total_clicks) if row.total_clicks else 0,
                "unique_clicks": unique,
                "click_rate": round((unique / total_links * 100) if total_links > 0 else 0.0, 2),
            })

        breakdowns[utm_field] = items

    return {"campaign_id": campaign_id, "breakdowns": breakdowns}


@router.get("/analytics/breakdown", response_model=List[UTMBreakdownItem])
async def get_utm_breakdown(
    group_by: str = Query(
        default="source",
        description="UTM field to group by: source, medium, campaign, content, term",
    ),
    campaign_id: Optional[str] = Query(default=None, description="Filter by campaign"),
    days: int = Query(default=30, ge=1, le=365, description="Number of days to look back"),
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Flexible UTM breakdown by any UTM field, optionally filtered by campaign and time range."""
    # Map group_by to column
    column_map = {
        "source": LinkClick.utm_source,
        "medium": LinkClick.utm_medium,
        "campaign": LinkClick.utm_campaign,
        "content": LinkClick.utm_content,
        "term": LinkClick.utm_term,
    }

    column = column_map.get(group_by)
    if not column:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid group_by value '{group_by}'. Must be one of: source, medium, campaign, content, term",
        )

    start_date = datetime.utcnow() - timedelta(days=days)

    conditions = [
        LinkClick.team_id == user.team_id,
        LinkClick.created_at >= start_date,
        column.isnot(None),
    ]
    if campaign_id:
        conditions.append(LinkClick.campaign_id == campaign_id)

    result = await session.execute(
        select(
            column.label("group_value"),
            func.count(LinkClick.id).label("total_links"),
            func.coalesce(func.sum(LinkClick.click_count), 0).label("total_clicks"),
            func.coalesce(func.sum(LinkClick.unique_clicks), 0).label("unique_clicks"),
        )
        .where(*conditions)
        .group_by(column)
        .order_by(func.sum(LinkClick.click_count).desc())
    )

    items = []
    for row in result.all():
        total_links = row.total_links or 0
        unique = int(row.unique_clicks) if row.unique_clicks else 0
        items.append(UTMBreakdownItem(
            group_key=group_by,
            group_value=row.group_value,
            total_links=total_links,
            total_clicks=int(row.total_clicks) if row.total_clicks else 0,
            unique_clicks=unique,
            click_rate=round((unique / total_links * 100) if total_links > 0 else 0.0, 2),
        ))

    return items


@router.get("/analytics/links/{campaign_id}", response_model=List[LinkPerformanceItem])
async def get_campaign_link_performance(
    campaign_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """List all unique links for a campaign with click stats, ordered by click_count desc."""
    result = await session.execute(
        select(
            LinkClick.original_url,
            LinkClick.anchor_text,
            LinkClick.utm_source,
            LinkClick.utm_medium,
            LinkClick.utm_campaign,
            LinkClick.utm_content,
            LinkClick.utm_term,
            func.coalesce(func.sum(LinkClick.click_count), 0).label("click_count"),
            func.coalesce(func.sum(LinkClick.unique_clicks), 0).label("unique_clicks"),
            func.min(LinkClick.first_clicked_at).label("first_clicked_at"),
        )
        .where(
            LinkClick.campaign_id == campaign_id,
            LinkClick.team_id == user.team_id,
        )
        .group_by(
            LinkClick.original_url,
            LinkClick.anchor_text,
            LinkClick.utm_source,
            LinkClick.utm_medium,
            LinkClick.utm_campaign,
            LinkClick.utm_content,
            LinkClick.utm_term,
        )
        .order_by(func.sum(LinkClick.click_count).desc())
    )

    items = []
    for row in result.all():
        items.append(LinkPerformanceItem(
            original_url=row.original_url,
            anchor_text=row.anchor_text,
            utm_source=row.utm_source,
            utm_medium=row.utm_medium,
            utm_campaign=row.utm_campaign,
            utm_content=row.utm_content,
            utm_term=row.utm_term,
            click_count=int(row.click_count) if row.click_count else 0,
            unique_clicks=int(row.unique_clicks) if row.unique_clicks else 0,
            first_clicked_at=row.first_clicked_at.isoformat() if row.first_clicked_at else None,
        ))

    return items
