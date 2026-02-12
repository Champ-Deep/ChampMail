"""
Email accounts API endpoints for managing multiple email accounts per user.
"""

from __future__ import annotations

from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_db_session
from app.core.security import require_auth, TokenData
from app.services.email_account_service import email_account_service

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================

class EmailAccountCreate(BaseModel):
    """Request to create a new email account."""
    name: str
    email: EmailStr
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: bool = True
    imap_host: Optional[str] = None
    imap_port: int = 993
    imap_username: Optional[str] = None
    imap_password: Optional[str] = None
    imap_use_ssl: bool = True
    imap_mailbox: str = "INBOX"
    from_name: Optional[str] = None
    reply_to_email: Optional[str] = None
    is_default: bool = False


class EmailAccountUpdate(BaseModel):
    """Request to update an email account."""
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: Optional[bool] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    imap_username: Optional[str] = None
    imap_password: Optional[str] = None
    imap_use_ssl: Optional[bool] = None
    imap_mailbox: Optional[str] = None
    from_name: Optional[str] = None
    reply_to_email: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class EmailAccountResponse(BaseModel):
    """Response for an email account."""
    id: str
    name: str
    email: str
    is_default: bool
    is_active: bool
    smtp_host: Optional[str]
    smtp_port: int
    smtp_username: Optional[str]
    smtp_use_tls: bool
    smtp_verified: bool
    smtp_verified_at: Optional[str]
    smtp_has_password: bool
    imap_host: Optional[str]
    imap_port: int
    imap_username: Optional[str]
    imap_use_ssl: bool
    imap_mailbox: Optional[str]
    imap_verified: bool
    imap_verified_at: Optional[str]
    imap_has_password: bool
    from_name: Optional[str]
    reply_to_email: Optional[str]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class TestConnectionResponse(BaseModel):
    """Response from testing a connection."""
    success: bool
    message: str


# ============================================================================
# Helper Functions
# ============================================================================

def account_to_response(account) -> EmailAccountResponse:
    """Convert an EmailAccount to response format."""
    return EmailAccountResponse(
        id=str(account.id),
        name=account.name,
        email=account.email,
        is_default=account.is_default,
        is_active=account.is_active,
        smtp_host=account.smtp_host,
        smtp_port=account.smtp_port,
        smtp_username=account.smtp_username,
        smtp_use_tls=account.smtp_use_tls,
        smtp_verified=account.smtp_verified,
        smtp_verified_at=account.smtp_verified_at.isoformat() if account.smtp_verified_at else None,
        smtp_has_password=bool(account.smtp_password_encrypted),
        imap_host=account.imap_host,
        imap_port=account.imap_port,
        imap_username=account.imap_username,
        imap_use_ssl=account.imap_use_ssl,
        imap_mailbox=account.imap_mailbox,
        imap_verified=account.imap_verified,
        imap_verified_at=account.imap_verified_at.isoformat() if account.imap_verified_at else None,
        imap_has_password=bool(account.imap_password_encrypted),
        from_name=account.from_name,
        reply_to_email=account.reply_to_email,
        created_at=account.created_at.isoformat() if account.created_at else None,
        updated_at=account.updated_at.isoformat() if account.updated_at else None,
    )


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=List[EmailAccountResponse])
async def list_accounts(
    current_user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """List all email accounts for the current user."""
    accounts = await email_account_service.get_accounts(session, current_user.user_id)
    return [account_to_response(acc) for acc in accounts]


@router.get("/default", response_model=Optional[EmailAccountResponse])
async def get_default_account(
    current_user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Get the default email account for the current user."""
    account = await email_account_service.get_default_account(session, current_user.user_id)
    if not account:
        return None
    return account_to_response(account)


@router.get("/{account_id}", response_model=EmailAccountResponse)
async def get_account(
    account_id: UUID,
    current_user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Get a specific email account."""
    account = await email_account_service.get_account(session, current_user.user_id, str(account_id))
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account_to_response(account)


@router.post("", response_model=EmailAccountResponse)
async def create_account(
    data: EmailAccountCreate,
    current_user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Create a new email account."""
    account = await email_account_service.create_account(
        session=session,
        user_id=current_user.user_id,
        name=data.name,
        email=data.email,
        smtp_host=data.smtp_host,
        smtp_port=data.smtp_port,
        smtp_username=data.smtp_username,
        smtp_password=data.smtp_password,
        smtp_use_tls=data.smtp_use_tls,
        imap_host=data.imap_host,
        imap_port=data.imap_port,
        imap_username=data.imap_username,
        imap_password=data.imap_password,
        imap_use_ssl=data.imap_use_ssl,
        imap_mailbox=data.imap_mailbox,
        from_name=data.from_name,
        reply_to_email=data.reply_to_email,
        is_default=data.is_default,
    )
    await session.commit()
    return account_to_response(account)


@router.put("/{account_id}", response_model=EmailAccountResponse)
async def update_account(
    account_id: UUID,
    data: EmailAccountUpdate,
    current_user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Update an email account."""
    account = await email_account_service.update_account(
        session=session,
        user_id=current_user.user_id,
        account_id=str(account_id),
        name=data.name,
        email=data.email,
        smtp_host=data.smtp_host,
        smtp_port=data.smtp_port,
        smtp_username=data.smtp_username,
        smtp_password=data.smtp_password,
        smtp_use_tls=data.smtp_use_tls,
        imap_host=data.imap_host,
        imap_port=data.imap_port,
        imap_username=data.imap_username,
        imap_password=data.imap_password,
        imap_use_ssl=data.imap_use_ssl,
        imap_mailbox=data.imap_mailbox,
        from_name=data.from_name,
        reply_to_email=data.reply_to_email,
        is_default=data.is_default,
        is_active=data.is_active,
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    await session.commit()
    return account_to_response(account)


@router.delete("/{account_id}")
async def delete_account(
    account_id: UUID,
    current_user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Delete an email account."""
    deleted = await email_account_service.delete_account(session, current_user.user_id, str(account_id))
    if not deleted:
        raise HTTPException(status_code=404, detail="Account not found")
    await session.commit()
    return {"success": True, "message": "Account deleted"}


@router.post("/{account_id}/test-smtp", response_model=TestConnectionResponse)
async def test_smtp(
    account_id: UUID,
    current_user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Test SMTP connection for an account."""
    success, message = await email_account_service.test_smtp_connection(
        session, current_user.user_id, str(account_id)
    )
    if success:
        await session.commit()
    return TestConnectionResponse(success=success, message=message)


@router.post("/{account_id}/test-imap", response_model=TestConnectionResponse)
async def test_imap(
    account_id: UUID,
    current_user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Test IMAP connection for an account."""
    success, message = await email_account_service.test_imap_connection(
        session, current_user.user_id, str(account_id)
    )
    if success:
        await session.commit()
    return TestConnectionResponse(success=success, message=message)


@router.post("/{account_id}/set-default", response_model=EmailAccountResponse)
async def set_default(
    account_id: UUID,
    current_user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Set an account as the default."""
    account = await email_account_service.update_account(
        session=session,
        user_id=current_user.user_id,
        account_id=str(account_id),
        is_default=True,
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    await session.commit()
    return account_to_response(account)
