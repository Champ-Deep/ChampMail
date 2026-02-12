"""
Sequence API endpoints.
Multi-step email sequence management.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

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

router = APIRouter(prefix="/sequences", tags=["Sequences"])


def _parse_sequence_result(result: dict) -> SequenceResponse:
    """Parse graph query result into SequenceResponse."""
    seq_data = result.get('s', {})

    if isinstance(seq_data, dict) and 'properties' in seq_data:
        props = seq_data['properties']
        seq_id = seq_data.get('id', 0)
    else:
        props = seq_data if isinstance(seq_data, dict) else {}
        seq_id = 0

    return SequenceResponse(
        id=seq_id,
        name=props.get('name', ''),
        description=props.get('description', ''),
        status=props.get('status', SequenceStatus.DRAFT),
        steps_count=props.get('steps_count', 0),
        owner_id=props.get('owner_id', ''),
        created_at=props.get('created_at'),
        enrolled_count=result.get('enrolled_count', 0),
        active_count=result.get('active_count', 0),
        completed_count=result.get('completed_count', 0),
        replied_count=result.get('replied_count', 0),
    )


@router.get("", response_model=SequenceListResponse)
async def list_sequences(
    status: SequenceStatus | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
):
    """
    List all sequences with optional status filter.
    """
    conditions = []
    params = {'skip': skip, 'limit': limit}

    if status:
        conditions.append("s.status = $status")
        params['status'] = status.value

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    query = f"""
        MATCH (s:Sequence)
        {where_clause}
        OPTIONAL MATCH (p:Prospect)-[e:ENROLLED_IN]->(s)
        WITH s, count(e) as enrolled_count
        RETURN s, enrolled_count
        ORDER BY s.created_at DESC
        SKIP $skip
        LIMIT $limit
    """

    results = graph_db.query(query, params)
    items = [_parse_sequence_result(r) for r in results]

    return SequenceListResponse(
        items=items,
        total=len(items),
    )


@router.post("", response_model=SequenceResponse, status_code=201)
async def create_sequence(sequence: SequenceCreate):
    """
    Create a new email sequence.

    Sequence starts in 'draft' status.
    """
    # TODO: Get actual owner from auth
    owner_id = "default_user"

    result = graph_db.create_sequence(
        name=sequence.name,
        owner_id=owner_id,
        steps_count=len(sequence.steps),
    )

    # Create sequence steps as separate nodes (if provided)
    if sequence.steps:
        seq_data = result.get('s', {})
        if isinstance(seq_data, dict) and 'properties' in seq_data:
            # seq_id = seq_data.get('id')
            pass
        # TODO: Create SequenceStep nodes and link to Sequence

    # Fetch created sequence
    query = """
        MATCH (s:Sequence {name: $name, owner_id: $owner_id})
        RETURN s
        ORDER BY s.created_at DESC
        LIMIT 1
    """
    created = graph_db.query(query, {
        'name': sequence.name,
        'owner_id': owner_id,
    })

    if created:
        return _parse_sequence_result(created[0])

    return _parse_sequence_result(result)


@router.get("/{sequence_id}", response_model=SequenceResponse)
async def get_sequence(sequence_id: int):
    """
    Get sequence by ID with enrollment statistics.
    """
    query = """
        MATCH (s:Sequence)
        WHERE id(s) = $id
        OPTIONAL MATCH (p:Prospect)-[e:ENROLLED_IN]->(s)
        WITH s,
             count(e) as enrolled_count,
             sum(CASE WHEN e.status = 'active' THEN 1 ELSE 0 END) as active_count,
             sum(CASE WHEN e.status = 'completed' THEN 1 ELSE 0 END) as completed_count,
             sum(CASE WHEN e.status = 'replied' THEN 1 ELSE 0 END) as replied_count
        RETURN s, enrolled_count, active_count, completed_count, replied_count
    """
    results = graph_db.query(query, {'id': sequence_id})

    if not results:
        raise HTTPException(status_code=404, detail="Sequence not found")

    return _parse_sequence_result(results[0])


@router.put("/{sequence_id}", response_model=SequenceResponse)
async def update_sequence(sequence_id: int, update: SequenceUpdate):
    """
    Update sequence properties.
    """
    # Check exists
    existing_query = "MATCH (s:Sequence) WHERE id(s) = $id RETURN s"
    existing = graph_db.query(existing_query, {'id': sequence_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Sequence not found")

    # Build update
    updates = {k: v.value if hasattr(v, 'value') else v
               for k, v in update.model_dump().items() if v is not None}

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clause = ', '.join(f's.{k} = ${k}' for k in updates.keys())
    query = f"""
        MATCH (s:Sequence)
        WHERE id(s) = $id
        SET {set_clause}
        RETURN s
    """
    updates['id'] = sequence_id
    result = graph_db.query(query, updates)

    return _parse_sequence_result(result[0]) if result else None


@router.post("/{sequence_id}/enroll", response_model=EnrollmentResponse)
async def enroll_prospects(sequence_id: int, request: EnrollmentRequest):
    """
    Enroll prospects in a sequence.

    - Prospects must exist
    - Cannot enroll if already enrolled and active
    """
    # Verify sequence exists
    seq_query = "MATCH (s:Sequence) WHERE id(s) = $id RETURN s"
    seq = graph_db.query(seq_query, {'id': sequence_id})
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")

    enrolled = 0
    already_enrolled = 0
    failed = 0
    errors = []

    for email in request.prospect_emails:
        try:
            # Check if prospect exists
            prospect = graph_db.get_prospect_by_email(email)
            if not prospect or not prospect.get('p'):
                failed += 1
                errors.append(f"{email}: Prospect not found")
                continue

            # Check if already enrolled
            check_query = """
                MATCH (p:Prospect {email: $email})-[e:ENROLLED_IN]->(s:Sequence)
                WHERE id(s) = $sequence_id AND e.status IN ['active', 'paused']
                RETURN e
            """
            existing = graph_db.query(check_query, {
                'email': email.lower(),
                'sequence_id': sequence_id,
            })

            if existing:
                already_enrolled += 1
                continue

            # Enroll
            graph_db.enroll_prospect_in_sequence(email, sequence_id)
            enrolled += 1

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
async def pause_sequence(sequence_id: int):
    """
    Pause a sequence and all active enrollments.
    """
    query = """
        MATCH (s:Sequence)
        WHERE id(s) = $id
        SET s.status = 'paused'
        WITH s
        MATCH (p:Prospect)-[e:ENROLLED_IN]->(s)
        WHERE e.status = 'active'
        SET e.status = 'paused', e.paused_at = datetime()
        RETURN s, count(e) as paused_count
    """
    result = graph_db.query(query, {'id': sequence_id})

    if not result:
        raise HTTPException(status_code=404, detail="Sequence not found")

    return {"status": "paused", "enrollments_paused": result[0].get('paused_count', 0)}


@router.post("/{sequence_id}/resume")
async def resume_sequence(sequence_id: int):
    """
    Resume a paused sequence and its enrollments.
    """
    query = """
        MATCH (s:Sequence)
        WHERE id(s) = $id
        SET s.status = 'active'
        WITH s
        MATCH (p:Prospect)-[e:ENROLLED_IN]->(s)
        WHERE e.status = 'paused'
        SET e.status = 'active', e.paused_at = null
        RETURN s, count(e) as resumed_count
    """
    result = graph_db.query(query, {'id': sequence_id})

    if not result:
        raise HTTPException(status_code=404, detail="Sequence not found")

    return {"status": "active", "enrollments_resumed": result[0].get('resumed_count', 0)}


@router.get("/{sequence_id}/analytics")
async def get_sequence_analytics(sequence_id: int):
    """
    Get detailed analytics for a sequence.

    Returns:
    - Enrollment funnel
    - Email performance (opens, clicks, replies)
    - Step-by-step breakdown
    """
    # Verify exists
    seq_query = "MATCH (s:Sequence) WHERE id(s) = $id RETURN s"
    seq = graph_db.query(seq_query, {'id': sequence_id})
    if not seq:
        raise HTTPException(status_code=404, detail="Sequence not found")

    # Get enrollment stats
    enrollment_query = """
        MATCH (p:Prospect)-[e:ENROLLED_IN]->(s:Sequence)
        WHERE id(s) = $id
        RETURN
            e.status as status,
            count(*) as count
    """
    enrollment_stats = graph_db.query(enrollment_query, {'id': sequence_id})

    # Get email stats
    email_query = """
        MATCH (p:Prospect)-[:RECEIVED]->(e:Email)
        WHERE e.sequence_id = $id
        RETURN
            e.step_number as step,
            count(*) as sent,
            sum(CASE WHEN e.opened_at IS NOT NULL THEN 1 ELSE 0 END) as opened,
            sum(CASE WHEN e.clicked_at IS NOT NULL THEN 1 ELSE 0 END) as clicked,
            sum(CASE WHEN e.replied_at IS NOT NULL THEN 1 ELSE 0 END) as replied
    """
    email_stats = graph_db.query(email_query, {'id': sequence_id})

    return {
        "sequence_id": sequence_id,
        "enrollment_stats": {
            stat.get('status', 'unknown'): stat.get('count', 0)
            for stat in enrollment_stats
        },
        "email_stats": email_stats,
    }
