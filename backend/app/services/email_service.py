"""
Email service for sending and receiving emails via SMTP/IMAP.

This service is called by n8n workflows via webhooks to send/receive emails
using the user's configured SMTP/IMAP credentials from the app.
"""

from __future__ import annotations

import logging
import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
import ssl
from datetime import datetime
from typing import Optional, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_settings import EmailSettings
from app.models.email_account import EmailAccount
from app.services.email_settings_service import email_settings_service
from app.services.email_account_service import email_account_service

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending and receiving emails."""

    async def send_email(
        self,
        session: AsyncSession,
        user_id: str,
        to_email: str,
        subject: str,
        body: str,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        html_body: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Send an email using the user's SMTP settings.

        Args:
            session: Database session
            user_id: User ID whose SMTP settings to use
            to_email: Recipient email address
            subject: Email subject
            body: Plain text email body
            from_email: Override from email (optional)
            from_name: Override from name (optional)
            reply_to: Reply-to address (optional)
            html_body: HTML version of email body (optional)

        Returns:
            Dict with status and message
        """
        logger.info("Sending email to %s for user %s", to_email, user_id)

        # Try to get email account first (new multi-account system)
        email_account = await email_account_service.get_default_account(session, user_id)
        settings = None

        if not email_account:
            # Fallback to legacy email_settings
            try:
                settings = await email_settings_service.get_settings(session, user_id)
            except Exception as e:
                logger.error("Error getting email settings for user %s: %s", user_id, e)
                return {"success": False, "error": f"Error fetching settings: {str(e)}"}

        if not email_account and not settings:
            logger.warning("No email configuration found for user %s", user_id)
            return {"success": False, "error": "No email settings configured. Please add an email account in Settings."}

        # Get SMTP configuration from either source
        if email_account:
            smtp_host = email_account.smtp_host
            smtp_port = email_account.smtp_port
            smtp_username = email_account.smtp_username
            smtp_use_tls = email_account.smtp_use_tls
            password = email_account_service.get_decrypted_smtp_password(email_account)
            default_from_email = email_account.email
            default_from_name = email_account.from_name or email_account.name
            logger.debug("Using email account: %s", email_account.name)
        else:
            smtp_host = settings.smtp_host
            smtp_port = settings.smtp_port
            smtp_username = settings.smtp_username
            smtp_use_tls = settings.smtp_use_tls
            password = email_settings_service.get_decrypted_smtp_password(settings)
            default_from_email = settings.from_email or settings.smtp_username
            default_from_name = settings.from_name or "ChampMail"
            logger.debug("Using legacy email settings")

        if not smtp_host or not smtp_username:
            return {"success": False, "error": "SMTP settings incomplete"}

        if not password:
            return {"success": False, "error": "SMTP password not configured"}

        try:
            sender_email = from_email or default_from_email
            sender_name = from_name or default_from_name

            # Create message
            if html_body:
                msg = MIMEMultipart("alternative")
                msg.attach(MIMEText(body, "plain"))
                msg.attach(MIMEText(html_body, "html"))
            else:
                msg = MIMEText(body, "plain")

            msg["Subject"] = subject
            msg["From"] = f"{sender_name} <{sender_email}>"
            msg["To"] = to_email

            # Get reply-to from the appropriate source
            default_reply_to = None
            if email_account:
                default_reply_to = email_account.reply_to_email
            elif settings:
                default_reply_to = settings.reply_to_email

            if reply_to or default_reply_to:
                msg["Reply-To"] = reply_to or default_reply_to

            # Connect and send
            context = ssl.create_default_context()

            if smtp_use_tls:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
                server.starttls(context=context)
            else:
                server = smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=30)

            server.login(smtp_username, password)
            server.sendmail(sender_email, to_email, msg.as_string())
            server.quit()
            logger.info("Email sent successfully to %s", to_email)

            return {
                "success": True,
                "message": f"Email sent to {to_email}",
                "details": {
                    "to": to_email,
                    "from": sender_email,
                    "subject": subject,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            }

        except smtplib.SMTPAuthenticationError as e:
            logger.error("SMTP auth error for user %s: %s", user_id, e)
            return {"success": False, "error": f"SMTP authentication failed: {str(e)}"}
        except smtplib.SMTPConnectError as e:
            logger.error("SMTP connect error for user %s: %s", user_id, e)
            return {"success": False, "error": f"Could not connect to SMTP server: {str(e)}"}
        except Exception as e:
            logger.exception("Email send failed for user %s", user_id)
            return {"success": False, "error": f"{type(e).__name__}: {str(e)}"}

    async def fetch_emails(
        self,
        session: AsyncSession,
        user_id: str,
        mailbox: str = "INBOX",
        limit: int = 20,
        unseen_only: bool = False,
    ) -> dict[str, Any]:
        """
        Fetch emails from the user's IMAP inbox.

        Args:
            session: Database session
            user_id: User ID whose IMAP settings to use
            mailbox: Mailbox to fetch from (default: INBOX)
            limit: Maximum number of emails to fetch
            unseen_only: Only fetch unread emails

        Returns:
            Dict with emails list or error
        """
        # Try to get email account first (new multi-account system)
        email_account = await email_account_service.get_default_account(session, user_id)
        settings = None

        if not email_account:
            settings = await email_settings_service.get_settings(session, user_id)

        if not email_account and not settings:
            return {"success": False, "error": "No email settings configured. Please add an email account in Settings.", "emails": []}

        # Get IMAP configuration from either source
        if email_account:
            imap_host = email_account.imap_host
            imap_port = email_account.imap_port
            imap_username = email_account.imap_username
            imap_use_ssl = email_account.imap_use_ssl
            imap_mailbox = email_account.imap_mailbox
            password = email_account_service.get_decrypted_imap_password(email_account)
        else:
            imap_host = settings.imap_host
            imap_port = settings.imap_port
            imap_username = settings.imap_username
            imap_use_ssl = settings.imap_use_ssl
            imap_mailbox = settings.imap_mailbox
            password = email_settings_service.get_decrypted_imap_password(settings)

        if not imap_host or not imap_username:
            return {"success": False, "error": "IMAP settings incomplete", "emails": []}

        if not password:
            return {"success": False, "error": "IMAP password not configured", "emails": []}

        try:
            # Connect to IMAP
            if imap_use_ssl:
                server = imaplib.IMAP4_SSL(imap_host, imap_port)
            else:
                server = imaplib.IMAP4(imap_host, imap_port)

            server.login(imap_username, password)
            server.select(mailbox or imap_mailbox or "INBOX")

            # Search for emails
            search_criteria = "UNSEEN" if unseen_only else "ALL"
            _, message_numbers = server.search(None, search_criteria)

            email_ids = message_numbers[0].split()
            # Get the most recent emails (last N)
            email_ids = email_ids[-limit:] if len(email_ids) > limit else email_ids
            email_ids = email_ids[::-1]  # Reverse to get newest first

            emails = []
            for email_id in email_ids:
                _, msg_data = server.fetch(email_id, "(RFC822)")
                if msg_data[0] is None:
                    continue

                email_body = msg_data[0][1]
                msg = email.message_from_bytes(email_body)

                # Parse email data
                parsed_email = self._parse_email(msg)
                emails.append(parsed_email)

            server.logout()

            return {
                "success": True,
                "emails": emails,
                "count": len(emails),
                "mailbox": mailbox,
            }

        except imaplib.IMAP4.error as e:
            return {"success": False, "error": f"IMAP error: {str(e)}", "emails": []}
        except Exception as e:
            return {"success": False, "error": str(e), "emails": []}

    def _parse_email(self, msg: email.message.Message) -> dict[str, Any]:
        """Parse an email message into a dictionary."""
        # Decode subject
        subject = ""
        subject_header = msg.get("Subject", "")
        if subject_header:
            decoded_parts = decode_header(subject_header)
            subject = "".join(
                part.decode(encoding or "utf-8") if isinstance(part, bytes) else part
                for part, encoding in decoded_parts
            )

        # Parse from address
        from_header = msg.get("From", "")
        from_name = ""
        from_address = ""
        if "<" in from_header:
            from_name = from_header.split("<")[0].strip().strip('"')
            from_address = from_header.split("<")[1].strip(">")
        else:
            from_address = from_header

        # Parse to address
        to_header = msg.get("To", "")
        to_name = ""
        to_address = ""
        if "<" in to_header:
            to_name = to_header.split("<")[0].strip().strip('"')
            to_address = to_header.split("<")[1].strip(">")
        else:
            to_address = to_header

        # Get date
        date_str = msg.get("Date", "")
        try:
            date_received = email.utils.parsedate_to_datetime(date_str).isoformat()
        except Exception:
            date_received = datetime.utcnow().isoformat()

        # Get body
        body_text = ""
        body_html = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    try:
                        body_text = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    except Exception:
                        pass
                elif content_type == "text/html":
                    try:
                        body_html = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    except Exception:
                        pass
        else:
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    body_text = payload.decode("utf-8", errors="ignore")
            except Exception:
                pass

        # Check for attachments
        has_attachments = False
        attachments = []
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                if part.get("Content-Disposition") is not None:
                    has_attachments = True
                    filename = part.get_filename()
                    if filename:
                        attachments.append({
                            "filename": filename,
                            "content_type": part.get_content_type(),
                        })

        return {
            "message_id": msg.get("Message-ID", ""),
            "subject": subject,
            "from": {
                "name": from_name,
                "address": from_address,
                "value": [{"name": from_name, "address": from_address}],
            },
            "to": {
                "name": to_name,
                "address": to_address,
                "value": [{"name": to_name, "address": to_address}],
            },
            "date": date_received,
            "text": body_text,
            "html": body_html,
            "has_attachments": has_attachments,
            "attachments": attachments,
            "headers": {
                "priority": msg.get("X-Priority", "normal"),
            },
        }


# Singleton instance
email_service = EmailService()
