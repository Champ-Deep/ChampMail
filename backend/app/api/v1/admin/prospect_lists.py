"""
Prospect list management endpoints.
Upload, validate, process, and manage CSV prospect lists.
"""

from __future__ import annotations

import os
import json
import aiofiles
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import TokenData, require_auth
from app.core.admin_security import require_data_team_or_admin, require_admin
from app.db.postgres import get_db_session
from app.utils.csv_parser import ProspectCSVParser, CSVValidationError
from app.services.audit_service import AuditService

router = APIRouter(prefix="/prospect-lists", tags=["Admin - Prospect Lists"])

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

UPLOAD_DIR = os.environ.get("PROSPECT_UPLOAD_DIR", os.path.join(os.getcwd(), "uploads", "prospect_lists"))


def _ensure_upload_dir() -> str:
    """Ensure the upload directory exists and return its path."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    return UPLOAD_DIR


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class ProspectListUploadResponse(BaseModel):
    """Response returned after a successful CSV upload."""
    id: UUID
    filename: str
    original_filename: str
    file_size: int
    file_hash: str
    status: str  # uploaded, validating, validated, processing, processed, error
    total_rows: int
    valid_prospects: int
    errors: List[str]
    warnings: List[str]
    headers_found: List[str]
    uploaded_at: datetime
    uploaded_by: str


class ProspectListSummary(BaseModel):
    """Lightweight representation used in list endpoints."""
    id: UUID
    name: str
    filename: str
    status: str
    total_rows: int
    valid_prospects: int
    processed_prospects: int
    created_at: datetime
    created_by: str


class ProspectListDetail(BaseModel):
    """Full detail for a single prospect list."""
    id: UUID
    name: str
    filename: str
    original_filename: str
    file_size: int
    file_hash: str
    status: str
    total_rows: int
    valid_prospects: int
    processed_prospects: int
    errors: List[str]
    warnings: List[str]
    headers_found: List[str]
    created_at: datetime
    created_by: str
    team_id: Optional[str]
    processed_at: Optional[datetime]


class ProspectListListResponse(BaseModel):
    """Paginated response for listing prospect lists."""
    items: List[ProspectListSummary]
    total: int
    skip: int
    limit: int


class ProcessListRequest(BaseModel):
    """Optional parameters when processing an uploaded list."""
    deduplicate: bool = Field(default=True, description="Remove duplicate emails within the file")
    skip_existing: bool = Field(default=True, description="Skip prospects whose email already exists in the database")
    tag: Optional[str] = Field(default=None, description="Optional tag to apply to all imported prospects")


class ProcessListResponse(BaseModel):
    """Response after processing a prospect list into the database."""
    list_id: UUID
    status: str
    total_in_file: int
    created: int
    skipped_duplicate: int
    skipped_existing: int
    failed: int
    errors: List[str]
    processed_at: datetime


class DeleteListResponse(BaseModel):
    """Confirmation of list deletion."""
    id: UUID
    deleted: bool
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_list_row(session: AsyncSession, list_id: UUID) -> Optional[Dict[str, Any]]:
    """Fetch a prospect_list row by id, returning None if not found."""
    result = await session.execute(
        text("SELECT * FROM prospect_lists WHERE id = :id"),
        {"id": str(list_id)},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def _get_user_team_id(session: AsyncSession, user_id: str) -> Optional[str]:
    """Look up the team_id for a user."""
    result = await session.execute(
        text("SELECT team_id FROM users WHERE id = :uid"),
        {"uid": user_id},
    )
    row = result.scalar_one_or_none()
    return str(row) if row else None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/upload",
    response_model=ProspectListUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a prospect CSV file",
)
async def upload_prospect_list(
    file: UploadFile = File(..., description="CSV file containing prospect data"),
    request: Request = None,
    user: TokenData = Depends(require_data_team_or_admin),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Upload a CSV file of prospects.

    The file is validated for structure (headers, email format, duplicates)
    but prospects are **not** inserted into the database until the
    `/process` endpoint is called.

    Requires **data_team** or **admin** role.
    """
    # --- Validate & parse CSV -------------------------------------------------
    parser = ProspectCSVParser()
    try:
        prospects, report = await parser.parse_and_validate(file, validate_only=False)
    except CSVValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"CSV validation failed: {exc}",
        )

    # --- Persist the raw file to disk -----------------------------------------
    await file.seek(0)
    raw_bytes = await file.read()
    file_hash = ProspectCSVParser.compute_file_hash(raw_bytes)

    list_id = uuid4()
    safe_filename = f"{list_id}.csv"
    upload_dir = _ensure_upload_dir()
    filepath = os.path.join(upload_dir, safe_filename)

    async with aiofiles.open(filepath, "wb") as out:
        await out.write(raw_bytes)

    # --- Store metadata in Postgres -------------------------------------------
    team_id = await _get_user_team_id(session, user.user_id)
    now = datetime.utcnow()

    await session.execute(
        text("""
            INSERT INTO prospect_lists (
                id, name, filename, original_filename, file_size, file_hash,
                status, total_rows, valid_prospects, processed_prospects,
                errors, warnings, headers_found,
                prospects_json,
                team_id, created_by, created_at, updated_at
            ) VALUES (
                :id, :name, :filename, :original_filename, :file_size, :file_hash,
                :status, :total_rows, :valid_prospects, :processed_prospects,
                :errors, :warnings, :headers_found,
                :prospects_json,
                :team_id, :created_by, :created_at, :updated_at
            )
        """),
        {
            "id": str(list_id),
            "name": file.filename or "Untitled",
            "filename": safe_filename,
            "original_filename": file.filename or "unknown.csv",
            "file_size": len(raw_bytes),
            "file_hash": file_hash,
            "status": "validated",
            "total_rows": report["total_rows"],
            "valid_prospects": report["valid_prospects"],
            "processed_prospects": 0,
            "errors": json.dumps(report["errors"]),
            "warnings": json.dumps(report["warnings"]),
            "headers_found": json.dumps(report["headers_found"]),
            "prospects_json": json.dumps(prospects),
            "team_id": team_id,
            "created_by": user.user_id,
            "created_at": now,
            "updated_at": now,
        },
    )
    await session.commit()

    # --- Audit log ------------------------------------------------------------
    await AuditService.log_prospect_list_upload(
        session=session,
        user=user,
        list_id=str(list_id),
        filename=file.filename or "unknown.csv",
        file_size=len(raw_bytes),
        total_prospects=report["valid_prospects"],
        request=request,
    )

    return ProspectListUploadResponse(
        id=list_id,
        filename=safe_filename,
        original_filename=file.filename or "unknown.csv",
        file_size=len(raw_bytes),
        file_hash=file_hash,
        status="validated",
        total_rows=report["total_rows"],
        valid_prospects=report["valid_prospects"],
        errors=report["errors"],
        warnings=report["warnings"],
        headers_found=report["headers_found"],
        uploaded_at=now,
        uploaded_by=user.email,
    )


