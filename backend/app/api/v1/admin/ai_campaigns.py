"""
AI campaign pipeline endpoints.
Orchestrates the multi-step AI email generation workflow:
  essence -> research -> segment -> pitch -> personalize -> html
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenData, require_auth
from app.db.postgres import get_db_session
from app.services.ai import (
    essence_service,
    research_service,
    segmentation_service,
    pitch_service,
    html_service,
)

router = APIRouter(prefix="/ai-campaigns", tags=["Admin - AI Campaigns"])


# ---------------------------------------------------------------------------
# Pydantic request / response schemas
# ---------------------------------------------------------------------------

# --- Essence ---------------------------------------------------------------

class EssenceRequest(BaseModel):
    """Input for campaign essence extraction."""
    description: str = Field(..., min_length=10, description="Free-text campaign description from the user")
    target_audience: Optional[str] = Field(default=None, description="Optional target audience description")


class EssenceResponse(BaseModel):
    """Extracted campaign essence."""
    value_propositions: List[str]
    pain_points: List[str]
    call_to_action: str
    tone: str
    unique_angle: str
    target_persona: str


# --- Research --------------------------------------------------------------

class ResearchRequest(BaseModel):
    """Input for prospect research."""
    prospect_ids: List[UUID] = Field(..., min_length=1, max_length=200, description="Prospect UUIDs to research")
    concurrency: int = Field(default=3, ge=1, le=10, description="Parallel research requests")


class ProspectResearchResult(BaseModel):
    """Research result for a single prospect."""
    prospect_id: Optional[str]
    prospect_email: Optional[str]
    research_data: Dict[str, Any]


class ResearchResponse(BaseModel):
    """Batch research results."""
    total_requested: int
    total_researched: int
    results: List[ProspectResearchResult]


# --- Segmentation ---------------------------------------------------------

class SegmentRequest(BaseModel):
    """Input for AI-powered segmentation."""
    research_results: List[Dict[str, Any]] = Field(..., min_length=1, description="Research results from the research step")
    campaign_goals: str = Field(..., min_length=5, description="What the campaign aims to achieve")
    campaign_essence: Dict[str, Any] = Field(..., description="Essence extracted in the first step")


class SegmentResponse(BaseModel):
    """Segmentation results."""
    segments: List[Dict[str, Any]]
    strategy: str
    unmatched_pct: float


# --- Pitch ----------------------------------------------------------------

class PitchRequest(BaseModel):
    """Input for segment-level pitch generation."""
    segment: Dict[str, Any] = Field(..., description="Segment object from the segmentation step")
    campaign_essence: Dict[str, Any] = Field(..., description="Campaign essence")
    sample_research: List[Dict[str, Any]] = Field(default_factory=list, description="Sample prospect research for context")


class PitchResponse(BaseModel):
    """Generated pitch for a segment."""
    pitch_angle: str
    key_messages: List[str]
    subject_lines: List[str]
    body_template: str
    follow_up_templates: List[Dict[str, Any]]
    personalization_variables: List[str]


# --- Personalize ----------------------------------------------------------

class PersonalizeRequest(BaseModel):
    """Input for personalizing a pitch for a specific prospect."""
    pitch: Dict[str, Any] = Field(..., description="Pitch object from the pitch step")
    prospect_id: UUID = Field(..., description="Prospect to personalize for")
    research_data: Dict[str, Any] = Field(..., description="Research data for this prospect")


class PersonalizeResponse(BaseModel):
    """Personalized email content for a single prospect."""
    prospect_id: str
    subject: str
    body: str
    follow_ups: List[Dict[str, Any]]
    variables_used: Dict[str, Any]


# --- HTML -----------------------------------------------------------------

class HTMLRequest(BaseModel):
    """Input for HTML email generation."""
    subject: str = Field(..., description="Email subject line")
    body_text: str = Field(..., description="Plain text email body")
    prospect_id: UUID = Field(..., description="Target prospect")
    campaign_style: Optional[Dict[str, Any]] = Field(default=None, description="Optional style overrides (primary_color, company_name)")


class HTMLResponse(BaseModel):
    """Generated HTML email."""
    prospect_id: str
    subject: str
    html: str
    generated_at: datetime


# --- Preview --------------------------------------------------------------

class PreviewRequest(BaseModel):
    """Input for a combined personalize + HTML preview."""
    pitch: Dict[str, Any] = Field(..., description="Pitch object")
    prospect_id: UUID = Field(..., description="Prospect to preview for")
    research_data: Dict[str, Any] = Field(..., description="Research data for the prospect")
    campaign_style: Optional[Dict[str, Any]] = Field(default=None, description="Optional style overrides")


class PreviewResponse(BaseModel):
    """Full email preview (personalized text + HTML)."""
    prospect_id: str
    subject: str
    body_text: str
    html: str
    variables_used: Dict[str, Any]
    generated_at: datetime


# --- Full Pipeline --------------------------------------------------------

class FullPipelineRequest(BaseModel):
    """Run the entire campaign pipeline end-to-end."""
    description: str = Field(..., min_length=10, description="Campaign description for essence extraction")
    target_audience: Optional[str] = Field(default=None, description="Target audience description")
    campaign_goals: str = Field(..., min_length=5, description="Campaign goals for segmentation")
    prospect_ids: List[UUID] = Field(..., min_length=1, max_length=100, description="Prospect UUIDs to include")
    campaign_style: Optional[Dict[str, Any]] = Field(default=None, description="Optional style overrides for HTML")
    research_concurrency: int = Field(default=3, ge=1, le=10)


class FullPipelineProspectResult(BaseModel):
    """Result for a single prospect in the full pipeline."""
    prospect_id: str
    segment: str
    subject: str
    body_text: str
    html: str
    variables_used: Dict[str, Any]


class FullPipelineResponse(BaseModel):
    """Complete pipeline output."""
    campaign_essence: Dict[str, Any]
    segments: List[Dict[str, Any]]
    strategy: str
    prospect_results: List[FullPipelineProspectResult]
    total_prospects: int
    total_emails_generated: int
    generated_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _load_prospect(session: AsyncSession, prospect_id: UUID) -> Dict[str, Any]:
    """Load a prospect row from the database as a dict."""
    result = await session.execute(
        text("""
            SELECT id, email, first_name, last_name, company_name,
                   company_domain, company_size, industry, job_title,
                   linkedin_url
            FROM prospects
            WHERE id = :id
        """),
        {"id": str(prospect_id)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prospect {prospect_id} not found",
        )
    return dict(row)


async def _load_prospects_batch(
    session: AsyncSession,
    prospect_ids: List[UUID],
) -> List[Dict[str, Any]]:
    """Load multiple prospects, raising 404 if any are missing."""
    prospects = []
    missing = []
    for pid in prospect_ids:
        result = await session.execute(
            text("""
                SELECT id, email, first_name, last_name, company_name,
                       company_domain, company_size, industry, job_title,
                       linkedin_url
                FROM prospects
                WHERE id = :id
            """),
            {"id": str(pid)},
        )
        row = result.mappings().first()
        if row:
            prospects.append(dict(row))
        else:
            missing.append(str(pid))

    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prospects not found: {', '.join(missing[:10])}",
        )
    return prospects


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/essence",
    response_model=EssenceResponse,
    summary="Extract campaign essence from a user description",
)
async def extract_essence(
    body: EssenceRequest,
    user: TokenData = Depends(require_auth),
):
    """
    Use the AI essence service to distill a free-text campaign description
    into a structured messaging framework (value props, pain points, tone, etc.).
    """
    try:
        result = await essence_service.extract_essence(
            user_input=body.description,
            target_audience=body.target_audience,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI essence extraction failed: {exc}",
        )

    return EssenceResponse(
        value_propositions=result.get("value_propositions", []),
        pain_points=result.get("pain_points", []),
        call_to_action=result.get("call_to_action", ""),
        tone=result.get("tone", "professional"),
        unique_angle=result.get("unique_angle", ""),
        target_persona=result.get("target_persona", ""),
    )


@router.post(
    "/research",
    response_model=ResearchResponse,
    summary="Research prospects using AI",
)
async def research_prospects(
    body: ResearchRequest,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Research a batch of prospects using Perplexity Sonar (via OpenRouter).
    Returns structured company info, industry insights, triggers, and
    personalization hooks for each prospect.
    """
    prospects = await _load_prospects_batch(session, body.prospect_ids)

    # Enrich the dicts with "id" field expected by ResearchService
    for p in prospects:
        p["id"] = p.get("id", "")
        # Map job_title -> title for consistency with research service
        if "job_title" in p and "title" not in p:
            p["title"] = p["job_title"]

    try:
        results = await research_service.research_batch(
            prospects=prospects,
            concurrency=body.concurrency,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI research failed: {exc}",
        )

    return ResearchResponse(
        total_requested=len(body.prospect_ids),
        total_researched=len(results),
        results=[
            ProspectResearchResult(
                prospect_id=r.get("prospect_id"),
                prospect_email=r.get("prospect_email"),
                research_data=r.get("research_data", {}),
            )
            for r in results
        ],
    )


