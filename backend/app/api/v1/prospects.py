"""
Prospect API endpoints.
CRUD operations for managing prospects via ChampGraph + PostgreSQL.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Depends

from app.db.falkordb import graph_db
from app.db.postgres import get_db_session
from app.core.security import require_auth, TokenData
from app.core.admin_security import require_admin
from app.schemas.prospect import (
    ProspectCreate,
    ProspectUpdate,
    ProspectResponse,
    ProspectListResponse,
    BulkProspectImport,
    BulkImportResponse,
)
from app.services.prospect_service import prospect_service
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/prospects", tags=["Prospects"])


def _parse_prospect_result(result: dict) -> ProspectResponse:
    """Parse graph query result into ProspectResponse."""
    prospect_data = result.get('p', {})

    if isinstance(prospect_data, dict) and 'properties' in prospect_data:
        props = prospect_data['properties']
        prospect_id = prospect_data.get('id')
    else:
        props = prospect_data if isinstance(prospect_data, dict) else {}
        prospect_id = props.get('id') or props.get('name')

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
    query: str = Query(default="", max_length=200, description="Search query"),
    industry: str = Query(default="", max_length=100, description="Filter by industry"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    List prospects.

    - Admins see all prospects (via ChampGraph search).
    - Regular users only see prospects assigned to them (via PostgreSQL).
    """
    if user.role != "user":
        # Admin / team_admin / data_team: full graph search
        results = await graph_db.search_prospects(
            query_text=query,
            industry=industry,
            limit=limit,
            skip=skip,
        )
        items = []
        for r in results:
            try:
                parsed = _parse_prospect_result(r)
                if parsed.email:  # Only include results with valid email
                    items.append(parsed)
            except Exception:
                pass
    else:
        # Regular user: only assigned prospects from PostgreSQL
        pg_prospects = await prospect_service.get_assigned_to_user(
            session, user.user_id, limit=limit, offset=skip
        )
        items = [
            ProspectResponse(
                id=p["id"],
                email=p["email"],
                first_name=p.get("first_name", ""),
                last_name=p.get("last_name", ""),
                title=p.get("job_title", ""),
                phone="",
                linkedin_url=p.get("linkedin_url", ""),
                created_at=p.get("created_at"),
            )
            for p in pg_prospects
        ]

    return ProspectListResponse(
        items=items,
        total=len(items),
        skip=skip,
        limit=limit,
    )


@router.post("", response_model=ProspectResponse, status_code=201)
async def create_prospect(prospect: ProspectCreate, user: TokenData = Depends(require_admin)):
    """Create a new prospect."""
    existing = await graph_db.get_prospect_by_email(prospect.email)
    if existing and existing.get('p'):
        raise HTTPException(
            status_code=409,
            detail=f"Prospect with email {prospect.email} already exists"
        )

    result = await graph_db.create_prospect(
        email=prospect.email,
        first_name=prospect.first_name,
        last_name=prospect.last_name,
        title=prospect.title,
        phone=prospect.phone,
        linkedin_url=prospect.linkedin_url,
    )

    if prospect.company_domain:
        await graph_db.create_company(
            name=prospect.company_name or prospect.company_domain,
            domain=prospect.company_domain,
            industry=prospect.industry or "",
        )
        await graph_db.link_prospect_to_company(
            prospect_email=prospect.email,
            company_domain=prospect.company_domain,
            title=prospect.title,
        )

    full_result = await graph_db.get_prospect_by_email(prospect.email)
    return _parse_prospect_result(full_result or result)


@router.get("/{email}", response_model=ProspectResponse)
async def get_prospect(email: str, user: TokenData = Depends(require_auth)):
    """Get prospect by email address."""
    result = await graph_db.get_prospect_by_email(email)
    if not result or not result.get('p'):
        raise HTTPException(status_code=404, detail="Prospect not found")
    return _parse_prospect_result(result)


@router.put("/{email}", response_model=ProspectResponse)
async def update_prospect(email: str, update: ProspectUpdate, user: TokenData = Depends(require_auth)):
    """Update prospect fields."""
    existing = await graph_db.get_prospect_by_email(email)
    if not existing or not existing.get('p'):
        raise HTTPException(status_code=404, detail="Prospect not found")

    updates = {k: v for k, v in update.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Re-ingest with updated data to update the graph
    await graph_db.create_prospect(email=email, **updates)

    result = await graph_db.get_prospect_by_email(email)
    return _parse_prospect_result(result)


@router.delete("/{email}", status_code=204)
async def delete_prospect(email: str, user: TokenData = Depends(require_auth)):
    """Delete prospect (soft delete via re-ingest with deleted status)."""
    existing = await graph_db.get_prospect_by_email(email)
    if not existing or not existing.get('p'):
        raise HTTPException(status_code=404, detail="Prospect not found")

    await graph_db._ingest(
        content=f"Prospect {email} marked as deleted",
        name=f"Prospect Deleted: {email}",
        account_name=email.split("@")[1] if "@" in email else "champmail",
        source="prospect_deletion",
    )


@router.post("/{email}/enrich", response_model=ProspectResponse)
async def enrich_prospect(email: str, user: TokenData = Depends(require_auth)):
    """Trigger enrichment for a prospect (TODO: implement enrichment logic)."""
    existing = await graph_db.get_prospect_by_email(email)
    if not existing or not existing.get('p'):
        raise HTTPException(status_code=404, detail="Prospect not found")
    return _parse_prospect_result(existing)


@router.get("/{email}/timeline")
async def get_prospect_timeline(email: str, user: TokenData = Depends(require_auth)):
    """Get activity timeline for a prospect via ChampGraph."""
    existing = await graph_db.get_prospect_by_email(email)
    if not existing or not existing.get('p'):
        raise HTTPException(status_code=404, detail="Prospect not found")

    account = email.split("@")[1] if "@" in email else "champmail"
    context = await graph_db.get_email_context(
        account_name=account,
        contact_email=email,
    )

    return {
        "prospect_email": email,
        "email_history": context.get("email_history", []),
        "all_interactions": context.get("all_interactions", []),
        "topics_discussed": context.get("topics_discussed", []),
    }


@router.post("/bulk", response_model=BulkImportResponse)
async def bulk_import_prospects(
    data: BulkProspectImport,
    user: TokenData = Depends(require_auth)
):
    """Bulk import prospects into ChampGraph."""
    created = 0
    updated = 0
    failed = 0
    errors = []

    for prospect in data.prospects:
        try:
            existing = await graph_db.get_prospect_by_email(prospect.email)

            if existing and existing.get('p'):
                updates = prospect.model_dump(exclude={'email', 'company_name', 'company_domain', 'industry'})
                updates = {k: v for k, v in updates.items() if v}
                if updates:
                    await graph_db.create_prospect(email=prospect.email, **updates)
                updated += 1
            else:
                await graph_db.create_prospect(
                    email=prospect.email,
                    first_name=prospect.first_name,
                    last_name=prospect.last_name,
                    title=prospect.title,
                    phone=prospect.phone,
                    linkedin_url=prospect.linkedin_url,
                )

                if prospect.company_domain:
                    await graph_db.create_company(
                        name=prospect.company_name or prospect.company_domain,
                        domain=prospect.company_domain,
                        industry=prospect.industry or "",
                    )
                    await graph_db.link_prospect_to_company(
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
        errors=errors[:10],
    )
