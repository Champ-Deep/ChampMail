"""
Prospect API endpoints.
CRUD operations for managing prospects in the knowledge graph.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Depends

from app.db.falkordb import graph_db
from app.schemas.prospect import (
    ProspectCreate,
    ProspectUpdate,
    ProspectResponse,
    ProspectListResponse,
    BulkProspectImport,
    BulkImportResponse,
)

router = APIRouter(prefix="/prospects", tags=["Prospects"])


def _parse_prospect_result(result: dict) -> ProspectResponse:
    """Parse graph query result into ProspectResponse."""
    prospect_data = result.get('p', {})

    # Handle both raw dict and parsed node format
    if isinstance(prospect_data, dict) and 'properties' in prospect_data:
        props = prospect_data['properties']
        prospect_id = prospect_data.get('id')
    else:
        props = prospect_data if isinstance(prospect_data, dict) else {}
        prospect_id = None

    company = None
    company_data = result.get('c')
    if company_data:
        if isinstance(company_data, dict) and 'properties' in company_data:
            company = company_data['properties']
        elif isinstance(company_data, dict):
            company = company_data

    works_at = None
    rel_data = result.get('r')
    if rel_data:
        if isinstance(rel_data, dict) and 'properties' in rel_data:
            works_at = rel_data['properties']
        elif isinstance(rel_data, dict):
            works_at = rel_data

    return ProspectResponse(
        id=prospect_id,
        email=props.get('email', ''),
        first_name=props.get('first_name', ''),
        last_name=props.get('last_name', ''),
        title=props.get('title', ''),
        phone=props.get('phone', ''),
        linkedin_url=props.get('linkedin_url', ''),
        created_at=props.get('created_at'),
        company=company,
        works_at=works_at,
    )


@router.get("", response_model=ProspectListResponse)
async def list_prospects(
    query: str = Query(default="", description="Search query"),
    industry: str = Query(default="", description="Filter by industry"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    List prospects with optional search and filtering.

    - **query**: Search in name and email
    - **industry**: Filter by company industry
    - **skip**: Pagination offset
    - **limit**: Max results (1-200)
    """
    results = graph_db.search_prospects(
        query_text=query,
        industry=industry,
        limit=limit,
        skip=skip,
    )

    items = [_parse_prospect_result(r) for r in results]

    return ProspectListResponse(
        items=items,
        total=len(items),  # TODO: Add count query for accurate total
        skip=skip,
        limit=limit,
    )


@router.post("", response_model=ProspectResponse, status_code=201)
async def create_prospect(prospect: ProspectCreate):
    """
    Create a new prospect.

    If company_domain is provided, also creates/links company.
    """
    # Check if prospect already exists
    existing = graph_db.get_prospect_by_email(prospect.email)
    if existing and existing.get('p'):
        raise HTTPException(
            status_code=409,
            detail=f"Prospect with email {prospect.email} already exists"
        )

    # Create prospect
    result = graph_db.create_prospect(
        email=prospect.email,
        first_name=prospect.first_name,
        last_name=prospect.last_name,
        title=prospect.title,
        phone=prospect.phone,
        linkedin_url=prospect.linkedin_url,
    )

    # Create company and link if provided
    if prospect.company_domain:
        graph_db.create_company(
            name=prospect.company_name or prospect.company_domain,
            domain=prospect.company_domain,
            industry=prospect.industry or "",
        )
        graph_db.link_prospect_to_company(
            prospect_email=prospect.email,
            company_domain=prospect.company_domain,
            title=prospect.title,
        )

    # Fetch full prospect with relationships
    full_result = graph_db.get_prospect_by_email(prospect.email)
    return _parse_prospect_result(full_result or result)


@router.get("/{email}", response_model=ProspectResponse)
async def get_prospect(email: str):
    """
    Get prospect by email address.

    Returns prospect with company relationship if exists.
    """
    result = graph_db.get_prospect_by_email(email)
    if not result or not result.get('p'):
        raise HTTPException(status_code=404, detail="Prospect not found")

    return _parse_prospect_result(result)


