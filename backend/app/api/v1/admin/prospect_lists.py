"""
Prospect list management endpoints.

Two-phase upload flow:
  1. POST /upload-preview  — upload file, get headers + sample rows + auto-mapping
  2. POST /upload-confirm  — submit column mapping + file hash, persist & validate

Also supports the legacy single-step POST /upload for backwards compat.
"""

from __future__ import annotations

import os
import json
import aiofiles
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenData
from app.core.admin_security import require_data_team_or_admin, require_admin
from app.db.postgres import get_db_session
from app.utils.file_parser import ProspectFileParser, FileValidationError
from app.services.audit_service import AuditService

router = APIRouter(prefix="/prospect-lists", tags=["Admin - Prospect Lists"])

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

UPLOAD_DIR = os.environ.get(
    "PROSPECT_UPLOAD_DIR",
    os.path.join(os.getcwd(), "uploads", "prospect_lists"),
)


def _ensure_upload_dir() -> str:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    return UPLOAD_DIR


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PreviewResponse(BaseModel):
    """Returned by upload-preview so the UI can build a column mapper."""

    format: str
    headers: List[str]
    sample_rows: List[List[str]]
    auto_mapping: Dict[str, str]
    total_rows: int
    file_size: int
    file_hash: str


class ConfirmRequest(BaseModel):
    """Submitted alongside the file to /upload-confirm."""

    column_mapping: Dict[str, str] = Field(
        ...,
        description='Maps file header → system field.  e.g. {"Email Address": "email"}',
    )
    name: Optional[str] = Field(
        default=None,
        description="Optional display name for this list (defaults to filename)",
    )


class ProspectListUploadResponse(BaseModel):
    id: UUID
    filename: str
    original_filename: str
    file_size: int
    file_hash: str
    status: str
    total_rows: int
    valid_prospects: int
    errors: List[str]
    warnings: List[str]
    headers_found: List[str]
    uploaded_at: datetime
    uploaded_by: str


class ProspectListSummary(BaseModel):
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
    items: List[ProspectListSummary]
    total: int
    skip: int
    limit: int


class ProcessListRequest(BaseModel):
    deduplicate: bool = Field(default=True)
    skip_existing: bool = Field(default=True)
    tag: Optional[str] = None


class ProcessListResponse(BaseModel):
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
    id: UUID
    deleted: bool
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_list_row(
    session: AsyncSession, list_id: UUID
) -> Optional[Dict[str, Any]]:
    result = await session.execute(
        text("SELECT * FROM prospect_lists WHERE id = :id"),
        {"id": str(list_id)},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def _get_user_team_id(
    session: AsyncSession, user_id: str
) -> Optional[str]:
    result = await session.execute(
        text("SELECT team_id FROM users WHERE id = :uid"),
        {"uid": user_id},
    )
    row = result.scalar_one_or_none()
    return str(row) if row else None


async def _persist_list(
    session: AsyncSession,
    *,
    list_id: UUID,
    name: str,
    filename: str,
    original_filename: str,
    raw_bytes: bytes,
    file_hash: str,
    prospects: List[Dict],
    report: Dict[str, Any],
    team_id: Optional[str],
    user_id: str,
) -> None:
    """Save prospect list metadata + parsed JSON to Postgres."""
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
            "name": name,
            "filename": filename,
            "original_filename": original_filename,
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
            "created_by": user_id,
            "created_at": now,
            "updated_at": now,
        },
    )
    await session.commit()


# ---------------------------------------------------------------------------
# Endpoints — New two-phase flow
# ---------------------------------------------------------------------------


@router.post(
    "/upload-preview",
    response_model=PreviewResponse,
    summary="Upload a file and get headers + sample rows for column mapping",
)
async def upload_preview(
    file: UploadFile = File(
        ..., description="CSV or XLSX file containing prospect data"
    ),
    user: TokenData = Depends(require_data_team_or_admin),
):
    """
    Phase 1 of the upload flow.

    Reads headers and a handful of sample rows from the uploaded file,
    returns them along with an auto-suggested column mapping so the UI
    can present a mapping screen.  Nothing is persisted yet.
    """
    try:
        preview = await ProspectFileParser.preview(file)
    except FileValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    return PreviewResponse(**preview)


