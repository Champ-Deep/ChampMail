"""
Email service for sending and receiving emails via SMTP/IMAP.

Responsibilities:
- SMTP transport (connect, authenticate, send)
- IMAP retrieval (connect, authenticate, fetch/parse)

Header construction is delegated to EmailHeaderBuilder (Single Responsibility).
Credential resolution is handled by _resolve_smtp_config / _resolve_imap_config.
"""

from __future__ import annotations

import logging
import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from email.utils import formatdate, formataddr, make_msgid
import ssl
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_settings import EmailSettings
from app.models.email_account import EmailAccount
from app.services.email_settings_service import email_settings_service
from app.services.email_account_service import email_account_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SmtpConfig:
    """Resolved SMTP credentials and identity — immutable after construction."""
    host: str
    port: int
    username: str
    password: str
    use_tls: bool
    from_email: str
    from_name: str
    reply_to: Optional[str] = None


# ---------------------------------------------------------------------------
# EmailHeaderBuilder  (Single Responsibility — only builds headers)
# ---------------------------------------------------------------------------

class EmailHeaderBuilder:
    """Constructs RFC-compliant email headers.

    Separated from EmailService so header logic can be tested and evolved
    independently of SMTP transport.
    """

    @staticmethod
    def build_message(
        *,
        sender_email: str,
        sender_name: str,
        to_email: str,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
        reply_to: Optional[str] = None,
        campaign_id: Optional[str] = None,
        prospect_id: Optional[str] = None,
        tracking_id: Optional[str] = None,
        unsubscribe_url: Optional[str] = None,
    ) -> MIMEMultipart:
        """Build a complete MIME message with all compliance headers.

        Parameters
        ----------
        sender_email : str
            The "From" email address.
        sender_name : str
            The display name for the "From" header.
        to_email : str
            Recipient email address.
        subject : str
            Email subject line.
        body : str
            Plain-text body (always included for multipart/alternative).
        html_body : str, optional
            HTML body. When provided, message is multipart/alternative.
        reply_to : str, optional
            Reply-To address.
        campaign_id : str, optional
            Campaign UUID — when set, List-Unsubscribe headers are added.
        prospect_id : str, optional
            Prospect UUID — used alongside campaign_id for tracking.
        tracking_id : str, optional
            Pre-generated tracking ID for unsubscribe header.
        unsubscribe_url : str, optional
            Pre-generated HTTPS unsubscribe URL.

        Returns
        -------
        MIMEMultipart
            Fully constructed message ready for SMTP sendmail().
        """
        # Always multipart/alternative — plain-text + optional HTML
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain", "utf-8"))
        if html_body:
            msg.attach(MIMEText(html_body, "html", "utf-8"))

        # --- Core headers ---
        sender_domain = sender_email.split("@")[1] if "@" in sender_email else "localhost"
        msg["Message-ID"] = make_msgid(domain=sender_domain)
        msg["Date"] = formatdate(localtime=True)
        msg["MIME-Version"] = "1.0"
        msg["Subject"] = subject
        msg["From"] = formataddr((sender_name, sender_email))
        msg["To"] = to_email

        if reply_to:
            msg["Reply-To"] = reply_to

        # --- List-Unsubscribe (Gmail/Yahoo/Outlook compliance) ---
        # Only added for campaign/bulk emails — not for transactional sends
        if tracking_id and unsubscribe_url:
            mailto_unsub = f"mailto:{sender_email}?subject=unsubscribe-{tracking_id}"
            msg["List-Unsubscribe"] = f"<{mailto_unsub}>, <{unsubscribe_url}>"
            msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

        return msg


# ---------------------------------------------------------------------------
# EmailService
# ---------------------------------------------------------------------------

