"""
Admin Prospect Management endpoints.

Only admins may access these routes.

Endpoints:
  POST   /admin/prospects                          Create prospect + trigger research
  GET    /admin/prospects                          List all prospects with assignment info
  POST   /admin/prospects/{prospect_id}/assign     Assign prospect to a user
  GET    /admin/prospects/{prospect_id}/logs       Sequence step logs for a prospect
  POST   /admin/prospects/{prospect_id}/enroll     Enroll in 3-Point Follow-up sequence
  GET    /admin/users                              List all users (for assignment UI)
  POST   /admin/users                             Create a new user account
"""

from __future__ import annotations

import logging
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_security import require_admin
from app.core.security import TokenData
from app.db.champgraph import graph_db
from app.db.postgres import get_db_session
from app.services.prospect_service import prospect_service
from app.services.sequence_service import sequence_service
from app.services.user_service import user_service
from app.services.three_point_followup import (
    get_or_create_three_point_sequence,
    enroll_prospect,
    three_point_executor,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Admin - Prospects"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AdminCreateProspectRequest(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    industry: Optional[str] = None
    job_title: Optional[str] = None
    linkedin_url: Optional[str] = None


class AssignProspectRequest(BaseModel):
    user_id: str
    campaign_id: Optional[str] = None


class EnrollRequest(BaseModel):
    """Enroll a prospect in the 3-Point Follow-up sequence."""
    campaign_id: Optional[str] = None
    sender_user_id: Optional[str] = None  # whose SMTP to use for sending


class AdminCreateUserRequest(BaseModel):
    email: EmailStr
    password: str
    name: str = ""
    role: str = "user"
    team_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Background: research a prospect after creation
# ---------------------------------------------------------------------------

async def _run_research(prospect_id: str, prospect_email: str) -> None:
    """
    Background task: query ChampGraph for context on the new prospect and
    save the results to prospects.research_data.
    """
    from app.db.postgres import async_session_maker as AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            await prospect_service.save_research_data(
                session, prospect_id, data={}, status="running"
            )

            # Pull existing graph context (emails, interactions, relationships)
            context = await graph_db.get_email_context(
                account_name=prospect_email.split("@")[1] if "@" in prospect_email else "champmail",
                contact_email=prospect_email,
            )

            research_result = {
                "email_history": context.get("email_history", []),
                "all_interactions": context.get("all_interactions", []),
                "topics_discussed": context.get("topics_discussed", []),
                "source": "champgraph",
            }

            await prospect_service.save_research_data(
                session, prospect_id, data=research_result, status="completed"
            )
            logger.info("Research completed for prospect %s", prospect_id)

        except Exception as exc:
            logger.error("Research failed for prospect %s: %s", prospect_id, exc)
            try:
                await prospect_service.save_research_data(
                    session, prospect_id, data={"error": str(exc)}, status="failed"
                )
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Prospect endpoints
# ---------------------------------------------------------------------------

@router.post("/prospects", status_code=201)
async def admin_create_prospect(
    request: AdminCreateProspectRequest,
    background_tasks: BackgroundTasks,
    admin: TokenData = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Create a prospect (admin only).

    1. Saves to PostgreSQL via prospect_service.
    2. Saves to ChampGraph for relationship intelligence.
    3. Triggers background research via ChampGraph context.
    """
    # Check duplicate in PostgreSQL
    existing_pg = await prospect_service.get_by_email(session, request.email)
    if existing_pg:
        raise HTTPException(status_code=409, detail=f"Prospect {request.email} already exists")

    # Check duplicate in graph
    existing_graph = await graph_db.get_prospect_by_email(request.email)
    if existing_graph and existing_graph.get("p"):
        raise HTTPException(status_code=409, detail=f"Prospect {request.email} already exists in graph")

    # Determine team_id (use admin's team or None)
    team_id = admin.team_id

    # Create in PostgreSQL
    pg_prospect = await prospect_service.create(
        session=session,
        email=request.email,
        team_id=team_id or str(uuid4()),  # fallback so NOT NULL is satisfied
        first_name=request.first_name,
        last_name=request.last_name,
        company_name=request.company_name,
        job_title=request.job_title,
        industry=request.industry,
        linkedin_url=request.linkedin_url,
        created_by=admin.user_id,
        research_status="pending",
    )

    # Create in ChampGraph
    await graph_db.create_prospect(
        email=request.email,
        first_name=request.first_name or "",
        last_name=request.last_name or "",
        title=request.job_title or "",
        linkedin_url=request.linkedin_url or "",
    )
    if request.company_domain:
        await graph_db.create_company(
            name=request.company_name or request.company_domain,
            domain=request.company_domain,
            industry=request.industry or "",
        )
        await graph_db.link_prospect_to_company(
            prospect_email=request.email,
            company_domain=request.company_domain,
            title=request.job_title or "",
        )

    # Trigger research in background
    background_tasks.add_task(_run_research, pg_prospect["id"], request.email)

    return {
        "prospect": pg_prospect,
        "message": "Prospect created. Research running in background.",
    }


@router.get("/prospects")
async def admin_list_prospects(
    limit: int = 100,
    offset: int = 0,
    admin: TokenData = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    """List all prospects with assignment info (admin only)."""
    team_id = admin.team_id
    if team_id:
        prospects = await prospect_service.get_by_team(
            session, team_id, limit=limit, offset=offset
        )
    else:
        # No team — return empty list; admins should be in a team
        prospects = []

    return {"prospects": prospects, "total": len(prospects)}


@router.post("/prospects/{prospect_id}/assign")
async def admin_assign_prospect(
    prospect_id: str,
    request: AssignProspectRequest,
    admin: TokenData = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Assign a prospect to a user (admin only).

    The assigned user will see this prospect in their list.
    If campaign_id is provided, also creates a CampaignProspect enrollment
    so the prospect's email is pre-fed into that campaign.
    """
    # Verify the target user exists
    target_user = await user_service.get_by_id(session, request.user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")

    updated = await prospect_service.assign_to_user(session, prospect_id, request.user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Prospect not found")

    # Optionally enroll in campaign
    if request.campaign_id:
        from app.models.campaign import CampaignProspect
        cp = CampaignProspect(
            id=uuid4(),
            campaign_id=request.campaign_id,
            prospect_id=prospect_id,
            status="enrolled",
        )
        session.add(cp)
        await session.commit()

    return {
        "prospect_id": prospect_id,
        "assigned_to_user_id": request.user_id,
        "campaign_id": request.campaign_id,
        "message": "Prospect assigned successfully",
    }


@router.get("/prospects/{prospect_id}/logs")
async def admin_get_prospect_logs(
    prospect_id: str,
    limit: int = 50,
    admin: TokenData = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Return all sequence step logs for a prospect (admin only).

    These logs are used as context for future AI email generation.
    """
    logs = await sequence_service.get_logs_for_prospect(session, prospect_id, limit=limit)
    return {"prospect_id": prospect_id, "logs": logs, "total": len(logs)}


@router.post("/prospects/{prospect_id}/enroll")
async def admin_enroll_prospect(
    prospect_id: str,
    request: EnrollRequest,
    background_tasks: BackgroundTasks,
    admin: TokenData = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Enroll a prospect in the 3-Point Follow-up sequence (admin only).

    Immediately fires Step 1 (initial outreach) in a background task.
    Steps 2 and 3 are scheduled by the background worker based on next_step_at.
    """
    prospect = await prospect_service.get_by_id(session, prospect_id)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")

    team_id = admin.team_id or prospect.get("team_id") or str(uuid4())
    sequence_id = await get_or_create_three_point_sequence(
        session, team_id=team_id, created_by=admin.user_id
    )

    enrollment_id = await enroll_prospect(
        session,
        sequence_id=sequence_id,
        prospect_id=prospect_id,
        campaign_id=request.campaign_id,
    )

    # Fire step 1 immediately in background
    background_tasks.add_task(
        _execute_step_bg,
        enrollment_id=enrollment_id,
        step_order=1,
        sender_user_id=request.sender_user_id or admin.user_id,
    )

    return {
        "enrollment_id": enrollment_id,
        "sequence_id": sequence_id,
        "message": "Prospect enrolled. Step 1 (initial email) firing now.",
    }


async def _execute_step_bg(enrollment_id: str, step_order: int, sender_user_id: str) -> None:
    """Background wrapper for three_point_executor.execute_step."""
    from app.db.postgres import async_session_maker as AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            result = await three_point_executor.execute_step(
                session=session,
                enrollment_id=enrollment_id,
                step_order=step_order,
                sender_user_id=sender_user_id,
            )
            logger.info("Step %d result for enrollment %s: %s", step_order, enrollment_id, result)
        except Exception as exc:
            logger.error(
                "Failed executing step %d for enrollment %s: %s",
                step_order, enrollment_id, exc,
            )


# ---------------------------------------------------------------------------
# User management endpoints (admin panel)
# ---------------------------------------------------------------------------

@router.get("/users")
async def admin_list_users(
    team_id: Optional[str] = None,
    role: Optional[str] = None,
    admin: TokenData = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    """List all users (admin only). Used for assignment dropdown."""
    users = await user_service.list_users(session, team_id=team_id, role=role)
    return {
        "users": [
            {
                "user_id": str(u.id),
                "email": u.email,
                "full_name": u.full_name,
                "role": u.role,
                "team_id": str(u.team_id) if u.team_id else None,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ]
    }


@router.post("/users", status_code=201)
async def admin_create_user(
    request: AdminCreateUserRequest,
    admin: TokenData = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    """Create a new user account (admin only)."""
    if await user_service.email_exists(session, request.email):
        raise HTTPException(status_code=409, detail="User already exists")

    user = await user_service.create(
        session,
        email=request.email,
        password=request.password,
        full_name=request.name,
        role=request.role,
        team_id=request.team_id,
    )
    await session.commit()

    return {
        "user_id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "team_id": str(user.team_id) if user.team_id else None,
        "message": "User created successfully",
    }
