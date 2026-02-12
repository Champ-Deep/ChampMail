"""
Campaign API endpoints.

Provides CRUD operations for email campaigns and sending functionality.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from pydantic import BaseModel, Field

from app.core.security import TokenData, require_auth
from app.services.campaigns import (
    campaign_service,
    Campaign,
    CampaignStatus,
)


router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


# ============================================================================
# Request/Response Models
# ============================================================================


class CampaignCreate(BaseModel):
    """Request to create a new campaign."""
    name: str = Field(..., min_length=1, max_length=200)
    template_id: str = Field(..., description="ID of the email template to use")
    sequence_id: Optional[str] = Field(None, description="Optional sequence to link to")


class CampaignUpdate(BaseModel):
    """Request to update a campaign."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)


class CampaignResponse(BaseModel):
    """Campaign response."""
    id: str
    name: str
    template_id: str
    sequence_id: Optional[str] = None
    status: str
    owner_id: str
    sent_count: int = 0
    delivered_count: int = 0
    opened_count: int = 0
    clicked_count: int = 0
    replied_count: int = 0
    bounced_count: int = 0
    scheduled_at: Optional[str] = None
    started_at: Optional[str] = None
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
    """Convert Campaign to response model."""
    return CampaignResponse(
        id=campaign.id,
        name=campaign.name,
        template_id=campaign.template_id,
        sequence_id=campaign.sequence_id,
        status=campaign.status.value,
        owner_id=campaign.owner_id,
        sent_count=campaign.sent_count,
        delivered_count=campaign.delivered_count,
        opened_count=campaign.opened_count,
        clicked_count=campaign.clicked_count,
        replied_count=campaign.replied_count,
        bounced_count=campaign.bounced_count,
        scheduled_at=campaign.scheduled_at.isoformat() if campaign.scheduled_at else None,
        started_at=campaign.started_at.isoformat() if campaign.started_at else None,
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
):
    """
    Create a new campaign.

    A campaign uses a template to send emails to a set of prospects.
    """
    try:
        campaign = campaign_service.create_campaign(
            name=request.name,
            template_id=request.template_id,
            owner_id=user.user_id,
            sequence_id=request.sequence_id,
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
    campaigns = campaign_service.list_campaigns(
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
):
    """
    Get a campaign by ID.
    """
    campaign = campaign_service.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign_to_response(campaign)


@router.get("/{campaign_id}/stats", response_model=CampaignStatsResponse)
async def get_campaign_stats(
    campaign_id: str,
    user: TokenData = Depends(require_auth),
):
    """
    Get campaign statistics.

    Returns delivery, engagement, and conversion metrics.
    """
    stats = campaign_service.get_campaign_stats(campaign_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return CampaignStatsResponse(**stats)


@router.post("/{campaign_id}/recipients")
async def add_recipients(
    campaign_id: str,
    request: AddRecipientsRequest,
    user: TokenData = Depends(require_auth),
):
    """
    Add prospects as recipients to a campaign.

    Prospects will be queued to receive the campaign email.
    """
    campaign = campaign_service.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.owner_id != user.user_id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    if campaign.status not in [CampaignStatus.DRAFT, CampaignStatus.PAUSED]:
        raise HTTPException(
            status_code=400,
            detail="Can only add recipients to draft or paused campaigns",
        )

    added = campaign_service.add_recipients(campaign_id, request.prospect_ids)
    return {"added": added, "total_requested": len(request.prospect_ids)}


@router.get("/{campaign_id}/recipients", response_model=list[RecipientResponse])
async def get_recipients(
    campaign_id: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(default=100, ge=1, le=500),
    user: TokenData = Depends(require_auth),
):
    """
    Get campaign recipients.

    Filter by status: pending, sent, delivered, opened, clicked, replied, bounced
    """
    recipients = campaign_service.get_recipients(campaign_id, status=status, limit=limit)
    return [
        RecipientResponse(
            prospect_id=r.prospect_id,
            email=r.email,
            first_name=r.first_name,
            last_name=r.last_name,
            company=r.company,
            title=r.title,
            status=r.status,
            sent_at=r.sent_at.isoformat() if r.sent_at else None,
            message_id=r.message_id,
        )
        for r in recipients
    ]


async def _send_campaign_background(campaign_id: str):
    """Background task to send campaign emails."""
    recipients = campaign_service.get_recipients(campaign_id, status='pending')

    for recipient in recipients:
        try:
            await campaign_service.send_to_recipient(campaign_id, recipient)
        except Exception as e:
            print(f"Error sending to {recipient.email}: {e}")

    # Mark campaign as completed
    remaining = campaign_service.get_recipients(campaign_id, status='pending', limit=1)
    if not remaining:
        campaign_service.update_campaign_status(campaign_id, CampaignStatus.COMPLETED)


@router.post("/{campaign_id}/send")
async def send_campaign(
    campaign_id: str,
    background_tasks: BackgroundTasks,
    user: TokenData = Depends(require_auth),
):
    """
    Start sending the campaign.

    Emails will be sent in the background. Check /campaigns/{id}/stats for progress.
    """
    campaign = campaign_service.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.owner_id != user.user_id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    if campaign.status == CampaignStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Campaign is already running")

    if campaign.status == CampaignStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Campaign is already completed")

    # Update status to running
    campaign_service.update_campaign_status(campaign_id, CampaignStatus.RUNNING)

    # Start background sending
    background_tasks.add_task(_send_campaign_background, campaign_id)

    return {"message": "Campaign sending started", "campaign_id": campaign_id}


@router.post("/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: str,
    user: TokenData = Depends(require_auth),
):
    """
    Pause a running campaign.

    Emails that haven't been sent yet will be held.
    """
    campaign = campaign_service.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.owner_id != user.user_id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    if campaign.status != CampaignStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Campaign is not running")

    campaign_service.update_campaign_status(campaign_id, CampaignStatus.PAUSED)
    return {"message": "Campaign paused", "campaign_id": campaign_id}


@router.post("/{campaign_id}/resume")
async def resume_campaign(
    campaign_id: str,
    background_tasks: BackgroundTasks,
    user: TokenData = Depends(require_auth),
):
    """
    Resume a paused campaign.
    """
    campaign = campaign_service.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.owner_id != user.user_id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    if campaign.status != CampaignStatus.PAUSED:
        raise HTTPException(status_code=400, detail="Campaign is not paused")

    # Update status to running
    campaign_service.update_campaign_status(campaign_id, CampaignStatus.RUNNING)

    # Resume background sending
    background_tasks.add_task(_send_campaign_background, campaign_id)

    return {"message": "Campaign resumed", "campaign_id": campaign_id}
