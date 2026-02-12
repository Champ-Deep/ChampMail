"""
Email settings service for managing user SMTP/IMAP configurations.

Handles encryption of sensitive credentials using Fernet symmetric encryption.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_settings import EmailSettings


class EmailSettingsService:
    """Service for managing email settings with encrypted credentials."""

    def __init__(self):
        # Get or generate encryption key from environment
        key = os.environ.get("EMAIL_ENCRYPTION_KEY")
        if not key:
            # Generate a key for development (in production, set this in .env)
            key = Fernet.generate_key().decode()
            os.environ["EMAIL_ENCRYPTION_KEY"] = key
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def _encrypt(self, value: str) -> str:
        """Encrypt a string value."""
        return self._fernet.encrypt(value.encode()).decode()

    def _decrypt(self, value: str) -> str:
        """Decrypt an encrypted string."""
        return self._fernet.decrypt(value.encode()).decode()

    async def get_settings(
        self, session: AsyncSession, user_id: str
    ) -> Optional[EmailSettings]:
        """Get email settings for a user."""
        result = await session.execute(
            select(EmailSettings).where(EmailSettings.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create_or_update_settings(
        self,
        session: AsyncSession,
        user_id: str,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_username: Optional[str] = None,
        smtp_password: Optional[str] = None,
        smtp_use_tls: Optional[bool] = None,
        imap_host: Optional[str] = None,
        imap_port: Optional[int] = None,
        imap_username: Optional[str] = None,
        imap_password: Optional[str] = None,
        imap_use_ssl: Optional[bool] = None,
        imap_mailbox: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to_email: Optional[str] = None,
    ) -> EmailSettings:
        """Create or update email settings for a user."""
        settings = await self.get_settings(session, user_id)

        if not settings:
            settings = EmailSettings(user_id=user_id)
            session.add(settings)

        # Update SMTP settings
        if smtp_host is not None:
            settings.smtp_host = smtp_host
        if smtp_port is not None:
            settings.smtp_port = smtp_port
        if smtp_username is not None:
            settings.smtp_username = smtp_username
        if smtp_password is not None:
            settings.smtp_password_encrypted = self._encrypt(smtp_password)
        if smtp_use_tls is not None:
            settings.smtp_use_tls = smtp_use_tls

        # Update IMAP settings
        if imap_host is not None:
            settings.imap_host = imap_host
        if imap_port is not None:
            settings.imap_port = imap_port
        if imap_username is not None:
            settings.imap_username = imap_username
        if imap_password is not None:
            settings.imap_password_encrypted = self._encrypt(imap_password)
        if imap_use_ssl is not None:
            settings.imap_use_ssl = imap_use_ssl
        if imap_mailbox is not None:
            settings.imap_mailbox = imap_mailbox

        # Update sender identity
        if from_email is not None:
            settings.from_email = from_email
        if from_name is not None:
            settings.from_name = from_name
        if reply_to_email is not None:
            settings.reply_to_email = reply_to_email

        await session.flush()
        return settings

    async def test_smtp_connection(
        self, session: AsyncSession, user_id: str
    ) -> tuple[bool, str]:
        """Test SMTP connection with user's settings."""
        settings = await self.get_settings(session, user_id)
        if not settings:
            return False, "No email settings configured"

        if not settings.smtp_host or not settings.smtp_username:
            return False, "SMTP settings incomplete"

        try:
            import smtplib
            import ssl

            # Decrypt password
            password = self._decrypt(settings.smtp_password_encrypted) if settings.smtp_password_encrypted else None

            context = ssl.create_default_context()

            if settings.smtp_use_tls:
                server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
                server.starttls(context=context)
            else:
                server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context, timeout=10)

            if password:
                server.login(settings.smtp_username, password)

            server.quit()

            # Mark as verified
            settings.smtp_verified = True
            settings.smtp_verified_at = datetime.utcnow()
            await session.flush()

            return True, "SMTP connection successful"

        except smtplib.SMTPAuthenticationError:
            return False, "Authentication failed - check username and password"
        except smtplib.SMTPConnectError:
            return False, f"Could not connect to {settings.smtp_host}:{settings.smtp_port}"
        except Exception as e:
            return False, f"Connection error: {str(e)}"

    async def test_imap_connection(
        self, session: AsyncSession, user_id: str
    ) -> tuple[bool, str]:
        """Test IMAP connection with user's settings."""
        settings = await self.get_settings(session, user_id)
        if not settings:
            return False, "No email settings configured"

        if not settings.imap_host or not settings.imap_username:
            return False, "IMAP settings incomplete"

        try:
            import imaplib

            # Decrypt password
            password = self._decrypt(settings.imap_password_encrypted) if settings.imap_password_encrypted else None

            if settings.imap_use_ssl:
                server = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
            else:
                server = imaplib.IMAP4(settings.imap_host, settings.imap_port)

            if password:
                server.login(settings.imap_username, password)

            # Try to select the mailbox
            server.select(settings.imap_mailbox or "INBOX")
            server.logout()

            # Mark as verified
            settings.imap_verified = True
            settings.imap_verified_at = datetime.utcnow()
            await session.flush()

            return True, "IMAP connection successful"

        except imaplib.IMAP4.error as e:
            return False, f"IMAP error: {str(e)}"
        except Exception as e:
            return False, f"Connection error: {str(e)}"

    def get_decrypted_smtp_password(self, settings: EmailSettings) -> Optional[str]:
        """Get decrypted SMTP password (for sending emails)."""
        if settings.smtp_password_encrypted:
            return self._decrypt(settings.smtp_password_encrypted)
        return None

    def get_decrypted_imap_password(self, settings: EmailSettings) -> Optional[str]:
        """Get decrypted IMAP password (for reply detection)."""
        if settings.imap_password_encrypted:
            return self._decrypt(settings.imap_password_encrypted)
        return None


# Singleton instance
email_settings_service = EmailSettingsService()
