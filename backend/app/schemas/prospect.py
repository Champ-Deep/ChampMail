"""
Pydantic schemas for Prospect operations.
Based on PRD knowledge graph schema.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field


class ProspectBase(BaseModel):
    """Base prospect fields."""
    email: EmailStr
    first_name: str = ""
    last_name: str = ""
    title: str = ""
    phone: str = ""
    linkedin_url: str = ""


class ProspectCreate(ProspectBase):
    """Schema for creating a prospect."""
    company_name: str | None = None
    company_domain: str | None = None
    industry: str | None = None


class ProspectUpdate(BaseModel):
    """Schema for updating a prospect."""
    first_name: str | None = None
    last_name: str | None = None
    title: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None


class CompanyInfo(BaseModel):
    """Embedded company information."""
    name: str
    domain: str
    industry: str = ""
    employee_count: int = 0


class WorksAtRelation(BaseModel):
    """WORKS_AT relationship data."""
    title: str = ""
    is_current: bool = True


class ProspectResponse(ProspectBase):
    """Full prospect response with relationships."""
    id: int | None = None
    created_at: datetime | None = None
    company: CompanyInfo | None = None
    works_at: WorksAtRelation | None = None

    class Config:
        from_attributes = True


class ProspectListResponse(BaseModel):
    """Paginated list of prospects."""
    items: list[ProspectResponse]
    total: int
    skip: int
    limit: int


class ProspectSearchParams(BaseModel):
    """Search parameters for prospects."""
    query: str = ""
    industry: str = ""
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=200)


class BulkProspectImport(BaseModel):
    """Bulk import request."""
    prospects: list[ProspectCreate]


class BulkImportResponse(BaseModel):
    """Bulk import result."""
    created: int
    updated: int
    failed: int
    errors: list[str] = []
