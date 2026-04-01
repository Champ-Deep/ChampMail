"""
Sequence API endpoints.
Multi-step email sequence management.

Sequences are stored in PostgreSQL via sequence_service.
ChampGraph is used as a secondary store for relationship intelligence.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_auth, TokenData
from app.db.postgres import get_db_session
from app.db.falkordb import graph_db
from app.schemas.sequence import (
    SequenceCreate,
    SequenceUpdate,
    SequenceResponse,
    SequenceListResponse,
    SequenceStatus,
    EnrollmentRequest,
    EnrollmentResponse,
)
from app.services.sequence_service import sequence_service

router = APIRouter(prefix="/sequences", tags=["Sequences"])


def _to_response(seq: dict) -> SequenceResponse:
    """Convert a sequence dict from service layer to API response."""
    return SequenceResponse(
        id=seq.get("id", 0),
        name=seq.get("name", ""),
        description=seq.get("description", ""),
        status=seq.get("status", "draft"),
        steps_count=len(seq.get("steps", [])),
        owner_id=str(seq.get("created_by") or seq.get("team_id") or ""),
        created_at=seq.get("created_at"),
        enrolled_count=seq.get("enrolled_count", 0),
        active_count=seq.get("active_count", 0),
        completed_count=seq.get("completed_count", 0),
        replied_count=seq.get("replied_count", 0),
    )


@router.get("", response_model=SequenceListResponse)
async def list_sequences(
    status: SequenceStatus | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """List all sequences with optional status filter."""
    sequences = await sequence_service.get_by_team(
        session, team_id=user.team_id or user.user_id, status=status.value if status else None
    )
    items = [_to_response(s) for s in sequences[skip:skip + limit]]
    return SequenceListResponse(items=items, total=len(sequences))


@router.post("", response_model=SequenceResponse, status_code=201)
async def create_sequence(
    sequence: SequenceCreate,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Create a new email sequence."""
    seq = await sequence_service.create(
        session,
        name=sequence.name,
        team_id=user.team_id or user.user_id,
        created_by=user.user_id,
        description=getattr(sequence, "description", None),
    )

    # Add steps if provided
    for i, step in enumerate(sequence.steps or []):
        await sequence_service.add_step(
            session,
            sequence_id=seq["id"],
            order=i + 1,
            name=step.get("name", f"Step {i+1}") if isinstance(step, dict) else f"Step {i+1}",
            subject_template=step.get("subject", "") if isinstance(step, dict) else getattr(step, "subject", ""),
            html_template=step.get("body", "") if isinstance(step, dict) else getattr(step, "body", ""),
            delay_hours=step.get("delay_hours", 24) if isinstance(step, dict) else getattr(step, "delay_hours", 24),
        )

    # Also ingest into ChampGraph for relationship intelligence
    await graph_db.create_sequence(
        name=sequence.name,
        owner_id=user.user_id,
        steps_count=len(sequence.steps) if sequence.steps else 0,
    )

    # Re-fetch to include steps
    seq = await sequence_service.get_by_id(session, seq["id"])
    return _to_response(seq)


