"""
Team service for database operations.

Handles team CRUD, invitations, and member management.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID, uuid4

from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import Team, TeamInvite, User


class TeamService:
    """Service for team-related database operations."""

    # --- Team CRUD ---

    async def create_team(
        self,
        session: AsyncSession,
        name: str,
        owner_id: UUID,
        max_members: int = 10,
    ) -> Team:
        """Create a new team with the specified owner."""
        team = Team(
            id=uuid4(),
            name=name,
            owner_id=owner_id,
            max_members=str(max_members),
        )
        session.add(team)
        await session.flush()

        # Update owner's team_id
        owner = await session.get(User, owner_id)
        if owner:
            owner.team_id = team.id
            owner.role = "team_admin"
            await session.flush()

        return team

    async def get_team_by_id(
        self,
        session: AsyncSession,
        team_id: UUID,
    ) -> Optional[Team]:
        """Get a team by its ID."""
        result = await session.execute(
            select(Team).where(Team.id == team_id)
        )
        return result.scalar_one_or_none()

    async def get_user_team(
        self,
        session: AsyncSession,
        user_id: UUID,
    ) -> Optional[Team]:
        """Get the team a user belongs to."""
        user = await session.get(User, user_id)
        if not user or not user.team_id:
            return None

        return await self.get_team_by_id(session, user.team_id)

    async def update_team(
        self,
        session: AsyncSession,
        team: Team,
        name: Optional[str] = None,
        max_members: Optional[int] = None,
    ) -> Team:
        """Update team details."""
        if name is not None:
            team.name = name
        if max_members is not None:
            team.max_members = str(max_members)
        team.updated_at = datetime.utcnow()
        await session.flush()
        return team

    async def delete_team(
        self,
        session: AsyncSession,
        team_id: UUID,
    ) -> bool:
        """Delete a team and remove all member associations."""
        team = await self.get_team_by_id(session, team_id)
        if not team:
            return False

        # Remove team association from all members
        members = await self.get_team_members(session, team_id)
        for member in members:
            member.team_id = None
            member.role = "user"

        # Delete pending invites
        await session.execute(
            delete(TeamInvite).where(TeamInvite.team_id == team_id)
        )

        # Delete the team
        await session.delete(team)
        await session.flush()
        return True

    # --- Member Management ---

    async def get_team_members(
        self,
        session: AsyncSession,
        team_id: UUID,
    ) -> List[User]:
        """Get all members of a team."""
        result = await session.execute(
            select(User).where(User.team_id == team_id).order_by(User.created_at)
        )
        return list(result.scalars().all())

    async def get_member_count(
        self,
        session: AsyncSession,
        team_id: UUID,
    ) -> int:
        """Get the number of members in a team."""
        members = await self.get_team_members(session, team_id)
        return len(members)

    async def add_member(
        self,
        session: AsyncSession,
        team_id: UUID,
        user_id: UUID,
        role: str = "user",
    ) -> bool:
        """Add a user to a team."""
        team = await self.get_team_by_id(session, team_id)
        if not team:
            return False

        # Check max members
        current_count = await self.get_member_count(session, team_id)
        max_members = int(team.max_members or 10)
        if current_count >= max_members:
            return False

        user = await session.get(User, user_id)
        if not user:
            return False

        user.team_id = team_id
        user.role = role
        await session.flush()
        return True

    async def remove_member(
        self,
        session: AsyncSession,
        team_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Remove a user from a team."""
        team = await self.get_team_by_id(session, team_id)
        if not team:
            return False

        # Cannot remove the owner
        if team.owner_id == user_id:
            return False

        user = await session.get(User, user_id)
        if not user or user.team_id != team_id:
            return False

        user.team_id = None
        user.role = "user"
        await session.flush()
        return True

    async def update_member_role(
        self,
        session: AsyncSession,
        team_id: UUID,
        user_id: UUID,
        new_role: str,
    ) -> bool:
        """Update a team member's role."""
        user = await session.get(User, user_id)
        if not user or user.team_id != team_id:
            return False

        user.role = new_role
        await session.flush()
        return True

    async def is_team_admin(
        self,
        session: AsyncSession,
        team_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Check if a user is an admin of a team."""
        team = await self.get_team_by_id(session, team_id)
        if not team:
            return False

        # Owner is always admin
        if team.owner_id == user_id:
            return True

        user = await session.get(User, user_id)
        return user is not None and user.team_id == team_id and user.role in ("admin", "team_admin")

    # --- Invitations ---

    async def create_invite(
        self,
        session: AsyncSession,
        team_id: UUID,
        email: str,
        invited_by: UUID,
        role: str = "user",
        expires_in_days: int = 7,
    ) -> Optional[TeamInvite]:
        """Create a team invitation."""
        team = await self.get_team_by_id(session, team_id)
        if not team:
            return None

        # Check if user is already a member
        existing_user_result = await session.execute(
            select(User).where(
                and_(User.email == email, User.team_id == team_id)
            )
        )
        if existing_user_result.scalar_one_or_none():
            return None  # Already a member

        # Check for existing pending invite
        existing_invite_result = await session.execute(
            select(TeamInvite).where(
                and_(
                    TeamInvite.team_id == team_id,
                    TeamInvite.email == email,
                    TeamInvite.accepted_at.is_(None),
                    TeamInvite.expires_at > datetime.utcnow(),
                )
            )
        )
        existing_invite = existing_invite_result.scalar_one_or_none()
        if existing_invite:
            return existing_invite  # Return existing invite

        # Generate secure token
        token = secrets.token_urlsafe(32)

        invite = TeamInvite(
            id=uuid4(),
            team_id=team_id,
            email=email,
            role=role,
            token=token,
            invited_by=invited_by,
            expires_at=datetime.utcnow() + timedelta(days=expires_in_days),
        )
        session.add(invite)
        await session.flush()
        return invite

    async def get_invite_by_token(
        self,
        session: AsyncSession,
        token: str,
    ) -> Optional[TeamInvite]:
        """Get an invitation by its token."""
        result = await session.execute(
            select(TeamInvite)
            .options(selectinload(TeamInvite.team))
            .where(TeamInvite.token == token)
        )
        return result.scalar_one_or_none()

    async def get_pending_invites(
        self,
        session: AsyncSession,
        team_id: UUID,
    ) -> List[TeamInvite]:
        """Get all pending invitations for a team."""
        result = await session.execute(
            select(TeamInvite)
            .options(selectinload(TeamInvite.inviter))
            .where(
                and_(
                    TeamInvite.team_id == team_id,
                    TeamInvite.accepted_at.is_(None),
                    TeamInvite.expires_at > datetime.utcnow(),
                )
            )
            .order_by(TeamInvite.created_at.desc())
        )
        return list(result.scalars().all())

    async def accept_invite(
        self,
        session: AsyncSession,
        token: str,
        user_id: UUID,
    ) -> Optional[Team]:
        """Accept a team invitation."""
        invite = await self.get_invite_by_token(session, token)
        if not invite:
            return None

        # Check if invite has expired
        if invite.expires_at < datetime.utcnow():
            return None

        # Check if already accepted
        if invite.accepted_at:
            return None

        # Get the user
        user = await session.get(User, user_id)
        if not user:
            return None

        # Verify email matches
        if user.email.lower() != invite.email.lower():
            return None

        # Add user to team
        success = await self.add_member(session, invite.team_id, user_id, invite.role)
        if not success:
            return None

        # Mark invite as accepted
        invite.accepted_at = datetime.utcnow()
        await session.flush()

        return await self.get_team_by_id(session, invite.team_id)

    async def delete_invite(
        self,
        session: AsyncSession,
        invite_id: UUID,
        team_id: UUID,
    ) -> bool:
        """Delete/revoke a team invitation."""
        result = await session.execute(
            select(TeamInvite).where(
                and_(TeamInvite.id == invite_id, TeamInvite.team_id == team_id)
            )
        )
        invite = result.scalar_one_or_none()
        if not invite:
            return False

        await session.delete(invite)
        await session.flush()
        return True

    async def get_invites_for_email(
        self,
        session: AsyncSession,
        email: str,
    ) -> List[TeamInvite]:
        """Get all pending invitations for an email address."""
        result = await session.execute(
            select(TeamInvite)
            .options(selectinload(TeamInvite.team))
            .where(
                and_(
                    TeamInvite.email == email,
                    TeamInvite.accepted_at.is_(None),
                    TeamInvite.expires_at > datetime.utcnow(),
                )
            )
            .order_by(TeamInvite.created_at.desc())
        )
        return list(result.scalars().all())


# Singleton instance
team_service = TeamService()
