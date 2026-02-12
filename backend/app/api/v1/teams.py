"""
Team management endpoints.

Handles team creation, member management, and invitations.
"""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenData, require_auth
from app.db.postgres import get_db_session
from app.services.team_service import team_service
from app.services.user_service import user_service

router = APIRouter(prefix="/teams", tags=["Teams"])


# ============================================================================
# Request/Response Models
# ============================================================================


class CreateTeamRequest(BaseModel):
    """Request to create a new team."""
    name: str
    max_members: int = 10


class UpdateTeamRequest(BaseModel):
    """Request to update team details."""
    name: Optional[str] = None
    max_members: Optional[int] = None


class TeamResponse(BaseModel):
    """Team information response."""
    id: str
    name: str
    owner_id: str
    max_members: int
    member_count: int
    is_owner: bool
    is_admin: bool


class TeamMemberResponse(BaseModel):
    """Team member information."""
    id: str
    email: str
    full_name: Optional[str]
    role: str
    is_owner: bool


class InviteMemberRequest(BaseModel):
    """Request to invite a member to the team."""
    email: EmailStr
    role: str = "user"


class TeamInviteResponse(BaseModel):
    """Team invitation response."""
    id: str
    email: str
    role: str
    token: str
    invited_by_email: Optional[str]
    expires_at: str
    invite_url: str


class AcceptInviteRequest(BaseModel):
    """Request to accept a team invitation."""
    token: str


class UpdateMemberRoleRequest(BaseModel):
    """Request to update a member's role."""
    role: str


class PendingInviteResponse(BaseModel):
    """Pending invitation for the current user."""
    id: str
    team_name: str
    team_id: str
    role: str
    token: str
    expires_at: str


# ============================================================================
# Team CRUD Endpoints
# ============================================================================


