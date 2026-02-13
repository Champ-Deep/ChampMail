"""
Admin and data team authentication and authorization.
Provides decorators and dependencies for role-based access control.
"""

from fastapi import Depends, HTTPException, status
from app.core.security import require_auth, TokenData


def require_data_team_or_admin(
    user: TokenData = Depends(require_auth)
) -> TokenData:
    """
    Dependency that requires user to have data_team or admin role.

    Args:
        user: Authenticated user from JWT token

    Returns:
        TokenData if user has required role

    Raises:
        HTTPException: 403 if user doesn't have required role
    """
    if user.role not in ["data_team", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Data team or admin access required. Your role: " + (user.role or "user")
        )
    return user


def require_admin(
    user: TokenData = Depends(require_auth)
) -> TokenData:
    """
    Dependency that requires user to have admin role.

    Args:
        user: Authenticated user from JWT token

    Returns:
        TokenData if user is admin

    Raises:
        HTTPException: 403 if user is not admin
    """
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required. Your role: " + (user.role or "user")
        )
    return user


def require_team_admin(
    user: TokenData = Depends(require_auth)
) -> TokenData:
    """
    Dependency that requires user to be team_admin or admin.

    Args:
        user: Authenticated user from JWT token

    Returns:
        TokenData if user is team_admin or admin

    Raises:
        HTTPException: 403 if user doesn't have required role
    """
    if user.role not in ["team_admin", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Team admin or admin access required. Your role: " + (user.role or "user")
        )
    return user


# Role hierarchy helper functions

def is_admin(user: TokenData) -> bool:
    """Check if user is admin."""
    return user.role == "admin"


def is_data_team(user: TokenData) -> bool:
    """Check if user is data_team."""
    return user.role == "data_team"


def is_team_admin(user: TokenData) -> bool:
    """Check if user is team_admin."""
    return user.role == "team_admin"


def can_manage_team(user: TokenData) -> bool:
    """Check if user can manage team (admin or team_admin)."""
    return user.role in ["admin", "team_admin"]


def can_upload_prospects(user: TokenData) -> bool:
    """Check if user can upload prospect lists (data_team or admin)."""
    return user.role in ["data_team", "admin"]


def can_access_admin_portal(user: TokenData) -> bool:
    """Check if user can access admin portal."""
    return user.role in ["data_team", "admin"]
