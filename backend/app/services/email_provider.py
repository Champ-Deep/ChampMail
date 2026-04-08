"""
Email provider abstraction layer.

Supports multiple email backends:
- StalwartSMTPProvider: Send via Stalwart's SMTP submission port
- IMAPReplyDetector: Monitor for incoming replies via IMAP
"""

from __future__ import annotations

import asyncio
import email
import logging
import smtplib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    """Email message structure."""
    to: str
    subject: str
    html_body: str
    text_body: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[str] = None
    tracking_id: Optional[str] = None
    headers: Optional[dict[str, str]] = None


@dataclass
class SendResult:
    """Result of sending an email."""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    tracking_id: Optional[str] = None


@dataclass
class IncomingMessage:
    """Incoming email message from IMAP."""
    message_id: str
    from_email: str
    from_name: Optional[str]
    subject: str
    body: str
    received_at: datetime
    in_reply_to: Optional[str] = None
    references: Optional[str] = None


class EmailProvider(ABC):
    """Abstract base class for email providers."""

    @abstractmethod
    async def send_email(self, message: EmailMessage) -> SendResult:
        """Send an email message."""
        ...

    @abstractmethod
    async def verify_connection(self) -> bool:
        """Verify the email provider connection."""
        ...


class StalwartSMTPProvider(EmailProvider):
    """
    Send emails via Stalwart's SMTP submission port (587).

    This provider uses standard SMTP with STARTTLS for secure email delivery.
    """

    def __init__(
        self,
        host: str = None,
        port: int = None,
        username: str = None,
        password: str = None,
        use_tls: bool = True,
        use_ssl: bool = False,
        from_email: str = None,
        from_name: str = None,
    ):
        self.host = host or getattr(settings, 'smtp_host', 'localhost')
        self.port = port or getattr(settings, 'smtp_port', 587)
        self.username = username or getattr(settings, 'smtp_username', '')
        self.password = password or getattr(settings, 'smtp_password', '')
        self.use_tls = use_tls
        # Auto-detect SSL mode for port 465, or accept explicit flag
        self.use_ssl = use_ssl or self.port == 465
        self.from_email = from_email or getattr(settings, 'mail_from_email', 'noreply@localhost')
        self.from_name = from_name or getattr(settings, 'mail_from_name', 'ChampMail')

    async def send_email(self, message: EmailMessage) -> SendResult:
        """Send an email via SMTP."""
        try:
            # Build the email
            msg = MIMEMultipart('alternative')
            msg['Subject'] = message.subject
            msg['From'] = f"{message.from_name or self.from_name} <{message.from_email or self.from_email}>"
            msg['To'] = message.to

            if message.reply_to:
                msg['Reply-To'] = message.reply_to

            # Add tracking header if provided
            if message.tracking_id:
                msg['X-ChampMail-Tracking-ID'] = message.tracking_id

            # Add custom headers
            if message.headers:
                for key, value in message.headers.items():
                    msg[key] = value

            # Attach text and HTML parts
            if message.text_body:
                text_part = MIMEText(message.text_body, 'plain', 'utf-8')
                msg.attach(text_part)

            html_part = MIMEText(message.html_body, 'html', 'utf-8')
            msg.attach(html_part)

            # Send via SMTP (sync operation wrapped in executor)
            loop = asyncio.get_event_loop()
            message_id = await loop.run_in_executor(
                None,
                self._send_sync,
                msg,
                message.to,
            )

            return SendResult(
                success=True,
                message_id=message_id,
                tracking_id=message.tracking_id,
            )

        except Exception as e:
            return SendResult(
                success=False,
                error=str(e),
                tracking_id=message.tracking_id,
            )

    def _send_sync(self, msg: MIMEMultipart, to_addr: str) -> str:
        """Synchronous SMTP send."""
        if self.use_ssl:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=30) as server:
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.send_message(msg)
                return msg['Message-ID'] or f"<{msg['Subject'][:20]}@champmail>"
        else:
            with smtplib.SMTP(self.host, self.port, timeout=30) as server:
                if self.use_tls:
                    server.starttls()
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.send_message(msg)
                return msg['Message-ID'] or f"<{msg['Subject'][:20]}@champmail>"

    async def verify_connection(self) -> bool:
        """Verify SMTP connection."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._verify_sync)
        except Exception:
            return False

    def _verify_sync(self) -> bool:
        """Synchronous connection verification."""
        if self.use_ssl:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=10) as server:
                if self.username and self.password:
                    server.login(self.username, self.password)
                return True
        else:
            with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                if self.use_tls:
                    server.starttls()
                if self.username and self.password:
                    server.login(self.username, self.password)
                return True


class IMAPReplyDetector:
    """
    Monitor Stalwart IMAP for incoming replies.

    Polls IMAP mailbox for new messages and matches them to
    existing prospects/conversations using headers.
    """

    def __init__(
        self,
        host: str = None,
        port: int = None,
        username: str = None,
        password: str = None,
        use_ssl: bool = True,
        mailbox: str = 'INBOX',
    ):
        self.host = host or getattr(settings, 'imap_host', 'localhost')
        self.port = port or getattr(settings, 'imap_port', 993)
        self.username = username or getattr(settings, 'imap_username', '')
        self.password = password or getattr(settings, 'imap_password', '')
        self.use_ssl = use_ssl
        self.mailbox = mailbox

    async def check_new_messages(self, since_uid: int = 0) -> list[IncomingMessage]:
        """
        Fetch new messages from IMAP.

        Args:
            since_uid: Only fetch messages with UID greater than this

        Returns:
            List of incoming messages

        Raises:
            Exception: Re-raises IMAP errors so callers can distinguish
                       "no messages" from "connection failed".
        """
        import imaplib

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._fetch_messages_sync,
            since_uid,
        )

    def _fetch_messages_sync(self, since_uid: int) -> list[IncomingMessage]:
        """Synchronous IMAP fetch."""
        import imaplib
        from email.header import decode_header as _decode_header
        from email.utils import parsedate_to_datetime

        messages = []

        if self.use_ssl:
            imap = imaplib.IMAP4_SSL(self.host, self.port)
        else:
            imap = imaplib.IMAP4(self.host, self.port)

        try:
            imap.login(self.username, self.password)
            imap.select(self.mailbox, readonly=True)

            # Always use UID-based search for consistency
            if since_uid > 0:
                status, data = imap.uid('search', None, f'(UID {since_uid}:*)')
            else:
                status, data = imap.uid('search', None, 'ALL')

            if status != 'OK' or not data[0]:
                return messages

            message_ids = data[0].split()

            for msg_uid in message_ids[-100:]:  # Limit to last 100
                status, msg_data = imap.uid('fetch', msg_uid, '(RFC822)')
                if status != 'OK' or not msg_data or not msg_data[0]:
                    continue

                raw_email = msg_data[0][1]
                email_msg = email.message_from_bytes(raw_email)

                # Extract body — try text/plain first, then text/html
                body = ""
                if email_msg.is_multipart():
                    for part in email_msg.walk():
                        ct = part.get_content_type()
                        if ct == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = payload.decode('utf-8', errors='ignore')
                            break
                        elif ct == "text/html" and not body:
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = payload.decode('utf-8', errors='ignore')
                else:
                    payload = email_msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode('utf-8', errors='ignore')

                def _decode_hdr(raw_val):
                    if not raw_val:
                        return ''
                    decoded_parts = _decode_header(raw_val)
                    result = []
                    for part_val, charset in decoded_parts:
                        if isinstance(part_val, bytes):
                            result.append(part_val.decode(charset or 'utf-8', errors='ignore'))
                        else:
                            result.append(part_val)
                    return ' '.join(result)

                subject = _decode_hdr(email_msg.get('Subject', ''))

                # Parse from header
                from_header = _decode_hdr(email_msg.get('From', ''))
                from_name = None
                from_email_addr = from_header
                if '<' in from_header:
                    parts = from_header.split('<')
                    from_name = parts[0].strip().strip('"')
                    from_email_addr = parts[1].rstrip('>')

                # Parse actual Date header instead of using datetime.now()
                received_at = datetime.now()
                date_hdr = email_msg.get('Date')
                if date_hdr:
                    try:
                        received_at = parsedate_to_datetime(date_hdr)
                        # Convert to naive datetime for consistency
                        if received_at.tzinfo:
                            received_at = received_at.replace(tzinfo=None)
                    except (ValueError, TypeError):
                        pass

                messages.append(IncomingMessage(
                    message_id=email_msg.get('Message-ID', ''),
                    from_email=from_email_addr,
                    from_name=from_name,
                    subject=subject,
                    body=body,
                    received_at=received_at,
                    in_reply_to=email_msg.get('In-Reply-To'),
                    references=email_msg.get('References'),
                ))

        finally:
            try:
                imap.logout()
            except Exception:
                pass

        return messages

    async def verify_connection(self) -> bool:
        """Verify IMAP connection."""
        try:
            import imaplib

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._verify_sync)
        except Exception:
            return False

    def _verify_sync(self) -> bool:
        """Synchronous IMAP verification."""
        import imaplib

        if self.use_ssl:
            imap = imaplib.IMAP4_SSL(self.host, self.port)
        else:
            imap = imaplib.IMAP4(self.host, self.port)

        try:
            imap.login(self.username, self.password)
            imap.select(self.mailbox)
            return True
        finally:
            imap.logout()


# Global provider instance (initialized on demand)
_email_provider: Optional[EmailProvider] = None


def get_email_provider() -> EmailProvider:
    """Get the configured email provider.

    Reads directly from os.environ so CLI config changes
    (via apply_to_runtime) are picked up immediately.
    """
    import os
    host = os.environ.get('SMTP_HOST') or getattr(settings, 'smtp_host', 'localhost')
    port = int(os.environ.get('SMTP_PORT') or getattr(settings, 'smtp_port', 587))
    username = os.environ.get('SMTP_USERNAME') or getattr(settings, 'smtp_username', '')
    password = os.environ.get('SMTP_PASSWORD') or getattr(settings, 'smtp_password', '')
    use_tls = os.environ.get('SMTP_USE_TLS', '').lower() not in ('false', '0', 'no', '')
    use_ssl = os.environ.get('SMTP_USE_SSL', '').lower() in ('true', '1', 'yes') or port == 465
    from_email = os.environ.get('MAIL_FROM_EMAIL') or getattr(settings, 'mail_from_email', 'noreply@localhost')
    from_name = os.environ.get('MAIL_FROM_NAME') or getattr(settings, 'mail_from_name', 'ChampMail')

    return StalwartSMTPProvider(
        host=host, port=port, username=username, password=password,
        use_tls=use_tls, use_ssl=use_ssl,
        from_email=from_email, from_name=from_name,
    )


def get_reply_detector() -> IMAPReplyDetector:
    """Get the IMAP reply detector.

    Reads directly from os.environ so CLI config changes are picked up.
    """
    import os
    return IMAPReplyDetector(
        host=os.environ.get('IMAP_HOST') or getattr(settings, 'imap_host', 'localhost'),
        port=int(os.environ.get('IMAP_PORT') or getattr(settings, 'imap_port', 993)),
        username=os.environ.get('IMAP_USERNAME') or getattr(settings, 'imap_username', ''),
        password=os.environ.get('IMAP_PASSWORD') or getattr(settings, 'imap_password', ''),
        use_ssl=os.environ.get('IMAP_USE_SSL', 'true').lower() in ('true', '1', 'yes'),
        mailbox=os.environ.get('IMAP_MAILBOX') or getattr(settings, 'imap_mailbox', 'INBOX'),
    )