@router.post(
    "/upload-confirm",
    response_model=ProspectListUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Confirm upload with column mapping — validates and persists",
)
async def upload_confirm(
    file: UploadFile = File(...),
    column_mapping: str = Query(
        ...,
        description='JSON string of column mapping, e.g. {"Email Address":"email"}',
    ),
    name: Optional[str] = Query(
        default=None, description="Display name for the list"
    ),
    request: Request = None,
    user: TokenData = Depends(require_data_team_or_admin),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Phase 2 of the upload flow.

    Accepts the file again along with a column mapping.  Parses every row,
    validates, and persists the list in the database.

    The column_mapping is a JSON-encoded dict sent as a query param because
    multipart/form-data doesn't natively support nested JSON bodies.
    """
    # Parse column mapping JSON
    try:
        mapping: Dict[str, str] = json.loads(column_mapping)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="column_mapping must be a valid JSON string",
        )

    # Parse & validate
    try:
        prospects, report = await ProspectFileParser.parse(file, mapping)
    except FileValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File validation failed: {exc}",
        )

    # Persist raw file to disk
    await file.seek(0)
    raw_bytes = await file.read()
    file_hash = ProspectFileParser.compute_file_hash(raw_bytes)

    list_id = uuid4()
    ext = ProspectFileParser.detect_format(file.filename or "")
    safe_filename = f"{list_id}.{ext}"
    upload_dir = _ensure_upload_dir()
    filepath = os.path.join(upload_dir, safe_filename)

    async with aiofiles.open(filepath, "wb") as out:
        await out.write(raw_bytes)

    # Save to DB
    team_id = await _get_user_team_id(session, user.user_id)
    display_name = name or file.filename or "Untitled"

    await _persist_list(
        session,
        list_id=list_id,
        name=display_name,
        filename=safe_filename,
        original_filename=file.filename or "unknown",
        raw_bytes=raw_bytes,
        file_hash=file_hash,
        prospects=prospects,
        report=report,
        team_id=team_id,
        user_id=user.user_id,
    )

    # Audit
    await AuditService.log_prospect_list_upload(
        session=session,
        user=user,
        list_id=str(list_id),
        filename=file.filename or "unknown",
        file_size=len(raw_bytes),
        total_prospects=report["valid_prospects"],
        request=request,
    )

    now = datetime.utcnow()
    return ProspectListUploadResponse(
        id=list_id,
        filename=safe_filename,
        original_filename=file.filename or "unknown",
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


# ---------------------------------------------------------------------------
# Legacy single-step upload (backwards compat)
# ---------------------------------------------------------------------------


@router.post(
    "/upload",
    response_model=ProspectListUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a prospect file (CSV or XLSX) — single-step with auto-mapping",
)
async def upload_prospect_list(
    file: UploadFile = File(
        ..., description="CSV or XLSX file containing prospect data"
    ),
    request: Request = None,
    user: TokenData = Depends(require_data_team_or_admin),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Single-step upload that auto-maps headers using common aliases.

    Use the two-phase /upload-preview + /upload-confirm flow instead if
    your file uses non-standard column names.
    """
    try:
        prospects, report = await ProspectFileParser.parse_and_validate(
            file, validate_only=False
        )
    except FileValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Validation failed: {exc}",
        )

    await file.seek(0)
    raw_bytes = await file.read()
    file_hash = ProspectFileParser.compute_file_hash(raw_bytes)

    list_id = uuid4()
    ext = ProspectFileParser.detect_format(file.filename or "")
    safe_filename = f"{list_id}.{ext}"
    upload_dir = _ensure_upload_dir()
    filepath = os.path.join(upload_dir, safe_filename)

    async with aiofiles.open(filepath, "wb") as out:
        await out.write(raw_bytes)

    team_id = await _get_user_team_id(session, user.user_id)

    await _persist_list(
        session,
        list_id=list_id,
        name=file.filename or "Untitled",
        filename=safe_filename,
        original_filename=file.filename or "unknown",
        raw_bytes=raw_bytes,
        file_hash=file_hash,
        prospects=prospects,
        report=report,
        team_id=team_id,
        user_id=user.user_id,
    )

    await AuditService.log_prospect_list_upload(
        session=session,
        user=user,
        list_id=str(list_id),
        filename=file.filename or "unknown",
        file_size=len(raw_bytes),
        total_prospects=report["valid_prospects"],
        request=request,
    )

    now = datetime.utcnow()
    return ProspectListUploadResponse(
        id=list_id,
        filename=safe_filename,
        original_filename=file.filename or "unknown",
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


# ---------------------------------------------------------------------------
# List / Detail / Process / Delete
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=ProspectListListResponse,
    summary="List prospect lists for the current team",
)
async def list_prospect_lists(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status_filter: Optional[str] = Query(
        default=None, alias="status", description="Filter by status"
    ),
    user: TokenData = Depends(require_data_team_or_admin),
    session: AsyncSession = Depends(get_db_session),
):
    team_id = await _get_user_team_id(session, user.user_id)

    where_clauses: List[str] = []
    params: Dict[str, Any] = {"skip": skip, "limit": limit}

    if team_id:
        where_clauses.append("team_id = :team_id")
        params["team_id"] = team_id
    else:
        where_clauses.append("created_by = :created_by")
        params["created_by"] = user.user_id

    if status_filter:
        where_clauses.append("status = :status_filter")
        params["status_filter"] = status_filter

    where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"

    count_result = await session.execute(
        text(f"SELECT COUNT(*) FROM prospect_lists WHERE {where_sql}"),
        params,
    )
    total = count_result.scalar_one()

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

    return ProspectListListResponse(
        items=items, total=total, skip=skip, limit=limit
    )


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
    row = await _get_list_row(session, list_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prospect list not found",
        )

    team_id = await _get_user_team_id(session, user.user_id)
    if user.role != "admin" and row.get("team_id") != team_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this prospect list",
        )

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
        errors=json.loads(row["errors"])
        if isinstance(row["errors"], str)
        else (row["errors"] or []),
        warnings=json.loads(row["warnings"])
        if isinstance(row["warnings"], str)
        else (row["warnings"] or []),
        headers_found=json.loads(row["headers_found"])
        if isinstance(row["headers_found"], str)
        else (row["headers_found"] or []),
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
    row = await _get_list_row(session, list_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prospect list not found",
        )

    if row["status"] not in ("validated", "error"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"List is in '{row['status']}' state. Only 'validated' or 'error' lists can be processed.",
        )

    team_id = await _get_user_team_id(session, user.user_id)
    if user.role != "admin" and row.get("team_id") != team_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this prospect list",
        )

    # Mark as processing
    await session.execute(
        text(
            "UPDATE prospect_lists SET status = 'processing', updated_at = :now WHERE id = :id"
        ),
        {"id": str(list_id), "now": datetime.utcnow()},
    )
    await session.commit()

    # Load parsed prospects from upload time
    prospects_json = row.get("prospects_json")
    if not prospects_json:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Parsed prospect data not found. Please re-upload the file.",
        )

    prospects: List[Dict] = (
        json.loads(prospects_json)
        if isinstance(prospects_json, str)
        else prospects_json
    )

    # Dedup
    skipped_duplicate = 0
    if body.deduplicate:
        prospects, dup_emails = await ProspectFileParser.deduplicate_prospects(
            prospects
        )
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
                    "source": "file_upload",
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

    # Audit
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
    row = await _get_list_row(session, list_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prospect list not found",
        )

    filepath = os.path.join(UPLOAD_DIR, row["filename"])
    if os.path.isfile(filepath):
        os.remove(filepath)

    await session.execute(
        text("DELETE FROM prospect_lists WHERE id = :id"),
        {"id": str(list_id)},
    )
    await session.commit()

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
