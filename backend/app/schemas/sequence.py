"""
Pydantic schemas for Sequence operations.
Based on PRD multi-step email sequence specification.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


class SequenceStatus(str, Enum):
    """Sequence status options."""
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class EnrollmentStatus(str, Enum):
    """Prospect enrollment status."""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    REPLIED = "replied"
    BOUNCED = "bounced"
    UNSUBSCRIBED = "unsubscribed"


class StepType(str, Enum):
    """Sequence step types."""
    EMAIL = "email"
    WAIT = "wait"
    CONDITION = "condition"


class SequenceStepCreate(BaseModel):
    """Schema for creating a sequence step."""
    step_number: int = Field(..., ge=1, le=10)
    step_type: StepType = StepType.EMAIL
    delay_days: int = Field(default=1, ge=0, le=30)
    delay_hours: int = Field(default=0, ge=0, le=23)
    template_id: str | None = None
    subject: str = ""
    body: str = ""
    condition: str | None = None  # e.g., "opened", "clicked", "no_reply"


class SequenceStepResponse(SequenceStepCreate):
    """Sequence step response."""
    id: int | None = None


class SequenceCreate(BaseModel):
    """Schema for creating a sequence."""
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    steps: list[SequenceStepCreate] = []


class SequenceUpdate(BaseModel):
    """Schema for updating a sequence."""
    name: str | None = None
    description: str | None = None
    status: SequenceStatus | None = None


class SequenceResponse(BaseModel):
    """Full sequence response."""
    id: int
    name: str
    description: str = ""
    status: SequenceStatus = SequenceStatus.DRAFT
    steps_count: int = 0
    owner_id: str
    created_at: datetime | None = None
    steps: list[SequenceStepResponse] = []

    # Analytics (optional)
    enrolled_count: int = 0
    active_count: int = 0
    completed_count: int = 0
    replied_count: int = 0

    class Config:
        from_attributes = True


class SequenceListResponse(BaseModel):
    """Paginated list of sequences."""
    items: list[SequenceResponse]
    total: int


class EnrollmentRequest(BaseModel):
    """Request to enroll prospects in a sequence."""
    prospect_emails: list[str] = Field(..., min_length=1, max_length=1000)


class EnrollmentResponse(BaseModel):
    """Enrollment result."""
    enrolled: int
    already_enrolled: int
    failed: int
    errors: list[str] = []


class ProspectEnrollment(BaseModel):
    """Individual prospect enrollment status."""
    prospect_email: str
    sequence_id: int
    status: EnrollmentStatus
    current_step: int
    enrolled_at: datetime | None = None
    paused_at: datetime | None = None
    completed_at: datetime | None = None