@router.get("/{sequence_id}", response_model=SequenceResponse)
async def get_sequence(
    sequence_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Get sequence by ID with enrollment statistics."""
    seq = await sequence_service.get_by_id(session, sequence_id)
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")
    return _to_response(seq)


@router.put("/{sequence_id}", response_model=SequenceResponse)
async def update_sequence(
    sequence_id: str,
    update: SequenceUpdate,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Update sequence properties."""
    seq = await sequence_service.get_by_id(session, sequence_id)
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")

    # Apply updates via raw SQL update
    from sqlalchemy import update as sql_update
    from app.models import Sequence

    updates = {k: v.value if hasattr(v, 'value') else v
               for k, v in update.model_dump().items() if v is not None}

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    from datetime import datetime
    updates["updated_at"] = datetime.utcnow()

    await session.execute(
        sql_update(Sequence).where(Sequence.id == sequence_id).values(**updates)
    )
    await session.commit()

    seq = await sequence_service.get_by_id(session, sequence_id)
    return _to_response(seq)


@router.post("/{sequence_id}/enroll", response_model=EnrollmentResponse)
async def enroll_prospects(
    sequence_id: str,
    request: EnrollmentRequest,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Enroll prospects in a sequence by email."""
    seq = await sequence_service.get_by_id(session, sequence_id)
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")

    enrolled = 0
    already_enrolled = 0
    failed = 0
    errors = []

    for email in request.prospect_emails:
        try:
            # Look up prospect by email
            from sqlalchemy import select as sql_select
            from app.models import Prospect
            result = await session.execute(
                sql_select(Prospect).where(Prospect.email == email.lower())
            )
            prospect = result.scalar_one_or_none()

            if not prospect:
                failed += 1
                errors.append(f"{email}: Prospect not found")
                continue

            # Check if already enrolled
            from app.models import SequenceEnrollment
            existing = await session.execute(
                sql_select(SequenceEnrollment).where(
                    SequenceEnrollment.sequence_id == sequence_id,
                    SequenceEnrollment.prospect_id == str(prospect.id),
                    SequenceEnrollment.status.in_(["active", "paused"]),
                )
            )
            if existing.scalar_one_or_none():
                already_enrolled += 1
                continue

            await sequence_service.enroll_prospect(session, sequence_id, str(prospect.id))
            enrolled += 1

            # Also record in ChampGraph for relationship tracking
            await graph_db.enroll_prospect_in_sequence(email, int(sequence_id) if sequence_id.isdigit() else 0)

        except Exception as e:
            failed += 1
            errors.append(f"{email}: {str(e)}")

    return EnrollmentResponse(
        enrolled=enrolled,
        already_enrolled=already_enrolled,
        failed=failed,
        errors=errors[:10],
    )


@router.post("/{sequence_id}/pause")
async def pause_sequence(
    sequence_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Pause a sequence and all active enrollments."""
    seq = await sequence_service.get_by_id(session, sequence_id)
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")

    await sequence_service.pause(session, sequence_id)
    return {"status": "paused"}


@router.post("/{sequence_id}/resume")
async def resume_sequence(
    sequence_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Resume a paused sequence and its enrollments."""
    seq = await sequence_service.get_by_id(session, sequence_id)
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")

    await sequence_service.resume(session, sequence_id)
    return {"status": "active"}


@router.get("/{sequence_id}/analytics")
async def get_sequence_analytics(
    sequence_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Get detailed analytics for a sequence."""
    seq = await sequence_service.get_by_id(session, sequence_id)
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")

    # Get enrollment stats from PostgreSQL
    from sqlalchemy import select as sql_select, func
    from app.models import SequenceEnrollment, SequenceStepExecution

    enrollment_result = await session.execute(
        sql_select(
            SequenceEnrollment.status,
            func.count().label("count"),
        ).where(
            SequenceEnrollment.sequence_id == sequence_id
        ).group_by(SequenceEnrollment.status)
    )
    enrollment_stats = {row[0]: row[1] for row in enrollment_result.fetchall()}

    # Get email stats by step
    email_result = await session.execute(
        sql_select(
            SequenceStepExecution.step_id,
            func.count().label("sent"),
        ).join(
            SequenceEnrollment,
            SequenceStepExecution.enrollment_id == SequenceEnrollment.id,
        ).where(
            SequenceEnrollment.sequence_id == sequence_id,
            SequenceStepExecution.status == "sent",
        ).group_by(SequenceStepExecution.step_id)
    )
    email_stats = [{"step_id": str(row[0]), "sent": row[1]} for row in email_result.fetchall()]

    return {
        "sequence_id": sequence_id,
        "enrollment_stats": enrollment_stats,
        "email_stats": email_stats,
    }