@router.get(
    "",
    response_model=ProspectListListResponse,
    summary="List prospect lists for the current team",
)
async def list_prospect_lists(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status_filter: Optional[str] = Query(default=None, alias="status", description="Filter by status"),
    user: TokenData = Depends(require_data_team_or_admin),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Return all prospect lists visible to the user's team.
    Supports pagination and optional status filtering.
    """
    team_id = await _get_user_team_id(session, user.user_id)

    # Build query with optional filters
    where_clauses = []
    params: Dict[str, Any] = {"skip": skip, "limit": limit}

    if team_id:
        where_clauses.append("team_id = :team_id")
        params["team_id"] = team_id
    else:
        # If no team, show only the user's own lists
        where_clauses.append("created_by = :created_by")
        params["created_by"] = user.user_id

    if status_filter:
        where_clauses.append("status = :status_filter")
        params["status_filter"] = status_filter

    where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"

    # Count
    count_result = await session.execute(
        text(f"SELECT COUNT(*) FROM prospect_lists WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

    # Fetch page
    rows_result = await session.execute(
        text(f"""
            SELECT id, name, filename, status, total_rows, valid_prospects,
                   processed_prospects, created_at, created_by
            FROM prospect_lists
            WHERE {where_sql}
            ORDER BY created_at DESC
            OFFSET :skip LIMIT :limit
        """),
        params,
    )
    rows = rows_result.mappings().all()

    items = [
        ProspectListSummary(
            id=UUID(r["id"]) if isinstance(r["id"], str) else r["id"],
            name=r["name"],
            filename=r["filename"],
            status=r["status"],
            total_rows=r["total_rows"],
            valid_prospects=r["valid_prospects"],
            processed_prospects=r["processed_prospects"],
            created_at=r["created_at"],
            created_by=r["created_by"],
        )
        for r in rows
    ]

    return ProspectListListResponse(items=items, total=total, skip=skip, limit=limit)


@router.get(
    "/{list_id}",
    response_model=ProspectListDetail,
    summary="Get prospect list details",
)
async def get_prospect_list(
    list_id: UUID,
    user: TokenData = Depends(require_data_team_or_admin),
    session: AsyncSession = Depends(get_db_session),
):
    """Return full details for a specific prospect list."""
    row = await _get_list_row(session, list_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect list not found")

    # Ensure the user has access (same team or admin)
    team_id = await _get_user_team_id(session, user.user_id)
    if user.role != "admin" and row.get("team_id") != team_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this prospect list")

    return ProspectListDetail(
        id=UUID(row["id"]) if isinstance(row["id"], str) else row["id"],
        name=row["name"],
        filename=row["filename"],
        original_filename=row["original_filename"],
        file_size=row["file_size"],
        file_hash=row["file_hash"],
        status=row["status"],
        total_rows=row["total_rows"],
        valid_prospects=row["valid_prospects"],
        processed_prospects=row["processed_prospects"],
        errors=json.loads(row["errors"]) if isinstance(row["errors"], str) else (row["errors"] or []),
        warnings=json.loads(row["warnings"]) if isinstance(row["warnings"], str) else (row["warnings"] or []),
        headers_found=json.loads(row["headers_found"]) if isinstance(row["headers_found"], str) else (row["headers_found"] or []),
        created_at=row["created_at"],
        created_by=row["created_by"],
        team_id=row.get("team_id"),
        processed_at=row.get("processed_at"),
    )


@router.post(
    "/{list_id}/process",
    response_model=ProcessListResponse,
    summary="Process an uploaded list into the prospect database",
)
async def process_prospect_list(
    list_id: UUID,
    body: ProcessListRequest = ProcessListRequest(),
    request: Request = None,
    user: TokenData = Depends(require_data_team_or_admin),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Process a previously uploaded and validated prospect list.

    This creates ``Prospect`` rows in the database for each valid entry
    in the CSV. Duplicates can optionally be skipped.
    """
    row = await _get_list_row(session, list_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect list not found")

    if row["status"] not in ("validated", "error"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"List is in '{row['status']}' state. Only 'validated' or 'error' lists can be processed.",
        )

    # Check team access
    team_id = await _get_user_team_id(session, user.user_id)
    if user.role != "admin" and row.get("team_id") != team_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this prospect list")

    # Mark as processing
    await session.execute(
        text("UPDATE prospect_lists SET status = 'processing', updated_at = :now WHERE id = :id"),
        {"id": str(list_id), "now": datetime.utcnow()},
    )
    await session.commit()

    # Load the parsed prospects stored at upload time
    prospects_json = row.get("prospects_json")
    if prospects_json:
        prospects: List[Dict] = json.loads(prospects_json) if isinstance(prospects_json, str) else prospects_json
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Parsed prospect data not found. Please re-upload the file.",
        )

    # Optional deduplication
    skipped_duplicate = 0
    if body.deduplicate:
        prospects, dup_emails = await ProspectCSVParser.deduplicate_prospects(prospects)
        skipped_duplicate = len(dup_emails)

    created = 0
    skipped_existing = 0
    failed = 0
    errors: List[str] = []

    for p in prospects:
        try:
            email = p["email"].lower()

            if body.skip_existing:
                existing = await session.execute(
                    text("SELECT id FROM prospects WHERE email = :email"),
                    {"email": email},
                )
                if existing.scalar_one_or_none() is not None:
                    skipped_existing += 1
                    continue

            prospect_id = uuid4()
            now = datetime.utcnow()

            await session.execute(
                text("""
                    INSERT INTO prospects (
                        id, email, first_name, last_name, full_name,
                        company_name, company_domain, company_size,
                        industry, job_title, linkedin_url,
                        source, import_batch_id,
                        team_id, created_by, status,
                        created_at, updated_at
                    ) VALUES (
                        :id, :email, :first_name, :last_name, :full_name,
                        :company_name, :company_domain, :company_size,
                        :industry, :job_title, :linkedin_url,
                        :source, :import_batch_id,
                        :team_id, :created_by, :status,
                        :created_at, :updated_at
                    )
                """),
                {
                    "id": str(prospect_id),
                    "email": email,
                    "first_name": p.get("first_name", ""),
                    "last_name": p.get("last_name", ""),
                    "full_name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
                    "company_name": p.get("company_name", ""),
                    "company_domain": p.get("company_domain", ""),
                    "company_size": p.get("company_size", ""),
                    "industry": p.get("industry", ""),
                    "job_title": p.get("title", ""),
                    "linkedin_url": p.get("linkedin_url", ""),
                    "source": "csv_upload",
                    "import_batch_id": str(list_id),
                    "team_id": team_id,
                    "created_by": user.user_id,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                },
            )
            created += 1
        except Exception as exc:
            failed += 1
            errors.append(f"{p.get('email', 'unknown')}: {exc}")

    # Update list status
    processed_at = datetime.utcnow()
    final_status = "processed" if failed == 0 else "error"

    await session.execute(
        text("""
            UPDATE prospect_lists
            SET status = :status,
                processed_prospects = :processed,
                processed_at = :processed_at,
                updated_at = :updated_at
            WHERE id = :id
        """),
        {
            "id": str(list_id),
            "status": final_status,
            "processed": created,
            "processed_at": processed_at,
            "updated_at": processed_at,
        },
    )
    await session.commit()

    # Audit log
    await AuditService.log_action(
        session=session,
        user=user,
        action=AuditService.ACTION_IMPORT,
        resource_type=AuditService.RESOURCE_PROSPECT_LIST,
        resource_id=str(list_id),
        resource_name=row.get("original_filename", ""),
        details={
            "created": created,
            "skipped_duplicate": skipped_duplicate,
            "skipped_existing": skipped_existing,
            "failed": failed,
        },
        request=request,
    )

    return ProcessListResponse(
        list_id=list_id,
        status=final_status,
        total_in_file=row["valid_prospects"],
        created=created,
        skipped_duplicate=skipped_duplicate,
        skipped_existing=skipped_existing,
        failed=failed,
        errors=errors[:20],
        processed_at=processed_at,
    )


@router.delete(
    "/{list_id}",
    response_model=DeleteListResponse,
    summary="Delete a prospect list (admin only)",
)
async def delete_prospect_list(
    list_id: UUID,
    request: Request = None,
    user: TokenData = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Permanently delete a prospect list and its stored CSV file.

    **Admin only.** Prospects already imported into the database are *not*
    removed -- only the list metadata and raw file are deleted.
    """
    row = await _get_list_row(session, list_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect list not found")

    # Delete the physical file if it exists
    filepath = os.path.join(UPLOAD_DIR, row["filename"])
    if os.path.isfile(filepath):
        os.remove(filepath)

    # Delete database row
    await session.execute(
        text("DELETE FROM prospect_lists WHERE id = :id"),
        {"id": str(list_id)},
    )
    await session.commit()

    # Audit
    await AuditService.log_action(
        session=session,
        user=user,
        action=AuditService.ACTION_DELETE,
        resource_type=AuditService.RESOURCE_PROSPECT_LIST,
        resource_id=str(list_id),
        resource_name=row.get("original_filename", ""),
        request=request,
    )

    return DeleteListResponse(
        id=list_id,
        deleted=True,
        message="Prospect list deleted. Previously imported prospects remain in the database.",
    )
