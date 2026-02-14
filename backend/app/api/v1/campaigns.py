"""
Campaign API endpoints.

Provides CRUD operations for email campaigns and sending functionality.
All campaign data is stored in PostgreSQL via SQLAlchemy.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenData, require_auth
from app.db.postgres import get_db_session, get_db
from app.models.campaign import Campaign
from app.services.campaigns import campaign_service, CampaignStatus
from app.services.campaign_pipeline import campaign_pipeline
from app.services.send_scheduler import send_scheduler
from app.services.tracking_service import tracking_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


# ============================================================================
# Request/Response Models
# ============================================================================


class CampaignCreate(BaseModel):
    """Request to create a new campaign."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    prospect_list_id: Optional[str] = Field(None, description="ID of the prospect list")
    from_name: Optional[str] = Field(None, max_length=255)
    from_address: Optional[str] = Field(None, max_length=255)
    daily_limit: int = Field(default=100, ge=1, le=10000)
    template_id: Optional[str] = Field(None, description="ID of the email template to use")
    sequence_id: Optional[str] = Field(None, description="Optional sequence to link to")


class CampaignUpdate(BaseModel):
    """Request to update a campaign."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    from_name: Optional[str] = Field(None, max_length=255)
    from_address: Optional[str] = Field(None, max_length=255)
    daily_limit: Optional[int] = Field(None, ge=1, le=10000)


class CampaignResponse(BaseModel):
    """Campaign response."""
    id: str
    name: str
    description: Optional[str] = None
    status: str
    owner_id: str
    from_name: Optional[str] = None
    from_address: Optional[str] = None
    prospect_list_id: Optional[str] = None
    daily_limit: int = 100
    total_prospects: int = 0
    sent_count: int = 0
    opened_count: int = 0
    clicked_count: int = 0
    replied_count: int = 0
    bounced_count: int = 0
    unsubscribed_count: int = 0
    activated_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CampaignListResponse(BaseModel):
    """List of campaigns response."""
    campaigns: list[CampaignResponse]
    total: int
    limit: int
    offset: int


class AddRecipientsRequest(BaseModel):
    """Request to add recipients to a campaign."""
    prospect_ids: list[str] = Field(..., min_length=1)


class CampaignStatsResponse(BaseModel):
    """Campaign statistics response."""
    sent: int
    delivered: int
    opened: int
    clicked: int
    replied: int
    bounced: int
    open_rate: float
    click_rate: float
    reply_rate: float


class RecipientResponse(BaseModel):
    """Campaign recipient response."""
    prospect_id: str
    email: str
    first_name: str = ""
    last_name: str = ""
    company: str = ""
    title: str = ""
    status: str
    sent_at: Optional[str] = None
    message_id: Optional[str] = None


# ============================================================================
# Helper Functions
# ============================================================================


def campaign_to_response(campaign: Campaign) -> CampaignResponse:
    """Convert SQLAlchemy Campaign model to response."""
    return CampaignResponse(
        id=str(campaign.id),
        name=campaign.name,
        description=campaign.description,
        status=campaign.status,
        owner_id=str(campaign.created_by) if campaign.created_by else "",
        from_name=campaign.from_name,
        from_address=campaign.from_address,
        prospect_list_id=str(campaign.prospect_list_id) if campaign.prospect_list_id else None,
        daily_limit=campaign.daily_limit or 100,
        total_prospects=campaign.total_prospects or 0,
        sent_count=campaign.sent_count or 0,
        opened_count=campaign.opened_count or 0,
        clicked_count=campaign.clicked_count or 0,
        replied_count=campaign.replied_count or 0,
        bounced_count=campaign.bounced_count or 0,
        unsubscribed_count=campaign.unsubscribed_count or 0,
        activated_at=campaign.activated_at.isoformat() if campaign.activated_at else None,
        completed_at=campaign.completed_at.isoformat() if campaign.completed_at else None,
        created_at=campaign.created_at.isoformat() if campaign.created_at else None,
        updated_at=campaign.updated_at.isoformat() if campaign.updated_at else None,
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.post("", response_model=CampaignResponse, status_code=201)
async def create_campaign(
    request: CampaignCreate,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Create a new campaign.

    A campaign uses a template to send emails to a set of prospects.
    """
    try:
        campaign = await campaign_service.create_campaign(
            session=session,
            name=request.name,
            owner_id=user.user_id,
            template_id=request.template_id,
            sequence_id=request.sequence_id,
            description=request.description,
            prospect_list_id=request.prospect_list_id,
            from_name=request.from_name,
            from_address=request.from_address,
            daily_limit=request.daily_limit,
        )
        return campaign_to_response(campaign)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=CampaignListResponse)