@router.post(
    "/segment",
    response_model=SegmentResponse,
    summary="Segment researched prospects using AI",
)
async def segment_prospects(
    body: SegmentRequest,
    user: TokenData = Depends(require_auth),
):
    """
    Analyze research results and create intelligent prospect segments
    aligned with the campaign goals and essence.
    """
    try:
        result = await segmentation_service.segment_prospects(
            research_data=body.research_results,
            campaign_goals=body.campaign_goals,
            campaign_essence=body.campaign_essence,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI segmentation failed: {exc}",
        )

    return SegmentResponse(
        segments=result.get("segments", []),
        strategy=result.get("strategy", ""),
        unmatched_pct=result.get("unmatched_pct", 0),
    )


@router.post(
    "/pitch",
    response_model=PitchResponse,
    summary="Generate an email pitch for a segment",
)
async def generate_pitch(
    body: PitchRequest,
    user: TokenData = Depends(require_auth),
):
    """
    Generate a segment-specific email pitch including subject lines,
    body template, and follow-up sequences.
    """
    try:
        result = await pitch_service.generate_pitch(
            segment=body.segment,
            campaign_essence=body.campaign_essence,
            sample_research=body.sample_research,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI pitch generation failed: {exc}",
        )

    return PitchResponse(
        pitch_angle=result.get("pitch_angle", ""),
        key_messages=result.get("key_messages", []),
        subject_lines=result.get("subject_lines", []),
        body_template=result.get("body_template", ""),
        follow_up_templates=result.get("follow_up_templates", []),
        personalization_variables=result.get("personalization_variables", []),
    )


