"""
User service for database operations.

Handles user CRUD operations with PostgreSQL persistence.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.core.security import get_password_hash, verify_password
from app.core.config import settings


class UserService:
    """Service for user-related database operations."""

    async def get_by_email(self, session: AsyncSession, email: str) -> Optional[User]:
        """Get a user by email address."""
        result = await session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, session: AsyncSession, user_id: str) -> Optional[User]:
        """Get a user by ID."""
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        session: AsyncSession,
        email: str,
        password: str,
        full_name: str = "",
        role: str = "user",
    ) -> User:
        """Create a new user."""
        user = User(
            id=uuid4(),
            email=email,
            hashed_password=get_password_hash(password),
            full_name=full_name or None,
            role=role,
            is_active=True,
            is_verified=False,
            onboarding_progress={"completed_tours": [], "skipped_tours": []},
        )
        session.add(user)
        await session.flush()
        return user

    async def authenticate(
        self,
        session: AsyncSession,
        email: str,
        password: str,
    ) -> Optional[User]:
        """Authenticate a user by email and password."""
        user = await self.get_by_email(session, email)

        if not user:
            if settings.environment == "development":
                # DEV ONLY: Auto-create user for easy development
                user = await self.create(
                    session,
                    email=email,
                    password=password,
                    full_name=email.split("@")[0].replace(".", " ").title(),
                    role="admin",
                )
                await session.commit()
                return user
            return None

        if not user.is_active:
            return None

        # Always verify password outside development mode
        if settings.environment != "development":
            if not verify_password(password, user.hashed_password):
                return None

        return user

    async def update_last_login(self, session: AsyncSession, user: User) -> None:
        """Update the user's last login timestamp."""
        user.last_login = datetime.utcnow()
        await session.flush()

    async def update_onboarding_progress(
        self,
        session: AsyncSession,
        user: User,
        tour_id: str,
        action: str = "complete",
    ) -> None:
        """Update a user's onboarding progress."""
        progress = user.onboarding_progress or {"completed_tours": [], "skipped_tours": []}

        if action == "complete" and tour_id not in progress.get("completed_tours", []):
            progress.setdefault("completed_tours", []).append(tour_id)
        elif action == "skip" and tour_id not in progress.get("skipped_tours", []):
            progress.setdefault("skipped_tours", []).append(tour_id)

        user.onboarding_progress = progress
        await session.flush()

    async def update_profile(
        self,
        session: AsyncSession,
        user: User,
        full_name: Optional[str] = None,
        job_title: Optional[str] = None,
    ) -> User:
        """Update user profile fields."""
        if full_name is not None:
            user.full_name = full_name
        if job_title is not None:
            user.job_title = job_title
        user.updated_at = datetime.utcnow()
        await session.flush()
        return user

    async def email_exists(self, session: AsyncSession, email: str) -> bool:
        """Check if an email is already registered."""
        user = await self.get_by_email(session, email)
        return user is not None

    async def ensure_default_admin(self, session: AsyncSession) -> None:
        """Ensure a default admin user exists. Only runs in development."""
        if settings.environment != "development":
            return

        admin_email = "admin@champions.dev"
        existing = await self.get_by_email(session, admin_email)

        if not existing:
            await self.create(
                session,
                email=admin_email,
                password="admin123",
                full_name="Admin User",
                role="admin",
            )
            await session.commit()


# Singleton instance
user_service = UserService()