@router.put("/{email}", response_model=ProspectResponse)
async def update_prospect(email: str, update: ProspectUpdate):
    """
    Update prospect fields.

    Only provided fields are updated.
    """
    # Check prospect exists
    existing = graph_db.get_prospect_by_email(email)
    if not existing or not existing.get('p'):
        raise HTTPException(status_code=404, detail="Prospect not found")

    # Build update query
    updates = {k: v for k, v in update.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clause = ', '.join(f'p.{k} = ${k}' for k in updates.keys())
    query = f"""
        MATCH (p:Prospect {{email: $email}})
        SET {set_clause}
        RETURN p
    """
    updates['email'] = email.lower()
    graph_db.query(query, updates)

    # Return updated prospect
    result = graph_db.get_prospect_by_email(email)
    return _parse_prospect_result(result)


@router.delete("/{email}", status_code=204)
async def delete_prospect(email: str):
    """
    Delete prospect (soft delete - marks as inactive).

    Note: Does not actually remove from graph to preserve history.
    """
    existing = graph_db.get_prospect_by_email(email)
    if not existing or not existing.get('p'):
        raise HTTPException(status_code=404, detail="Prospect not found")

    # Soft delete - set status to deleted
    query = """
        MATCH (p:Prospect {email: $email})
        SET p.status = 'deleted', p.deleted_at = datetime()
        RETURN p
    """
    graph_db.query(query, {'email': email.lower()})


@router.post("/{email}/enrich", response_model=ProspectResponse)
async def enrich_prospect(email: str):
    """
    Trigger enrichment for a prospect.

    Calls external enrichment service (Lake B2B, Apollo, etc.)
    and updates prospect data.

    TODO: Implement actual enrichment logic
    """
    existing = graph_db.get_prospect_by_email(email)
    if not existing or not existing.get('p'):
        raise HTTPException(status_code=404, detail="Prospect not found")

    # TODO: Call enrichment service
    # For now, just return existing data
    return _parse_prospect_result(existing)


@router.get("/{email}/timeline")
async def get_prospect_timeline(email: str):
    """
    Get activity timeline for a prospect.

    Returns all interactions: emails sent, opens, clicks, replies.
    """
    existing = graph_db.get_prospect_by_email(email)
    if not existing or not existing.get('p'):
        raise HTTPException(status_code=404, detail="Prospect not found")

    # Query all email interactions
    query = """
        MATCH (p:Prospect {email: $email})-[:RECEIVED]->(e:Email)
        RETURN e
        ORDER BY e.sent_at DESC
        LIMIT 50
    """
    emails = graph_db.query(query, {'email': email.lower()})

    return {
        "prospect_email": email,
        "events": emails,
    }


@router.post("/bulk", response_model=BulkImportResponse)
async def bulk_import_prospects(data: BulkProspectImport):
    """
    Bulk import prospects.

    Creates prospects and optionally links to companies.
    Returns count of created, updated, and failed records.
    """
    created = 0
    updated = 0
    failed = 0
    errors = []

    for prospect in data.prospects:
        try:
            existing = graph_db.get_prospect_by_email(prospect.email)

            if existing and existing.get('p'):
                # Update existing
                updates = prospect.model_dump(exclude={'email', 'company_name', 'company_domain', 'industry'})
                updates = {k: v for k, v in updates.items() if v}
                if updates:
                    set_clause = ', '.join(f'p.{k} = ${k}' for k in updates.keys())
                    query = f"MATCH (p:Prospect {{email: $email}}) SET {set_clause}"
                    updates['email'] = prospect.email.lower()
                    graph_db.query(query, updates)
                updated += 1
            else:
                # Create new
                graph_db.create_prospect(
                    email=prospect.email,
                    first_name=prospect.first_name,
                    last_name=prospect.last_name,
                    title=prospect.title,
                    phone=prospect.phone,
                    linkedin_url=prospect.linkedin_url,
                )

                # Create company link if provided
                if prospect.company_domain:
                    graph_db.create_company(
                        name=prospect.company_name or prospect.company_domain,
                        domain=prospect.company_domain,
                        industry=prospect.industry or "",
                    )
                    graph_db.link_prospect_to_company(
                        prospect_email=prospect.email,
                        company_domain=prospect.company_domain,
                        title=prospect.title,
                    )
                created += 1

        except Exception as e:
            failed += 1
            errors.append(f"{prospect.email}: {str(e)}")

    return BulkImportResponse(
        created=created,
        updated=updated,
        failed=failed,
        errors=errors[:10],  # Limit errors in response
    )