@router.post(
    "/personalize",
    response_model=PersonalizeResponse,
    summary="Personalize a pitch for a specific prospect",
)
async def personalize_pitch(
    body: PersonalizeRequest,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Replace template variables in a pitch with prospect-specific data
    drawn from the research step.
    """
    prospect = await _load_prospect(session, body.prospect_id)

    try:
        result = pitch_service.personalize_for_prospect(
            pitch=body.pitch,
            prospect=prospect,
            research_data=body.research_data,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Personalization failed: {exc}",
        )

    return PersonalizeResponse(
        prospect_id=str(body.prospect_id),
        subject=result.get("subject", ""),
        body=result.get("body", ""),
        follow_ups=result.get("follow_ups", []),
        variables_used=result.get("variables_used", {}),
    )


@router.post(
    "/html",
    response_model=HTMLResponse,
    summary="Generate HTML email from personalized text",
)
async def generate_html_email(
    body: HTMLRequest,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Convert a personalized plain-text email into a mobile-responsive
    HTML email ready for sending.
    """
    prospect = await _load_prospect(session, body.prospect_id)

    try:
        html = await html_service.generate_html(
            subject=body.subject,
            body_text=body.body_text,
            prospect=prospect,
            campaign_style=body.campaign_style,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"HTML generation failed: {exc}",
        )

    return HTMLResponse(
        prospect_id=str(body.prospect_id),
        subject=body.subject,
        html=html,
        generated_at=datetime.utcnow(),
    )


@router.post(
    "/preview",
    response_model=PreviewResponse,
    summary="Preview a complete personalized HTML email",
)
async def preview_email(
    body: PreviewRequest,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Convenience endpoint that combines the personalize and HTML generation
    steps into a single call, returning both plain text and HTML.
    """
    prospect = await _load_prospect(session, body.prospect_id)

    # Step 1: personalize
    try:
        personalized = pitch_service.personalize_for_prospect(
            pitch=body.pitch,
            prospect=prospect,
            research_data=body.research_data,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Personalization failed: {exc}",
        )

    subject = personalized.get("subject", "")
    body_text = personalized.get("body", "")

    # Step 2: generate HTML
    try:
        html = await html_service.generate_html(
            subject=subject,
            body_text=body_text,
            prospect=prospect,
            campaign_style=body.campaign_style,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"HTML generation failed: {exc}",
        )

    return PreviewResponse(
        prospect_id=str(body.prospect_id),
        subject=subject,
        body_text=body_text,
        html=html,
        variables_used=personalized.get("variables_used", {}),
        generated_at=datetime.utcnow(),
    )


@router.post(
    "/full-pipeline",
    response_model=FullPipelineResponse,
    summary="Run the full AI campaign pipeline end-to-end",
)
async def full_pipeline(
    body: FullPipelineRequest,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Execute the entire AI campaign pipeline in one request:

    1. **Essence** -- extract campaign messaging framework
    2. **Research** -- research all provided prospects
    3. **Segment** -- create intelligent prospect segments
    4. **Pitch** -- generate a pitch per segment
    5. **Personalize + HTML** -- create final emails per prospect

    This is a long-running request; callers should use an appropriate timeout.
    """

    # --- 1. Essence -----------------------------------------------------------
    try:
        campaign_essence = await essence_service.extract_essence(
            user_input=body.description,
            target_audience=body.target_audience,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Essence extraction failed: {exc}",
        )

    # --- 2. Research ----------------------------------------------------------
    prospects = await _load_prospects_batch(session, body.prospect_ids)

    for p in prospects:
        p["id"] = p.get("id", "")
        if "job_title" in p and "title" not in p:
            p["title"] = p["job_title"]

    try:
        research_results = await research_service.research_batch(
            prospects=prospects,
            concurrency=body.research_concurrency,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Research failed: {exc}",
        )

    # Build a lookup: prospect_id -> research_data
    research_by_id: Dict[str, Dict] = {}
    for r in research_results:
        pid = r.get("prospect_id") or r.get("prospect_email", "")
        research_by_id[str(pid)] = r.get("research_data", {})

    # --- 3. Segment -----------------------------------------------------------
    try:
        segmentation = await segmentation_service.segment_prospects(
            research_data=research_results,
            campaign_goals=body.campaign_goals,
            campaign_essence=campaign_essence,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Segmentation failed: {exc}",
        )

    segments = segmentation.get("segments", [])
    if not segments:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Segmentation returned no segments",
        )

    # --- 4. Pitch (one per segment) -------------------------------------------
    pitches_by_segment: Dict[str, Dict] = {}
    for seg in segments:
        seg_id = seg.get("id", seg.get("name", "default"))
        try:
            pitch = await pitch_service.generate_pitch(
                segment=seg,
                campaign_essence=campaign_essence,
                sample_research=research_results[:3],
            )
            pitches_by_segment[seg_id] = pitch
        except Exception:
            # Use a fallback pitch so the pipeline doesn't abort entirely
            pitches_by_segment[seg_id] = {
                "pitch_angle": "Value-focused outreach",
                "key_messages": campaign_essence.get("value_propositions", ["Key benefit"]),
                "subject_lines": ["Quick question for {{companyName}}"],
                "body_template": "Hi {{firstName}},\n\n" + campaign_essence.get("call_to_action", "Would love to connect."),
                "follow_up_templates": [],
                "personalization_variables": ["firstName", "companyName"],
            }

    # --- 5. Personalize + HTML per prospect -----------------------------------
    # Simple segment assignment: use the first (highest-priority) segment for all
    # prospects. A production system would match each prospect to the best segment.
    default_segment = segments[0]
    default_seg_id = default_segment.get("id", default_segment.get("name", "default"))

    prospect_results: List[FullPipelineProspectResult] = []

    for prospect in prospects:
        pid = str(prospect.get("id", ""))
        seg_id = default_seg_id
        pitch = pitches_by_segment.get(seg_id, pitches_by_segment.get(list(pitches_by_segment.keys())[0]))

        research_data = research_by_id.get(pid, {})

        # Personalize
        try:
            personalized = pitch_service.personalize_for_prospect(
                pitch=pitch,
                prospect=prospect,
                research_data=research_data,
            )
        except Exception:
            personalized = {
                "subject": "Quick question",
                "body": f"Hi {prospect.get('first_name', 'there')},\n\n{campaign_essence.get('call_to_action', '')}",
                "follow_ups": [],
                "variables_used": {},
            }

        subject = personalized.get("subject", "")
        body_text = personalized.get("body", "")

        # HTML
        try:
            html = await html_service.generate_html(
                subject=subject,
                body_text=body_text,
                prospect=prospect,
                campaign_style=body.campaign_style,
            )
        except Exception:
            html = f"<html><body><p>{body_text}</p></body></html>"

        prospect_results.append(
            FullPipelineProspectResult(
                prospect_id=pid,
                segment=default_segment.get("name", "Default"),
                subject=subject,
                body_text=body_text,
                html=html,
                variables_used=personalized.get("variables_used", {}),
            )
        )

    return FullPipelineResponse(
        campaign_essence=campaign_essence,
        segments=segments,
        strategy=segmentation.get("strategy", ""),
        prospect_results=prospect_results,
        total_prospects=len(prospects),
        total_emails_generated=len(prospect_results),
        generated_at=datetime.utcnow(),
    )
