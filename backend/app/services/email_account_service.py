"""
Email account service for managing multiple user email accounts.

Handles CRUD operations and encryption of sensitive credentials.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_account import EmailAccount


class EmailAccountService:
    """Service for managing multiple email accounts with encrypted credentials."""

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

    async def get_accounts(
        self, session: AsyncSession, user_id: str
    ) -> List[EmailAccount]:
        """Get all email accounts for a user."""
        result = await session.execute(
            select(EmailAccount)
            .where(EmailAccount.user_id == user_id)
            .order_by(EmailAccount.created_at)
        )
        return list(result.scalars().all())

    async def get_account(
        self, session: AsyncSession, user_id: str, account_id: str
    ) -> Optional[EmailAccount]:
        """Get a specific email account."""
        result = await session.execute(
            select(EmailAccount).where(
                EmailAccount.id == account_id,
                EmailAccount.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def get_default_account(
        self, session: AsyncSession, user_id: str
    ) -> Optional[EmailAccount]:
        """Get the default email account for a user."""
        result = await session.execute(
            select(EmailAccount).where(
                EmailAccount.user_id == user_id,
                EmailAccount.is_default == True,
                EmailAccount.is_active == True
            )
        )
        account = result.scalar_one_or_none()

        # If no default, return the first active account
        if not account:
            result = await session.execute(
                select(EmailAccount).where(
                    EmailAccount.user_id == user_id,
                    EmailAccount.is_active == True
                ).order_by(EmailAccount.created_at).limit(1)
            )
            account = result.scalar_one_or_none()

        return account

    async def create_account(
        self,
        session: AsyncSession,
        user_id: str,
        name: str,
        email: str,
        smtp_host: Optional[str] = None,
        smtp_port: int = 587,
        smtp_username: Optional[str] = None,
        smtp_password: Optional[str] = None,
        smtp_use_tls: bool = True,
        imap_host: Optional[str] = None,
        imap_port: int = 993,
        imap_username: Optional[str] = None,
        imap_password: Optional[str] = None,
        imap_use_ssl: bool = True,
        imap_mailbox: str = "INBOX",
        from_name: Optional[str] = None,
        reply_to_email: Optional[str] = None,
        is_default: bool = False,
    ) -> EmailAccount:
        """Create a new email account for a user."""
        # If this is set as default, unset other defaults
        if is_default:
            await session.execute(
                update(EmailAccount)
                .where(EmailAccount.user_id == user_id)
                .values(is_default=False)
            )

        account = EmailAccount(
            user_id=user_id,
            name=name,
            email=email,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_username=smtp_username,
            smtp_password_encrypted=self._encrypt(smtp_password) if smtp_password else None,
            smtp_use_tls=smtp_use_tls,
            imap_host=imap_host,
            imap_port=imap_port,
            imap_username=imap_username,
            imap_password_encrypted=self._encrypt(imap_password) if imap_password else None,
            imap_use_ssl=imap_use_ssl,
            imap_mailbox=imap_mailbox,
            from_name=from_name or name,
            reply_to_email=reply_to_email,
            is_default=is_default,
        )
        session.add(account)
        await session.flush()

        # If this is the first account, make it default
        accounts = await self.get_accounts(session, user_id)
        if len(accounts) == 1:
            account.is_default = True
            await session.flush()

        return account

    async def update_account(
        self,
        session: AsyncSession,
        user_id: str,
        account_id: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
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
        from_name: Optional[str] = None,
        reply_to_email: Optional[str] = None,
        is_default: Optional[bool] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[EmailAccount]:
        """Update an email account."""
        account = await self.get_account(session, user_id, account_id)
        if not account:
            return None

        # If setting as default, unset other defaults
        if is_default:
            await session.execute(
                update(EmailAccount)
                .where(EmailAccount.user_id == user_id, EmailAccount.id != account_id)
                .values(is_default=False)
            )

        if name is not None:
            account.name = name
        if email is not None:
            account.email = email
        if smtp_host is not None:
            account.smtp_host = smtp_host
        if smtp_port is not None:
            account.smtp_port = smtp_port
        if smtp_username is not None:
            account.smtp_username = smtp_username
        if smtp_password is not None:
            account.smtp_password_encrypted = self._encrypt(smtp_password)
            account.smtp_verified = False  # Re-verify after password change
        if smtp_use_tls is not None:
            account.smtp_use_tls = smtp_use_tls
        if imap_host is not None:
            account.imap_host = imap_host
        if imap_port is not None:
            account.imap_port = imap_port
        if imap_username is not None:
            account.imap_username = imap_username
        if imap_password is not None:
            account.imap_password_encrypted = self._encrypt(imap_password)
            account.imap_verified = False  # Re-verify after password change
        if imap_use_ssl is not None:
            account.imap_use_ssl = imap_use_ssl
        if imap_mailbox is not None:
            account.imap_mailbox = imap_mailbox
        if from_name is not None:
            account.from_name = from_name
        if reply_to_email is not None:
            account.reply_to_email = reply_to_email
        if is_default is not None:
            account.is_default = is_default
        if is_active is not None:
            account.is_active = is_active

        account.updated_at = datetime.utcnow()
        await session.flush()
        return account

    async def delete_account(
        self, session: AsyncSession, user_id: str, account_id: str
    ) -> bool:
        """Delete an email account."""
        account = await self.get_account(session, user_id, account_id)
        if not account:
            return False

        was_default = account.is_default
        await session.delete(account)
        await session.flush()

        # If we deleted the default, set a new default
        if was_default:
            accounts = await self.get_accounts(session, user_id)
            if accounts:
                accounts[0].is_default = True
                await session.flush()

        return True

    async def test_smtp_connection(
        self, session: AsyncSession, user_id: str, account_id: str
    ) -> tuple[bool, str]:
        """Test SMTP connection for an account."""
        account = await self.get_account(session, user_id, account_id)
        if not account:
            return False, "Account not found"

        if not account.smtp_host or not account.smtp_username:
            return False, "SMTP settings incomplete"

        try:
            import smtplib
            import ssl

            password = self._decrypt(account.smtp_password_encrypted) if account.smtp_password_encrypted else None
            context = ssl.create_default_context()

            if account.smtp_use_tls:
                server = smtplib.SMTP(account.smtp_host, account.smtp_port, timeout=10)
                server.starttls(context=context)
            else:
                server = smtplib.SMTP_SSL(account.smtp_host, account.smtp_port, context=context, timeout=10)

            if password:
                server.login(account.smtp_username, password)

            server.quit()

            account.smtp_verified = True
            account.smtp_verified_at = datetime.utcnow()
            await session.flush()

            return True, "SMTP connection successful"

        except smtplib.SMTPAuthenticationError:
            return False, "Authentication failed - check username and password"
        except smtplib.SMTPConnectError:
            return False, f"Could not connect to {account.smtp_host}:{account.smtp_port}"
        except Exception as e:
            return False, f"Connection error: {str(e)}"

    async def test_imap_connection(
        self, session: AsyncSession, user_id: str, account_id: str
    ) -> tuple[bool, str]:
        """Test IMAP connection for an account."""
        account = await self.get_account(session, user_id, account_id)
        if not account:
            return False, "Account not found"

        if not account.imap_host or not account.imap_username:
            return False, "IMAP settings incomplete"

        try:
            import imaplib

            password = self._decrypt(account.imap_password_encrypted) if account.imap_password_encrypted else None

            if account.imap_use_ssl:
                server = imaplib.IMAP4_SSL(account.imap_host, account.imap_port)
            else:
                server = imaplib.IMAP4(account.imap_host, account.imap_port)

            if password:
                server.login(account.imap_username, password)

            server.select(account.imap_mailbox or "INBOX")
            server.logout()

            account.imap_verified = True
            account.imap_verified_at = datetime.utcnow()
            await session.flush()

            return True, "IMAP connection successful"

        except imaplib.IMAP4.error as e:
            return False, f"IMAP error: {str(e)}"
        except Exception as e:
            return False, f"Connection error: {str(e)}"

    def get_decrypted_smtp_password(self, account: EmailAccount) -> Optional[str]:
        """Get decrypted SMTP password."""
        if account.smtp_password_encrypted:
            return self._decrypt(account.smtp_password_encrypted)
        return None

    def get_decrypted_imap_password(self, account: EmailAccount) -> Optional[str]:
        """Get decrypted IMAP password."""
        if account.imap_password_encrypted:
            return self._decrypt(account.imap_password_encrypted)
        return None


# Singleton instance
email_account_service = EmailAccountService()
