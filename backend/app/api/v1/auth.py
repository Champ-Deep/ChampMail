"""
Authentication endpoints.

JWT-based auth with PostgreSQL user persistence.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    Token,
    TokenData,
    require_auth,
)
from app.db.postgres import get_db_session
from app.services.user_service import user_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ============================================================================
# Request/Response Models
# ============================================================================


class LoginRequest(BaseModel):
    """Login credentials."""
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    """Registration request."""
    email: EmailStr
    password: str
    name: str = ""


class UserResponse(BaseModel):
    """User info response."""
    user_id: str
    email: str
    full_name: Optional[str] = None
    role: str
    is_verified: bool = False
    onboarding_progress: Optional[dict] = None


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/login", response_model=Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: AsyncSession = Depends(get_db_session),
):
    """
    Authenticate and receive JWT token.

    Accepts OAuth2 password form (username/password).
    Username should be the email address.

    Development credentials:
    - Admin: admin@champions.dev / admin123
    """
    # OAuth2 form uses 'username' field, but we expect email
    email = form_data.username

    user = await user_service.authenticate(session, email, form_data.password)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    # Update last login timestamp
    await user_service.update_last_login(session, user)
    await session.commit()

    access_token = create_access_token(
        data={
            "user_id": str(user.id),
            "email": user.email,
            "role": user.role,
            "team_id": str(user.team_id) if user.team_id else None,
        },
        expires_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes),
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/register", response_model=UserResponse)
async def register(
    request: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Register a new user.

    Creates a new user account in the database.
    """
    # Check if email already exists
    if await user_service.email_exists(session, request.email):
        raise HTTPException(
            status_code=409,
            detail="User already exists",
        )

    # Create the user
    user = await user_service.create(
        session,
        email=request.email,
        password=request.password,
        full_name=request.name,
    )
    await session.commit()

    return UserResponse(
        user_id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_verified=user.is_verified,
        onboarding_progress=user.onboarding_progress,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get current authenticated user info.
    """
    db_user = await user_service.get_by_id(session, user.user_id)

    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(
        user_id=str(db_user.id),
        email=db_user.email,
        full_name=db_user.full_name,
        role=db_user.role,
        is_verified=db_user.is_verified,
        onboarding_progress=db_user.onboarding_progress,
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(user: TokenData = Depends(require_auth)):
    """
    Refresh the access token.
    """
    access_token = create_access_token(
        data={
            "user_id": user.user_id,
            "email": user.email,
            "role": user.role,
            "team_id": user.team_id,
        },
        expires_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes),
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/onboarding/{tour_id}/complete")
async def complete_tour(
    tour_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Mark an onboarding tour as completed.
    """
    db_user = await user_service.get_by_id(session, user.user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    await user_service.update_onboarding_progress(session, db_user, tour_id, "complete")
    await session.commit()

    return {"message": f"Tour {tour_id} marked as completed"}


@router.post("/onboarding/{tour_id}/skip")
async def skip_tour(
    tour_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Mark an onboarding tour as skipped.
    """
    db_user = await user_service.get_by_id(session, user.user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    await user_service.update_onboarding_progress(session, db_user, tour_id, "skip")
    await session.commit()

    return {"message": f"Tour {tour_id} marked as skipped"}


@router.get("/onboarding/progress")
async def get_onboarding_progress(
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get the user's onboarding progress.
    """
    db_user = await user_service.get_by_id(session, user.user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    return db_user.onboarding_progress or {"completed_tours": [], "skipped_tours": []}