@router.post("", response_model=TeamResponse)
async def create_team(
    request: CreateTeamRequest,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Create a new team.

    The authenticated user becomes the team owner.
    """
    # Check if user already has a team
    existing_team = await team_service.get_user_team(session, UUID(user.user_id))
    if existing_team:
        raise HTTPException(
            status_code=400,
            detail="You are already a member of a team. Leave your current team first.",
        )

    team = await team_service.create_team(
        session,
        name=request.name,
        owner_id=UUID(user.user_id),
        max_members=request.max_members,
    )
    await session.commit()

    member_count = await team_service.get_member_count(session, team.id)

    return TeamResponse(
        id=str(team.id),
        name=team.name,
        owner_id=str(team.owner_id),
        max_members=int(team.max_members or 10),
        member_count=member_count,
        is_owner=True,
        is_admin=True,
    )


@router.get("/my-team", response_model=Optional[TeamResponse])
async def get_my_team(
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get the current user's team.

    Returns null if the user is not a member of any team.
    """
    team = await team_service.get_user_team(session, UUID(user.user_id))
    if not team:
        return None

    member_count = await team_service.get_member_count(session, team.id)
    is_admin = await team_service.is_team_admin(session, team.id, UUID(user.user_id))

    return TeamResponse(
        id=str(team.id),
        name=team.name,
        owner_id=str(team.owner_id),
        max_members=int(team.max_members or 10),
        member_count=member_count,
        is_owner=str(team.owner_id) == user.user_id,
        is_admin=is_admin,
    )


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get team details by ID.

    User must be a member of the team.
    """
    team = await team_service.get_team_by_id(session, UUID(team_id))
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Check membership
    db_user = await user_service.get_by_id(session, user.user_id)
    if not db_user or str(db_user.team_id) != team_id:
        raise HTTPException(status_code=403, detail="Not a member of this team")

    member_count = await team_service.get_member_count(session, team.id)
    is_admin = await team_service.is_team_admin(session, team.id, UUID(user.user_id))

    return TeamResponse(
        id=str(team.id),
        name=team.name,
        owner_id=str(team.owner_id),
        max_members=int(team.max_members or 10),
        member_count=member_count,
        is_owner=str(team.owner_id) == user.user_id,
        is_admin=is_admin,
    )


@router.put("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: str,
    request: UpdateTeamRequest,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Update team details.

    Requires team admin privileges.
    """
    team = await team_service.get_team_by_id(session, UUID(team_id))
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Check admin permission
    if not await team_service.is_team_admin(session, UUID(team_id), UUID(user.user_id)):
        raise HTTPException(status_code=403, detail="Only team admins can update team settings")

    team = await team_service.update_team(
        session,
        team,
        name=request.name,
        max_members=request.max_members,
    )
    await session.commit()

    member_count = await team_service.get_member_count(session, team.id)

    return TeamResponse(
        id=str(team.id),
        name=team.name,
        owner_id=str(team.owner_id),
        max_members=int(team.max_members or 10),
        member_count=member_count,
        is_owner=str(team.owner_id) == user.user_id,
        is_admin=True,
    )


@router.delete("/{team_id}")
async def delete_team(
    team_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Delete a team.

    Only the team owner can delete a team.
    All members will be removed from the team.
    """
    team = await team_service.get_team_by_id(session, UUID(team_id))
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Only owner can delete
    if str(team.owner_id) != user.user_id:
        raise HTTPException(status_code=403, detail="Only the team owner can delete the team")

    success = await team_service.delete_team(session, UUID(team_id))
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete team")

    await session.commit()
    return {"message": "Team deleted successfully"}


# ============================================================================
# Member Management Endpoints
# ============================================================================


@router.get("/{team_id}/members", response_model=List[TeamMemberResponse])
async def get_team_members(
    team_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get all members of a team.

    User must be a member of the team.
    """
    team = await team_service.get_team_by_id(session, UUID(team_id))
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Check membership
    db_user = await user_service.get_by_id(session, user.user_id)
    if not db_user or str(db_user.team_id) != team_id:
        raise HTTPException(status_code=403, detail="Not a member of this team")

    members = await team_service.get_team_members(session, UUID(team_id))

    return [
        TeamMemberResponse(
            id=str(member.id),
            email=member.email,
            full_name=member.full_name,
            role=member.role,
            is_owner=str(member.id) == str(team.owner_id),
        )
        for member in members
    ]


@router.put("/{team_id}/members/{member_id}/role")
async def update_member_role(
    team_id: str,
    member_id: str,
    request: UpdateMemberRoleRequest,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Update a team member's role.

    Requires team admin privileges.
    Cannot change the owner's role.
    """
    team = await team_service.get_team_by_id(session, UUID(team_id))
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Check admin permission
    if not await team_service.is_team_admin(session, UUID(team_id), UUID(user.user_id)):
        raise HTTPException(status_code=403, detail="Only team admins can change roles")

    # Cannot change owner's role
    if str(team.owner_id) == member_id:
        raise HTTPException(status_code=400, detail="Cannot change the owner's role")

    # Validate role
    valid_roles = ["user", "team_admin"]
    if request.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {valid_roles}")

    success = await team_service.update_member_role(
        session, UUID(team_id), UUID(member_id), request.role
    )
    if not success:
        raise HTTPException(status_code=404, detail="Member not found in team")

    await session.commit()
    return {"message": "Role updated successfully"}


@router.delete("/{team_id}/members/{member_id}")
async def remove_member(
    team_id: str,
    member_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Remove a member from the team.

    Admins can remove any member (except owner).
    Users can only remove themselves.
    """
    team = await team_service.get_team_by_id(session, UUID(team_id))
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    is_self = member_id == user.user_id
    is_admin = await team_service.is_team_admin(session, UUID(team_id), UUID(user.user_id))

    # Check permission: admin or self
    if not is_admin and not is_self:
        raise HTTPException(status_code=403, detail="You can only remove yourself from the team")

    # Cannot remove owner
    if str(team.owner_id) == member_id:
        raise HTTPException(status_code=400, detail="Cannot remove the team owner")

    success = await team_service.remove_member(session, UUID(team_id), UUID(member_id))
    if not success:
        raise HTTPException(status_code=404, detail="Member not found in team")

    await session.commit()
    return {"message": "Member removed successfully"}


@router.post("/{team_id}/leave")
async def leave_team(
    team_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Leave the team.

    Owner cannot leave - must delete team or transfer ownership.
    """
    team = await team_service.get_team_by_id(session, UUID(team_id))
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Check membership
    db_user = await user_service.get_by_id(session, user.user_id)
    if not db_user or str(db_user.team_id) != team_id:
        raise HTTPException(status_code=400, detail="You are not a member of this team")

    # Owner cannot leave
    if str(team.owner_id) == user.user_id:
        raise HTTPException(
            status_code=400,
            detail="Team owner cannot leave. Delete the team or transfer ownership first.",
        )

    success = await team_service.remove_member(session, UUID(team_id), UUID(user.user_id))
    if not success:
        raise HTTPException(status_code=500, detail="Failed to leave team")

    await session.commit()
    return {"message": "Successfully left the team"}


# ============================================================================
# Invitation Endpoints
# ============================================================================


@router.post("/{team_id}/invites", response_model=TeamInviteResponse)
async def invite_member(
    team_id: str,
    request: InviteMemberRequest,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Invite a new member to the team.

    Requires team admin privileges.
    Returns an invite token that can be shared with the invitee.
    """
    team = await team_service.get_team_by_id(session, UUID(team_id))
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Check admin permission
    if not await team_service.is_team_admin(session, UUID(team_id), UUID(user.user_id)):
        raise HTTPException(status_code=403, detail="Only team admins can invite members")

    # Check team capacity
    member_count = await team_service.get_member_count(session, UUID(team_id))
    max_members = int(team.max_members or 10)
    if member_count >= max_members:
        raise HTTPException(
            status_code=400,
            detail=f"Team has reached maximum capacity ({max_members} members)",
        )

    # Validate role
    valid_roles = ["user", "team_admin"]
    if request.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {valid_roles}")

    invite = await team_service.create_invite(
        session,
        team_id=UUID(team_id),
        email=request.email,
        invited_by=UUID(user.user_id),
        role=request.role,
    )

    if not invite:
        raise HTTPException(
            status_code=400,
            detail="Could not create invite. User may already be a team member.",
        )

    await session.commit()

    # Get inviter email
    inviter = await user_service.get_by_id(session, user.user_id)
    inviter_email = inviter.email if inviter else None

    return TeamInviteResponse(
        id=str(invite.id),
        email=invite.email,
        role=invite.role,
        token=invite.token,
        invited_by_email=inviter_email,
        expires_at=invite.expires_at.isoformat(),
        invite_url=f"/join-team?token={invite.token}",
    )


@router.get("/{team_id}/invites", response_model=List[TeamInviteResponse])
async def get_pending_invites(
    team_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get all pending invitations for a team.

    Requires team admin privileges.
    """
    team = await team_service.get_team_by_id(session, UUID(team_id))
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Check admin permission
    if not await team_service.is_team_admin(session, UUID(team_id), UUID(user.user_id)):
        raise HTTPException(status_code=403, detail="Only team admins can view invites")

    invites = await team_service.get_pending_invites(session, UUID(team_id))

    return [
        TeamInviteResponse(
            id=str(invite.id),
            email=invite.email,
            role=invite.role,
            token=invite.token,
            invited_by_email=invite.inviter.email if invite.inviter else None,
            expires_at=invite.expires_at.isoformat(),
            invite_url=f"/join-team?token={invite.token}",
        )
        for invite in invites
    ]


@router.delete("/{team_id}/invites/{invite_id}")
async def delete_invite(
    team_id: str,
    invite_id: str,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Delete/revoke a team invitation.

    Requires team admin privileges.
    """
    # Check admin permission
    if not await team_service.is_team_admin(session, UUID(team_id), UUID(user.user_id)):
        raise HTTPException(status_code=403, detail="Only team admins can revoke invites")

    success = await team_service.delete_invite(session, UUID(invite_id), UUID(team_id))
    if not success:
        raise HTTPException(status_code=404, detail="Invite not found")

    await session.commit()
    return {"message": "Invite revoked successfully"}


@router.post("/accept-invite")
async def accept_invite(
    request: AcceptInviteRequest,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Accept a team invitation.

    The invite token must match the authenticated user's email.
    """
    # Check if user already has a team
    existing_team = await team_service.get_user_team(session, UUID(user.user_id))
    if existing_team:
        raise HTTPException(
            status_code=400,
            detail="You are already a member of a team. Leave your current team first.",
        )

    team = await team_service.accept_invite(session, request.token, UUID(user.user_id))
    if not team:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired invite, or email does not match.",
        )

    await session.commit()

    member_count = await team_service.get_member_count(session, team.id)

    return {
        "message": "Successfully joined the team",
        "team": {
            "id": str(team.id),
            "name": team.name,
            "member_count": member_count,
        },
    }


@router.get("/my-invites", response_model=List[PendingInviteResponse])
async def get_my_invites(
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get pending team invitations for the current user.
    """
    db_user = await user_service.get_by_id(session, user.user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    invites = await team_service.get_invites_for_email(session, db_user.email)

    return [
        PendingInviteResponse(
            id=str(invite.id),
            team_name=invite.team.name if invite.team else "Unknown",
            team_id=str(invite.team_id),
            role=invite.role,
            token=invite.token,
            expires_at=invite.expires_at.isoformat(),
        )
        for invite in invites
    ]