class EmailService:
    """Service for sending and receiving emails."""

    def __init__(self) -> None:
        self._header_builder = EmailHeaderBuilder()

    # -- credential resolution (DRY — extracted from send_email / fetch_emails) --

    async def _resolve_smtp_config(
        self,
        session: AsyncSession,
        user_id: str,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> SmtpConfig | dict[str, Any]:
        """Resolve SMTP credentials from EmailAccount or legacy EmailSettings.

        Returns SmtpConfig on success, or an error dict on failure.
        """
        email_account = await email_account_service.get_default_account(session, user_id)
        settings = None

        if not email_account:
            try:
                settings = await email_settings_service.get_settings(session, user_id)
            except Exception as e:
                logger.error("Error getting email settings for user %s: %s", user_id, e)
                return {"success": False, "error": f"Error fetching settings: {str(e)}"}

        if not email_account and not settings:
            logger.warning("No email configuration found for user %s", user_id)
            return {"success": False, "error": "No email settings configured. Please add an email account in Settings."}

        if email_account:
            password = email_account_service.get_decrypted_smtp_password(email_account)
            # from_email resolution: explicit override > account.from_email > account.email
            resolved_from_email = from_email or getattr(email_account, "from_email", None) or email_account.email
            resolved_from_name = from_name or email_account.from_name or email_account.name
            resolved_reply_to = reply_to or email_account.reply_to_email
            return SmtpConfig(
                host=email_account.smtp_host,
                port=email_account.smtp_port,
                username=email_account.smtp_username,
                password=password,
                use_tls=email_account.smtp_use_tls,
                from_email=resolved_from_email,
                from_name=resolved_from_name,
                reply_to=resolved_reply_to,
            )
        else:
            password = email_settings_service.get_decrypted_smtp_password(settings)
            resolved_from_email = from_email or settings.from_email or settings.smtp_username
            resolved_from_name = from_name or settings.from_name or settings.smtp_username
            resolved_reply_to = reply_to or settings.reply_to_email
            return SmtpConfig(
                host=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_username,
                password=password,
                use_tls=settings.smtp_use_tls,
                from_email=resolved_from_email,
                from_name=resolved_from_name,
                reply_to=resolved_reply_to,
            )

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
        campaign_id: Optional[str] = None,
        prospect_id: Optional[str] = None,
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
            campaign_id: Campaign UUID — triggers tracking + unsubscribe headers
            prospect_id: Prospect UUID — used with campaign_id for tracking

        Returns:
            Dict with status and message
        """
        logger.info("Sending email to %s for user %s", to_email, user_id)

        # --- Resolve SMTP credentials ---
        config = await self._resolve_smtp_config(
            session, user_id, from_email, from_name, reply_to,
        )
        if isinstance(config, dict):
            return config  # error dict

        if not config.host or not config.username:
            return {"success": False, "error": "SMTP settings incomplete"}
        if not config.password:
            return {"success": False, "error": "SMTP password not configured"}

        try:
            # --- Generate tracking URLs for campaign emails ---
            tracking_id = None
            unsubscribe_url = None
            if campaign_id and prospect_id:
                try:
                    from app.services.tracking_service import tracking_service
                    tracking_urls = await tracking_service.generate_tracking_urls(
                        campaign_id, prospect_id,
                    )
                    tracking_id = tracking_urls.get("tracking_id")
                    unsubscribe_url = tracking_urls.get("unsubscribe_url")

                    # Inject tracking pixel + click wrappers into HTML
                    if html_body:
                        html_body = tracking_service.wrap_links_in_html(
                            html_body,
                            tracking_urls["click_base_url"],
                            tracking_urls["signature"],
                        )
                        html_body = html_body.replace(
                            "{{tracking_url}}", tracking_urls.get("pixel_url", ""),
                        )
                        html_body = html_body.replace(
                            "{{unsubscribe_url}}", tracking_urls.get("unsubscribe_url", ""),
                        )
                except Exception:
                    logger.debug("Tracking setup failed, sending without tracking", exc_info=True)

            # --- Build message with compliance headers ---
            msg = self._header_builder.build_message(
                sender_email=config.from_email,
                sender_name=config.from_name,
                to_email=to_email,
                subject=subject,
                body=body,
                html_body=html_body,
                reply_to=config.reply_to,
                campaign_id=campaign_id,
                prospect_id=prospect_id,
                tracking_id=tracking_id,
                unsubscribe_url=unsubscribe_url,
            )

            # --- SMTP transport ---
            context = ssl.create_default_context()

            if config.use_tls:
                server = smtplib.SMTP(config.host, config.port, timeout=30)
                server.starttls(context=context)
            else:
                server = smtplib.SMTP_SSL(config.host, config.port, context=context, timeout=30)

            server.login(config.username, config.password)
            server.sendmail(config.from_email, to_email, msg.as_string())
            server.quit()
            logger.info("Email sent successfully to %s", to_email)

            return {
                "success": True,
                "message": f"Email sent to {to_email}",
                "details": {
                    "to": to_email,
                    "from": config.from_email,
                    "subject": subject,
                    "message_id": msg["Message-ID"],
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
