"""
Campaign Reply & Bounce Detector.

Polls each user's IMAP mailbox for incoming replies and bounces,
matches them to SendLog entries via In-Reply-To / References headers,
and updates campaign stats accordingly.

Used by Celery beat tasks (every 5 minutes).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import async_session_maker
from app.db.redis import redis_client
from app.models.campaign import Campaign
from app.models.email_settings import EmailSettings
from app.models.send_log import BounceLog, SendLog
from app.services.email_provider import IMAPReplyDetector, IncomingMessage

logger = logging.getLogger(__name__)

# Redis key storing the last-seen IMAP UID per user
_LAST_UID_KEY = "reply_detector:last_uid:{user_id}"

# DSN bounce patterns (Delivery Status Notification)
_DSN_SUBJECT_RE = re.compile(
    r"(undeliverable|delivery.*fail|returned.*mail|mail.*delivery.*"
    r"failed|delivery.*status|non.*deliver)",
    re.IGNORECASE,
)
_BOUNCE_BODY_PATTERNS = [
    re.compile(r"(\d{3})\s[\d.]+\s", re.IGNORECASE),             # SMTP code
    re.compile(r"mailbox.*(?:full|unavailable)", re.IGNORECASE),
    re.compile(r"user.*(?:unknown|not found)", re.IGNORECASE),
    re.compile(r"address.*rejected", re.IGNORECASE),
    re.compile(r"does not exist", re.IGNORECASE),
    re.compile(r"permanent.*failure", re.IGNORECASE),
]


class CampaignReplyDetector:
    """Detects campaign replies and DSN bounces from user IMAP mailboxes."""

    # ------------------------------------------------------------------
    # Public: check replies for all users with verified IMAP
    # ------------------------------------------------------------------

    async def check_all_users(self) -> Dict[str, Any]:
        """Scan every user with verified IMAP for new replies & bounces.

        Returns summary dict with total replies and bounces found.
        """
        total_replies = 0
        total_bounces = 0
        users_checked = 0

        async with async_session_maker() as session:
            result = await session.execute(
                select(EmailSettings).where(
                    EmailSettings.imap_verified == True,  # noqa: E712
                    EmailSettings.imap_host.isnot(None),
                    EmailSettings.imap_username.isnot(None),
                )
            )
            settings_list = result.scalars().all()

        for settings in settings_list:
            user_id = str(settings.user_id)
            try:
                replies, bounces = await self._check_user_mailbox(settings)
                total_replies += replies
                total_bounces += bounces
                users_checked += 1
            except Exception as exc:
                logger.error(
                    "Reply check failed for user %s: %s", user_id, exc
                )

        logger.info(
            "Reply detection complete: %d users, %d replies, %d bounces",
            users_checked, total_replies, total_bounces,
        )

        return {
            "users_checked": users_checked,
            "total_replies": total_replies,
            "total_bounces": total_bounces,
        }

    # ------------------------------------------------------------------
    # Internal: check a single user's mailbox
    # ------------------------------------------------------------------

    async def _check_user_mailbox(
        self, settings: EmailSettings
    ) -> tuple[int, int]:
        """Connect to one user's IMAP and process new messages.

        Returns (reply_count, bounce_count).
        """
        from app.services.email_settings_service import email_settings_service

        user_id = str(settings.user_id)

        password = email_settings_service.get_decrypted_imap_password(settings)
        if not password:
            return 0, 0

        detector = IMAPReplyDetector(
            host=settings.imap_host,
            port=settings.imap_port or 993,
            username=settings.imap_username,
            password=password,
            use_ssl=settings.imap_use_ssl if settings.imap_use_ssl is not None else True,
            mailbox=settings.imap_mailbox or "INBOX",
        )

        # Get last-seen UID from Redis
        last_uid_data = await redis_client.get_json(
            _LAST_UID_KEY.format(user_id=user_id)
        )
        since_uid = last_uid_data.get("uid", 0) if last_uid_data else 0

        messages = await detector.check_new_messages(since_uid=since_uid)
        if not messages:
            return 0, 0

        reply_count = 0
        bounce_count = 0

        for msg in messages:
            if self._is_bounce(msg):
                matched = await self._process_bounce(msg, user_id)
                if matched:
                    bounce_count += 1
            elif msg.in_reply_to or msg.references:
                matched = await self._process_reply(msg, user_id)
                if matched:
                    reply_count += 1

        # Update last-seen UID (use highest message_id numerically if possible)
        new_uid = since_uid
        for msg in messages:
            # message_id is a string like "<xxx@domain>"; use a counter instead
            new_uid = max(new_uid, since_uid + len(messages))

        await redis_client.set_json(
            _LAST_UID_KEY.format(user_id=user_id),
            {"uid": new_uid},
            ex=86400 * 30,
        )

        return reply_count, bounce_count

    # ------------------------------------------------------------------
    # Reply processing
    # ------------------------------------------------------------------

    async def _process_reply(
        self, msg: IncomingMessage, user_id: str
    ) -> bool:
        """Match an incoming reply to a SendLog and record it.

        Returns True if the reply was matched to an outbound send.
        """
        # Build list of message IDs to search for
        candidate_ids = []
        if msg.in_reply_to:
            candidate_ids.append(msg.in_reply_to.strip())
        if msg.references:
            # References header can contain multiple message IDs
            candidate_ids.extend(
                ref.strip() for ref in msg.references.split()
                if ref.strip()
            )

        if not candidate_ids:
            return False

        async with async_session_maker() as session:
            # Find the original outbound send
            result = await session.execute(
                select(SendLog).where(
                    SendLog.message_id.in_(candidate_ids),
                    SendLog.status.in_(["sent", "delivered", "opened", "clicked"]),
                )
            )
            send_log = result.scalars().first()

            if not send_log:
                return False

            # Update SendLog with reply info
            now = datetime.now(timezone.utc)
            await session.execute(
                update(SendLog)
                .where(SendLog.id == send_log.id)
                .values(
                    replied_at=now,
                    reply_text=msg.body[:2000] if msg.body else None,
                    status="replied",
                )
            )

            # Increment campaign reply count
            if send_log.campaign_id:
                await session.execute(
                    update(Campaign)
                    .where(Campaign.id == send_log.campaign_id)
                    .values(
                        replied_count=Campaign.replied_count + 1,
                        updated_at=now,
                    )
                )

            await session.commit()

            logger.info(
                "Reply detected: from=%s, matched send_log=%s, campaign=%s",
                msg.from_email,
                send_log.id,
                send_log.campaign_id,
            )

        return True

    # ------------------------------------------------------------------
    # Bounce detection from IMAP (DSN messages)
    # ------------------------------------------------------------------

    def _is_bounce(self, msg: IncomingMessage) -> bool:
        """Check if an incoming message is a DSN bounce notification."""
        if _DSN_SUBJECT_RE.search(msg.subject or ""):
            return True
        # Check from address for common mailer-daemon patterns
        from_lower = (msg.from_email or "").lower()
        return any(
            kw in from_lower
            for kw in ("mailer-daemon", "postmaster", "mail-daemon")
        )

    async def _process_bounce(
        self, msg: IncomingMessage, user_id: str
    ) -> bool:
        """Parse a DSN bounce and record it against the original send.

        Returns True if the bounce was matched to an outbound send.
        """
        # Try to find the original message ID from references
        candidate_ids = []
        if msg.in_reply_to:
            candidate_ids.append(msg.in_reply_to.strip())
        if msg.references:
            candidate_ids.extend(
                ref.strip() for ref in msg.references.split()
                if ref.strip()
            )

        if not candidate_ids:
            return False

        # Classify bounce type from body
        bounce_type = "soft"
        bounce_category = "unknown"
        body_lower = (msg.body or "").lower()

        if "user unknown" in body_lower or "does not exist" in body_lower:
            bounce_type = "hard"
            bounce_category = "unknown_user"
        elif "mailbox full" in body_lower or "quota exceeded" in body_lower:
            bounce_type = "soft"
            bounce_category = "mailbox_full"
        elif "address rejected" in body_lower:
            bounce_type = "hard"
            bounce_category = "address_rejected"
        elif "permanent" in body_lower:
            bounce_type = "hard"
            bounce_category = "permanent_failure"

        # Extract SMTP error code if present
        smtp_code = None
        for pattern in _BOUNCE_BODY_PATTERNS:
            match = pattern.search(msg.body or "")
            if match and match.group(0).strip()[:3].isdigit():
                smtp_code = match.group(0).strip()[:3]
                break

        async with async_session_maker() as session:
            result = await session.execute(
                select(SendLog).where(
                    SendLog.message_id.in_(candidate_ids),
                    SendLog.status.in_(["sent", "delivered", "opened", "clicked"]),
                )
            )
            send_log = result.scalars().first()

            if not send_log:
                return False

            now = datetime.now(timezone.utc)

            # Update SendLog
            await session.execute(
                update(SendLog)
                .where(SendLog.id == send_log.id)
                .values(
                    bounced_at=now,
                    bounce_type=bounce_type,
                    bounce_reason=msg.subject,
                    smtp_response=msg.body[:500] if msg.body else None,
                    status="bounced",
                )
            )

            # Create BounceLog entry
            bounce_log = BounceLog(
                send_log_id=send_log.id,
                prospect_id=send_log.prospect_id,
                email=send_log.recipient_email,
                bounce_type=bounce_type,
                bounce_category=bounce_category,
                smtp_error_code=smtp_code,
                smtp_response=msg.body[:500] if msg.body else None,
            )
            session.add(bounce_log)

            # Increment campaign bounce count
            if send_log.campaign_id:
                await session.execute(
                    update(Campaign)
                    .where(Campaign.id == send_log.campaign_id)
                    .values(
                        bounced_count=Campaign.bounced_count + 1,
                        updated_at=now,
                    )
                )

            await session.commit()

            logger.info(
                "IMAP bounce detected: type=%s, category=%s, send_log=%s, campaign=%s",
                bounce_type,
                bounce_category,
                send_log.id,
                send_log.campaign_id,
            )

        return True


# Module-level singleton
campaign_reply_detector = CampaignReplyDetector()