async def list_campaigns(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(None, description="Filter by status"),
    my_campaigns: bool = Query(default=False, description="Only show my campaigns"),
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    List all campaigns.

    Set my_campaigns=true to only see campaigns you own.
    Filter by status: draft, scheduled, running, paused, completed, failed
    """
    campaign_status = None
    if status:
        try:
            campaign_status = CampaignStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {[s.value for s in CampaignStatus]}",
            )

    owner_id = user.user_id if my_campaigns else None
    campaigns = await campaign_service.list_campaigns(
        session=session,
        owner_id=owner_id,
        status=campaign_status,
        limit=limit,
        offset=offset,
    )

    return CampaignListResponse(
        campaigns=[campaign_to_response(c) for c in campaigns],
        total=len(campaigns),
        limit=limit,
        offset=offset,
    )


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Get a campaign by ID."""
    campaign = await campaign_service.get_campaign(session, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign_to_response(campaign)


@router.get("/{campaign_id}/stats", response_model=CampaignStatsResponse)
async def get_campaign_stats(
    campaign_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get campaign statistics.

    Returns delivery, engagement, and conversion metrics.
    """
    stats = await campaign_service.get_campaign_stats(session, campaign_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return CampaignStatsResponse(**stats)


@router.post("/{campaign_id}/recipients")
async def add_recipients(
    campaign_id: str,
    request: AddRecipientsRequest,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Add prospects as recipients to a campaign.

    Prospects will be queued to receive the campaign email.
    """
    campaign = await campaign_service.get_campaign(session, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if str(campaign.created_by) != user.user_id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    if campaign.status not in ["draft", "paused"]:
        raise HTTPException(
            status_code=400,
            detail="Can only add recipients to draft or paused campaigns",
        )

    added = await campaign_service.add_recipients(session, campaign_id, request.prospect_ids)
    return {"added": added, "total_requested": len(request.prospect_ids)}


@router.get("/{campaign_id}/recipients", response_model=list[RecipientResponse])
async def get_recipients(
    campaign_id: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(default=100, ge=1, le=500),
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get campaign recipients.

    Filter by status: enrolled, active, completed, paused, bounced, unsubscribed
    """
    recipients = await campaign_service.get_recipients(session, campaign_id, status=status, limit=limit)
    return [
        RecipientResponse(
            prospect_id=r["prospect_id"],
            email=r["email"],
            first_name=r["first_name"],
            last_name=r["last_name"],
            company=r["company"],
            title=r["title"],
            status=r["status"],
            sent_at=r["sent_at"].isoformat() if r["sent_at"] else None,
            message_id=r["message_id"],
        )
        for r in recipients
    ]


async def _send_campaign_background(campaign_id: str):
    """Background task to send campaign emails."""
    async with get_db() as session:
        recipients = await campaign_service.get_recipients(session, campaign_id, status="enrolled")

        for recipient in recipients:
            try:
                logger.info("Processing recipient %s for campaign %s", recipient["email"], campaign_id)
            except Exception as e:
                logger.error("Error processing %s: %s", recipient["email"], e)

        # Check if all recipients have been processed
        remaining = await campaign_service.get_recipients(session, campaign_id, status="enrolled", limit=1)
        if not remaining:
            await campaign_service.update_campaign_status(session, campaign_id, CampaignStatus.COMPLETED)


@router.post("/{campaign_id}/send")
async def send_campaign(
    campaign_id: str,
    background_tasks: BackgroundTasks,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Start sending the campaign.

    Emails will be sent in the background. Check /campaigns/{id}/stats for progress.
    """
    campaign = await campaign_service.get_campaign(session, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if str(campaign.created_by) != user.user_id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    if campaign.status == CampaignStatus.RUNNING.value:
        raise HTTPException(status_code=400, detail="Campaign is already running")

    if campaign.status == CampaignStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="Campaign is already completed")

    await campaign_service.update_campaign_status(session, campaign_id, CampaignStatus.RUNNING)
    background_tasks.add_task(_send_campaign_background, campaign_id)

    return {"message": "Campaign sending started", "campaign_id": campaign_id}


@router.post("/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Pause a running campaign.

    Emails that haven't been sent yet will be held.
    """
    campaign = await campaign_service.get_campaign(session, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if str(campaign.created_by) != user.user_id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    if campaign.status != CampaignStatus.RUNNING.value:
        raise HTTPException(status_code=400, detail="Campaign is not running")

    await campaign_service.update_campaign_status(session, campaign_id, CampaignStatus.PAUSED)
    return {"message": "Campaign paused", "campaign_id": campaign_id}


@router.post("/{campaign_id}/resume")
async def resume_campaign(
    campaign_id: str,
    background_tasks: BackgroundTasks,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Resume a paused campaign."""
    campaign = await campaign_service.get_campaign(session, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if str(campaign.created_by) != user.user_id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    if campaign.status != CampaignStatus.PAUSED.value:
        raise HTTPException(status_code=400, detail="Campaign is not paused")

    await campaign_service.update_campaign_status(session, campaign_id, CampaignStatus.RUNNING)
    background_tasks.add_task(_send_campaign_background, campaign_id)

    return {"message": "Campaign resumed", "campaign_id": campaign_id}


# ============================================================================
# Pipeline Status & Scheduling Endpoints
# ============================================================================


class PipelineStatusResponse(BaseModel):
    """Current status of the AI pipeline for a campaign."""
    status: str
    current_step: Optional[str] = None
    step_index: Optional[int] = None
    total_steps: Optional[int] = None
    progress: Optional[int] = None
    error: Optional[str] = None
    run_id: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    total_emails: Optional[int] = None


class ScheduleResponse(BaseModel):
    """Campaign schedule summary."""
    total_scheduled: int
    first_send: Optional[str] = None
    last_send: Optional[str] = None


class TrackingStatsResponse(BaseModel):
    """Detailed tracking stats for a campaign."""
    campaign_id: str
    campaign_name: str = ""
    campaign_status: str = ""
    total_prospects: int = 0
    sent: int = 0
    delivered: int = 0
    opens: dict = {}
    clicks: dict = {}
    bounces: dict = {}
    replies: dict = {}
    unsubscribes: int = 0
    delivery_rate: float = 0.0


@router.get("/{campaign_id}/pipeline-status", response_model=PipelineStatusResponse)
async def get_pipeline_status(
    campaign_id: str,
    user: TokenData = Depends(require_auth),
):
    """Poll the AI pipeline status for a campaign.

    Returns the current step, progress percentage, and any errors.
    Frontend should poll this every 2-3 seconds while pipeline is running.
    """
    status = await campaign_pipeline.get_pipeline_status(campaign_id)
    if not status:
        return PipelineStatusResponse(status="not_started")

    return PipelineStatusResponse(**status)


@router.get("/{campaign_id}/pipeline-results")
async def get_pipeline_results(
    campaign_id: str,
    user: TokenData = Depends(require_auth),
):
    """Get the full pipeline results after completion.

    Returns essence, segments, pitches, and generated emails.
    """
    results = await campaign_pipeline.get_all_results(campaign_id)
    if not results:
        raise HTTPException(status_code=404, detail="No pipeline results found")

    return results


@router.get("/{campaign_id}/pipeline-step/{step_name}")
async def get_pipeline_step_result(
    campaign_id: str,
    step_name: str,
    user: TokenData = Depends(require_auth),
):
    """Get the result of a specific pipeline step.

    Valid step names: extract_essence, research_prospects, segment_prospects,
    generate_pitches, personalize_emails, generate_html
    """
    valid_steps = [
        "extract_essence", "research_prospects", "segment_prospects",
        "generate_pitches", "personalize_emails", "generate_html",
    ]
    if step_name not in valid_steps:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid step name. Must be one of: {valid_steps}",
        )

    result = await campaign_pipeline.get_step_result(campaign_id, step_name)
    if not result:
        raise HTTPException(status_code=404, detail=f"No result for step '{step_name}'")

    return result


@router.post("/{campaign_id}/schedule", response_model=ScheduleResponse)
async def schedule_campaign(
    campaign_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Schedule campaign sends with intelligent timing.

    Uses timezone detection and B2B heuristics to find optimal send times
    for each prospect (Tue-Thu, 10am-2pm local time).
    """
    campaign = await campaign_service.get_campaign(session, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if str(campaign.created_by) != user.user_id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get pipeline results for personalized emails
    results = await campaign_pipeline.get_all_results(campaign_id)
    if not results or not results.get("emails"):
        raise HTTPException(
            status_code=400,
            detail="Run the AI pipeline first to generate personalized emails",
        )

    schedule = await send_scheduler.schedule_campaign_sends(
        campaign_id=campaign_id,
        personalized_emails=results["emails"],
    )

    return ScheduleResponse(
        total_scheduled=len(schedule),
        first_send=schedule[0]["send_at"] if schedule else None,
        last_send=schedule[-1]["send_at"] if schedule else None,
    )


@router.get("/{campaign_id}/schedule")
async def get_campaign_schedule(
    campaign_id: str,
    user: TokenData = Depends(require_auth),
):
    """Get the current send schedule for a campaign."""
    stats = await send_scheduler.get_campaign_schedule_stats(campaign_id)
    if not stats:
        raise HTTPException(status_code=404, detail="No schedule found for this campaign")

    return stats


@router.get("/{campaign_id}/tracking", response_model=TrackingStatsResponse)
async def get_campaign_tracking(
    campaign_id: str,
    user: TokenData = Depends(require_auth),
):
    """Get comprehensive tracking stats for a campaign.

    Combines real-time Redis counters with database aggregates.
    Results are cached for 5 minutes.
    """
    stats = await tracking_service.get_campaign_tracking_stats(campaign_id)
    if stats.get("error"):
        raise HTTPException(status_code=404, detail=stats["error"])

    return TrackingStatsResponse(**stats)
