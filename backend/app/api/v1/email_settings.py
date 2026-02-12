"""
Email settings API endpoints.

Allows users to configure their SMTP/IMAP credentials for sending emails
and detecting replies.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenData, require_auth
from app.db.postgres import get_db_session
from app.services.email_settings_service import email_settings_service

router = APIRouter(prefix="/settings", tags=["Email Settings"])


# ============================================================================
# Request/Response Models
# ============================================================================


class SMTPSettings(BaseModel):
    """SMTP configuration settings."""
    host: Optional[str] = Field(None, description="SMTP server hostname")
    port: Optional[int] = Field(587, description="SMTP port (587 for TLS, 465 for SSL)")
    username: Optional[str] = Field(None, description="SMTP username")
    password: Optional[str] = Field(None, description="SMTP password (will be encrypted)")
    use_tls: Optional[bool] = Field(True, description="Use STARTTLS")


class IMAPSettings(BaseModel):
    """IMAP configuration settings."""
    host: Optional[str] = Field(None, description="IMAP server hostname")
    port: Optional[int] = Field(993, description="IMAP port (993 for SSL)")
    username: Optional[str] = Field(None, description="IMAP username")
    password: Optional[str] = Field(None, description="IMAP password (will be encrypted)")
    use_ssl: Optional[bool] = Field(True, description="Use SSL")
    mailbox: Optional[str] = Field("INBOX", description="Mailbox to monitor")


class SenderIdentity(BaseModel):
    """Email sender identity settings."""
    from_email: Optional[EmailStr] = Field(None, description="From email address")
    from_name: Optional[str] = Field(None, description="From name")
    reply_to_email: Optional[EmailStr] = Field(None, description="Reply-to address")


class EmailSettingsUpdate(BaseModel):
    """Request to update email settings."""
    smtp: Optional[SMTPSettings] = None
    imap: Optional[IMAPSettings] = None
    sender: Optional[SenderIdentity] = None


class EmailSettingsResponse(BaseModel):
    """Email settings response (passwords are not returned)."""
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_has_password: bool = False
    smtp_use_tls: bool = True
    smtp_verified: bool = False
    smtp_verified_at: Optional[str] = None

    imap_host: Optional[str] = None
    imap_port: int = 993
    imap_username: Optional[str] = None
    imap_has_password: bool = False
    imap_use_ssl: bool = True
    imap_mailbox: str = "INBOX"
    imap_verified: bool = False
    imap_verified_at: Optional[str] = None

    from_email: Optional[str] = None
    from_name: Optional[str] = None
    reply_to_email: Optional[str] = None


class TestConnectionResponse(BaseModel):
    """Response for connection test."""
    success: bool
    message: str


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/email", response_model=EmailSettingsResponse)
async def get_email_settings(
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Get current email settings.

    Returns all settings except passwords (shows whether passwords are set).
    """
    settings = await email_settings_service.get_settings(session, user.user_id)

    if not settings:
        return EmailSettingsResponse()

    return EmailSettingsResponse(
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port or 587,
        smtp_username=settings.smtp_username,
        smtp_has_password=bool(settings.smtp_password_encrypted),
        smtp_use_tls=settings.smtp_use_tls if settings.smtp_use_tls is not None else True,
        smtp_verified=settings.smtp_verified or False,
        smtp_verified_at=settings.smtp_verified_at.isoformat() if settings.smtp_verified_at else None,
        imap_host=settings.imap_host,
        imap_port=settings.imap_port or 993,
        imap_username=settings.imap_username,
        imap_has_password=bool(settings.imap_password_encrypted),
        imap_use_ssl=settings.imap_use_ssl if settings.imap_use_ssl is not None else True,
        imap_mailbox=settings.imap_mailbox or "INBOX",
        imap_verified=settings.imap_verified or False,
        imap_verified_at=settings.imap_verified_at.isoformat() if settings.imap_verified_at else None,
        from_email=settings.from_email,
        from_name=settings.from_name,
        reply_to_email=settings.reply_to_email,
    )


@router.put("/email", response_model=EmailSettingsResponse)
async def update_email_settings(
    request: EmailSettingsUpdate,
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Update email settings.

    Only provided fields will be updated. Passwords are encrypted at rest.
    """
    smtp = request.smtp or SMTPSettings()
    imap = request.imap or IMAPSettings()
    sender = request.sender or SenderIdentity()

    settings = await email_settings_service.create_or_update_settings(
        session,
        user.user_id,
        smtp_host=smtp.host,
        smtp_port=smtp.port,
        smtp_username=smtp.username,
        smtp_password=smtp.password,
        smtp_use_tls=smtp.use_tls,
        imap_host=imap.host,
        imap_port=imap.port,
        imap_username=imap.username,
        imap_password=imap.password,
        imap_use_ssl=imap.use_ssl,
        imap_mailbox=imap.mailbox,
        from_email=sender.from_email,
        from_name=sender.from_name,
        reply_to_email=sender.reply_to_email,
    )
    await session.commit()

    return EmailSettingsResponse(
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port or 587,
        smtp_username=settings.smtp_username,
        smtp_has_password=bool(settings.smtp_password_encrypted),
        smtp_use_tls=settings.smtp_use_tls if settings.smtp_use_tls is not None else True,
        smtp_verified=settings.smtp_verified or False,
        smtp_verified_at=settings.smtp_verified_at.isoformat() if settings.smtp_verified_at else None,
        imap_host=settings.imap_host,
        imap_port=settings.imap_port or 993,
        imap_username=settings.imap_username,
        imap_has_password=bool(settings.imap_password_encrypted),
        imap_use_ssl=settings.imap_use_ssl if settings.imap_use_ssl is not None else True,
        imap_mailbox=settings.imap_mailbox or "INBOX",
        imap_verified=settings.imap_verified or False,
        imap_verified_at=settings.imap_verified_at.isoformat() if settings.imap_verified_at else None,
        from_email=settings.from_email,
        from_name=settings.from_name,
        reply_to_email=settings.reply_to_email,
    )


@router.post("/email/test-smtp", response_model=TestConnectionResponse)
async def test_smtp_connection(
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Test SMTP connection with current settings.

    Attempts to connect and authenticate with the configured SMTP server.
    On success, marks the SMTP settings as verified.
    """
    success, message = await email_settings_service.test_smtp_connection(session, user.user_id)
    await session.commit()
    return TestConnectionResponse(success=success, message=message)


@router.post("/email/test-imap", response_model=TestConnectionResponse)
async def test_imap_connection(
    user: TokenData = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Test IMAP connection with current settings.

    Attempts to connect, authenticate, and select the mailbox.
    On success, marks the IMAP settings as verified.
    """
    success, message = await email_settings_service.test_imap_connection(session, user.user_id)
    await session.commit()
    return TestConnectionResponse(success=success, message=message)
