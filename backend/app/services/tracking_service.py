"""
Email Tracking and Bounce Handling Service.

Handles open tracking (via pixel), click tracking (via URL wrapping),
bounce classification, and campaign-level analytics aggregation.

Tracking IDs follow the format: {campaign_id}_{prospect_id}_{uuid_short}
This allows reconstructing who opened/clicked without a separate lookup table.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode, urlparse
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.postgres import async_session_maker
from app.db.redis import redis_client
from app.models.campaign import Campaign, CampaignProspect, Prospect
from app.models.send_log import BounceLog, SendLog

logger = logging.getLogger(__name__)

# Tracking URL base (should be configured via env in production)
TRACKING_BASE_URL = f"{settings.frontend_url}/api/v1/track"

# Redis TTL for tracking event deduplication (24 hours)
TRACKING_DEDUP_TTL = 86400

# Redis TTL for real-time tracking stats cache (5 minutes)
STATS_CACHE_TTL = 300


class TrackingService:
    """Track email opens, clicks, bounces with immaculate detail.

    Open tracking uses a 1x1 transparent pixel embedded in the HTML email.
    Click tracking wraps all links through a redirect endpoint that records
    the click before forwarding to the original URL.
    Bounce classification uses SMTP response code patterns.
    """

    def _generate_tracking_id(self, campaign_id: str, prospect_id: str) -> str:
        """Generate a unique, deterministic tracking ID.

        Format: {campaign_short}_{prospect_short}_{random_suffix}
        The ID is short enough for URL embedding but unique enough to prevent collisions.
        """
        campaign_short = campaign_id[:8] if campaign_id else "unknown"
        prospect_short = prospect_id[:8] if prospect_id else "unknown"
        random_suffix = uuid4().hex[:8]
        return f"{campaign_short}_{prospect_short}_{random_suffix}"

    def _sign_tracking_id(self, tracking_id: str) -> str:
        """Generate an HMAC signature for a tracking ID to prevent spoofing."""
        secret = settings.webhook_secret or settings.jwt_secret_key
        return hmac.new(
            secret.encode(),
            tracking_id.encode(),
            hashlib.sha256,
        ).hexdigest()[:16]

    def _verify_tracking_signature(self, tracking_id: str, signature: str) -> bool:
        """Verify the HMAC signature of a tracking ID."""
        expected = self._sign_tracking_id(tracking_id)
        return hmac.compare_digest(expected, signature)

    async def generate_tracking_urls(
        self,
        campaign_id: str,
        prospect_id: str,
    ) -> dict:
        """Generate unique tracking pixel URL and click-wrapped URL patterns.

        Parameters
        ----------
        campaign_id : str
            Campaign UUID.
        prospect_id : str
            Prospect UUID.

        Returns
        -------
        dict
            Contains tracking_id, pixel_url, click_base_url, unsubscribe_url,
            and the signature for verification.
        """
        tracking_id = self._generate_tracking_id(campaign_id, prospect_id)
        signature = self._sign_tracking_id(tracking_id)

        # Store the tracking_id -> campaign/prospect mapping in Redis
        mapping = {
            "campaign_id": campaign_id,
            "prospect_id": prospect_id,
            "created_at": datetime.utcnow().isoformat(),
        }
        await redis_client.set_json(
            f"tracking:{tracking_id}",
            mapping,
            ex=86400 * 90,  # Keep mapping for 90 days
        )

        pixel_url = (
            f"{TRACKING_BASE_URL}/open/{tracking_id}"
            f"?sig={signature}"
        )

        click_base_url = (
            f"{TRACKING_BASE_URL}/click/{tracking_id}"
            f"?sig={signature}"
        )

        unsubscribe_url = (
            f"{TRACKING_BASE_URL}/unsubscribe/{tracking_id}"
            f"?sig={signature}"
        )

        return {
            "tracking_id": tracking_id,
            "signature": signature,
            "pixel_url": pixel_url,
            "click_base_url": click_base_url,
            "unsubscribe_url": unsubscribe_url,
        }

    def wrap_links_in_html(
        self,
        html_body: str,
        click_base_url: str,
        signature: str,
    ) -> str:
        """Replace all links in HTML with click-tracked versions.

        Wraps <a href="..."> links through the click tracking endpoint.
        Skips mailto: links, unsubscribe links, and tracking pixel URLs.

        Parameters
        ----------
        html_body : str
            Original HTML email body.
        click_base_url : str
            Base URL for click tracking (without the destination URL param).
        signature : str
            HMAC signature for the tracking ID.

        Returns
        -------
        str
            HTML with all trackable links wrapped.
        """
        # Pattern to match href attributes in anchor tags
        href_pattern = re.compile(
            r'(<a\s[^>]*href=["\'])([^"\']+)(["\'][^>]*>)',
            re.IGNORECASE,
        )

        def _wrap_link(match):
            prefix = match.group(1)
            url = match.group(2)
            suffix = match.group(3)

            # Skip non-http links, tracking pixels, and template variables
            if any(skip in url.lower() for skip in [
                "mailto:", "tel:", "javascript:",
                "tracking_url", "unsubscribe",
                click_base_url,
                "{{", "}}",
            ]):
                return match.group(0)

            # Wrap the URL through our click tracker
            encoded_url = quote(url, safe="")
            tracked_url = f"{click_base_url}&url={encoded_url}"
            return f"{prefix}{tracked_url}{suffix}"

        return href_pattern.sub(_wrap_link, html_body)

    async def record_open(self, tracking_id: str) -> dict:
        """Record an email open event.

        Deduplicates opens within a 1-hour window per tracking_id to avoid
        counting image proxy re-fetches as multiple opens.

        Parameters
        ----------
        tracking_id : str
            Unique tracking identifier from the pixel URL.

        Returns
        -------
        dict
            Event details including whether this was a first open or repeat.
        """
        now = datetime.utcnow()

        # Deduplication: check if we already recorded an open recently
        dedup_key = f"tracking:open:dedup:{tracking_id}"
        already_counted = await redis_client.exists(dedup_key)

        # Resolve campaign_id and prospect_id from tracking_id
        mapping = await redis_client.get_json(f"tracking:{tracking_id}")
        if not mapping:
            logger.warning("Open event for unknown tracking_id: %s", tracking_id)
            return {"status": "unknown_tracking_id", "tracking_id": tracking_id}

        campaign_id = mapping["campaign_id"]
        prospect_id = mapping["prospect_id"]

        # Record the event in Redis for real-time stats
        event = {
            "type": "open",
            "tracking_id": tracking_id,
            "campaign_id": campaign_id,
            "prospect_id": prospect_id,
            "timestamp": now.isoformat(),
            "is_first": not already_counted,
        }

        # Append to the campaign's event stream
        events_key = f"tracking:events:{campaign_id}"
        await redis_client.set_json(
            f"tracking:open:{tracking_id}:{now.strftime('%Y%m%d%H')}",
            event,
            ex=86400 * 30,
        )

        if not already_counted:
            # Set dedup window (1 hour)
            await redis_client.set(dedup_key, "1", ex=3600)

            # Increment real-time counters
            await redis_client.incr(f"tracking:stats:{campaign_id}:opens")
            await redis_client.incr(f"tracking:stats:{campaign_id}:unique_opens")

            # Update database records
            await self._update_open_in_db(campaign_id, prospect_id, now)
        else:
            # Still count total opens
            await redis_client.incr(f"tracking:stats:{campaign_id}:opens")

        logger.info(
            "Open recorded: campaign=%s prospect=%s first=%s",
            campaign_id,
            prospect_id,
            not already_counted,
        )
        return event

    async def record_click(self, tracking_id: str, url: str) -> dict:
        """Record a link click event.

        Parameters
        ----------
        tracking_id : str
            Unique tracking identifier from the click URL.
        url : str
            The original destination URL that was clicked.

        Returns
        -------
        dict
            Event details including the destination URL.
        """
        now = datetime.utcnow()

        mapping = await redis_client.get_json(f"tracking:{tracking_id}")
        if not mapping:
            logger.warning("Click event for unknown tracking_id: %s", tracking_id)
            return {"status": "unknown_tracking_id", "tracking_id": tracking_id}

        campaign_id = mapping["campaign_id"]
        prospect_id = mapping["prospect_id"]

        # Check if this is the first click for this prospect in this campaign
        first_click_key = f"tracking:click:first:{campaign_id}:{prospect_id}"
        is_first = not await redis_client.exists(first_click_key)

        event = {
            "type": "click",
            "tracking_id": tracking_id,
            "campaign_id": campaign_id,
            "prospect_id": prospect_id,
            "url": url,
            "timestamp": now.isoformat(),
            "is_first": is_first,
        }

        # Store click event
        click_id = uuid4().hex[:12]
        await redis_client.set_json(
            f"tracking:click:{tracking_id}:{click_id}",
            event,
            ex=86400 * 30,
        )

        # Increment counters
        await redis_client.incr(f"tracking:stats:{campaign_id}:clicks")
        if is_first:
            await redis_client.set(first_click_key, "1", ex=86400 * 90)
            await redis_client.incr(f"tracking:stats:{campaign_id}:unique_clicks")

        # Update database
        await self._update_click_in_db(campaign_id, prospect_id, url, now)

        logger.info(
            "Click recorded: campaign=%s prospect=%s url=%s first=%s",
            campaign_id,
            prospect_id,
            url[:80],
            is_first,
        )
        return event

    async def classify_bounce(self, bounce_data: dict) -> dict:
        """Classify a bounce by type based on SMTP response codes and patterns.

        Categories:
        - hard_bounce: Permanent delivery failure (bad email, domain doesn't exist)
        - soft_bounce: Temporary failure (mailbox full, server busy)
        - out_of_office: Auto-reply indicating absence
        - unsubscribe: Auto-generated unsubscribe confirmation
        - spam_complaint: Recipient marked as spam
        - transient: Temporary network/server issue, likely to resolve

        Parameters
        ----------
        bounce_data : dict
            Must contain at least 'smtp_response' or 'bounce_type'.
            Optionally 'email', 'smtp_code', 'diagnostic_message'.

        Returns
        -------
        dict
            Classification result with type, category, should_suppress, description.
        """
        smtp_code = str(bounce_data.get("smtp_code", ""))
        smtp_response = (bounce_data.get("smtp_response") or "").lower()
        diagnostic = (bounce_data.get("diagnostic_message") or "").lower()
        combined_text = f"{smtp_response} {diagnostic}"
        provided_type = (bounce_data.get("bounce_type") or "").lower()

        # Hard bounce patterns (5xx permanent failures)
        hard_bounce_patterns = [
            "user unknown", "mailbox not found", "no such user",
            "does not exist", "invalid recipient", "unknown user",
            "invalid address", "bad destination", "undeliverable",
            "rejected", "permanently", "account disabled",
            "account has been disabled", "no mailbox here",
        ]

        # Soft bounce patterns (4xx temporary failures)
        soft_bounce_patterns = [
            "mailbox full", "over quota", "insufficient storage",
            "try again", "temporarily", "busy", "unavailable",
            "connection timed out", "too many connections",
            "rate limit", "throttl", "defer",
        ]

        # Out of office patterns
        ooo_patterns = [
            "out of office", "auto-reply", "automatic reply",
            "on vacation", "away from", "out of the office",
            "currently unavailable", "limited access to email",
        ]

        # Spam complaint patterns
        spam_patterns = [
            "spam", "abuse", "blacklist", "blocked",
            "reputation", "policy", "rbl", "dnsbl",
        ]

        # Classify
        bounce_type = "unknown"
        category = "unknown"
        should_suppress = False
        description = ""

        if smtp_code.startswith("5") or provided_type == "hard":
            if any(p in combined_text for p in hard_bounce_patterns):
                bounce_type = "hard_bounce"
                category = "invalid_recipient"
                should_suppress = True
                description = "Permanent delivery failure: recipient address is invalid"
            elif any(p in combined_text for p in spam_patterns):
                bounce_type = "hard_bounce"
                category = "spam_block"
                should_suppress = True
                description = "Blocked by spam filter or blacklist"
            else:
                bounce_type = "hard_bounce"
                category = "permanent_failure"
                should_suppress = True
                description = f"Permanent delivery failure (SMTP {smtp_code})"

        elif smtp_code.startswith("4") or provided_type == "soft":
            if any(p in combined_text for p in soft_bounce_patterns):
                bounce_type = "soft_bounce"
                category = "temporary_failure"
                should_suppress = False
                description = "Temporary failure, may succeed on retry"
            else:
                bounce_type = "soft_bounce"
                category = "temporary_failure"
                should_suppress = False
                description = f"Temporary delivery issue (SMTP {smtp_code})"

        elif any(p in combined_text for p in ooo_patterns):
            bounce_type = "out_of_office"
            category = "auto_reply"
            should_suppress = False
            description = "Recipient is out of office"

        elif "unsubscribe" in combined_text or provided_type == "unsubscribe":
            bounce_type = "unsubscribe"
            category = "opt_out"
            should_suppress = True
            description = "Recipient unsubscribed"

        elif any(p in combined_text for p in spam_patterns):
            bounce_type = "hard_bounce"
            category = "spam_complaint"
            should_suppress = True
            description = "Message flagged as spam"

        elif any(p in combined_text for p in hard_bounce_patterns):
            bounce_type = "hard_bounce"
            category = "invalid_recipient"
            should_suppress = True
            description = "Permanent delivery failure"

        elif any(p in combined_text for p in soft_bounce_patterns):
            bounce_type = "soft_bounce"
            category = "temporary_failure"
            should_suppress = False
            description = "Temporary delivery issue"

        else:
            # Default: treat unknown bounces as soft to avoid premature suppression
            bounce_type = "soft_bounce"
            category = "unknown"
            should_suppress = False
            description = f"Unclassified bounce (SMTP {smtp_code or 'unknown'})"

        return {
            "bounce_type": bounce_type,
            "category": category,
            "should_suppress": should_suppress,
            "description": description,
            "smtp_code": smtp_code,
            "original_data": bounce_data,
        }

    async def process_bounce_webhook(self, webhook_data: dict) -> dict:
        """Process an incoming bounce webhook from the mail server.

        Classifies the bounce, updates the database, and takes appropriate
        action (suppressing the prospect for hard bounces, etc.).

        Parameters
        ----------
        webhook_data : dict
            Webhook payload with email, smtp_code, smtp_response, message_id, etc.

        Returns
        -------
        dict
            Processing result with classification and actions taken.
        """
        email = webhook_data.get("email", "")
        message_id = webhook_data.get("message_id", "")

        logger.info("Processing bounce webhook for %s (message_id=%s)", email, message_id)

        # Classify the bounce
        classification = await self.classify_bounce(webhook_data)

        async with async_session_maker() as session:
            # Find the send log entry
            send_log = None
            if message_id:
                result = await session.execute(
                    select(SendLog).where(SendLog.message_id == message_id)
                )
                send_log = result.scalar_one_or_none()

            # Create bounce log entry
            bounce_log = BounceLog(
                id=uuid4(),
                send_log_id=send_log.id if send_log else None,
                prospect_id=send_log.prospect_id if send_log else None,
                email=email,
                bounce_type=classification["bounce_type"],
                bounce_category=classification["category"],
                smtp_error_code=classification.get("smtp_code"),
                smtp_response=webhook_data.get("smtp_response", "")[:500],
                processed=True,
            )
            session.add(bounce_log)

            actions_taken = []

            # Update SendLog if found
            if send_log:
                send_log.status = "bounced"
                send_log.bounced_at = datetime.utcnow()
                send_log.bounce_type = classification["bounce_type"]
                send_log.bounce_reason = classification["description"]
                send_log.smtp_response = webhook_data.get("smtp_response", "")[:500]
                actions_taken.append("updated_send_log")

                # Update CampaignProspect
                if send_log.campaign_id and send_log.prospect_id:
                    await session.execute(
                        update(CampaignProspect)
                        .where(CampaignProspect.campaign_id == send_log.campaign_id)
                        .where(CampaignProspect.prospect_id == send_log.prospect_id)
                        .values(
                            bounced=True,
                            status="bounced",
                        )
                    )
                    actions_taken.append("updated_campaign_prospect")

                    # Increment campaign bounce counter
                    await session.execute(
                        update(Campaign)
                        .where(Campaign.id == send_log.campaign_id)
                        .values(
                            bounced_count=Campaign.bounced_count + 1,
                            updated_at=datetime.utcnow(),
                        )
                    )
                    actions_taken.append("incremented_campaign_bounces")

            # For hard bounces, suppress the prospect entirely
            if classification["should_suppress"]:
                new_status = "do_not_contact" if classification["category"] == "spam_complaint" else "bounced"
                await session.execute(
                    update(Prospect)
                    .where(Prospect.email == email)
                    .values(
                        status=new_status,
                        updated_at=datetime.utcnow(),
                    )
                )
                actions_taken.append(f"suppressed_prospect:{new_status}")
                bounce_log.prospect_marked_bounced = True

            await session.commit()

        # Update real-time Redis counters
        if send_log and send_log.campaign_id:
            await redis_client.incr(f"tracking:stats:{send_log.campaign_id}:bounces")

        result = {
            "email": email,
            "message_id": message_id,
            "classification": classification,
            "actions_taken": actions_taken,
        }

        logger.info(
            "Bounce processed: email=%s type=%s suppress=%s actions=%s",
            email,
            classification["bounce_type"],
            classification["should_suppress"],
            actions_taken,
        )
        return result

    async def get_campaign_tracking_stats(self, campaign_id: str) -> dict:
        """Get comprehensive tracking stats for a campaign.

        Combines real-time Redis counters with database aggregates for
        a complete picture of campaign performance.

        Parameters
        ----------
        campaign_id : str
            Campaign UUID.

        Returns
        -------
        dict
            Stats including sent, delivered, opens, clicks, bounces, rates.
        """
        # Check cache first
        cache_key = f"tracking:stats_cache:{campaign_id}"
        cached = await redis_client.get_json(cache_key)
        if cached:
            return cached

        # Fetch from database
        async with async_session_maker() as session:
            # Campaign-level counts
            campaign_result = await session.execute(
                select(Campaign).where(Campaign.id == campaign_id)
            )
            campaign = campaign_result.scalar_one_or_none()
            if not campaign:
                return {"error": "Campaign not found"}

            # Detailed send log aggregates
            send_stats = await session.execute(
                select(
                    func.count(SendLog.id).label("total_sent"),
                    func.count(SendLog.delivered_at).label("total_delivered"),
                    func.sum(SendLog.open_count).label("total_opens"),
                    func.count(SendLog.first_open_at).label("unique_opens"),
                    func.sum(SendLog.click_count).label("total_clicks"),
                    func.count(SendLog.first_click_at).label("unique_clicks"),
                    func.count(SendLog.bounced_at).label("total_bounces"),
                    func.count(SendLog.replied_at).label("total_replies"),
                )
                .where(SendLog.campaign_id == campaign_id)
            )
            row = send_stats.one()

            total_sent = row.total_sent or 0
            total_delivered = row.total_delivered or 0
            unique_opens = row.unique_opens or 0
            unique_clicks = row.unique_clicks or 0
            total_bounces = row.total_bounces or 0
            total_replies = row.total_replies or 0

            # Calculate rates (based on delivered for accuracy)
            base = total_delivered if total_delivered > 0 else total_sent
            open_rate = (unique_opens / base * 100) if base > 0 else 0.0
            click_rate = (unique_clicks / base * 100) if base > 0 else 0.0
            bounce_rate = (total_bounces / total_sent * 100) if total_sent > 0 else 0.0
            reply_rate = (total_replies / base * 100) if base > 0 else 0.0
            click_to_open = (unique_clicks / unique_opens * 100) if unique_opens > 0 else 0.0

            # Bounce breakdown
            bounce_breakdown = await session.execute(
                select(
                    BounceLog.bounce_type,
                    func.count(BounceLog.id).label("count"),
                )
                .where(BounceLog.send_log_id.in_(
                    select(SendLog.id).where(SendLog.campaign_id == campaign_id)
                ))
                .group_by(BounceLog.bounce_type)
            )
            bounce_types = {row.bounce_type: row.count for row in bounce_breakdown.all()}

        stats = {
            "campaign_id": campaign_id,
            "campaign_name": campaign.name,
            "campaign_status": campaign.status,
            "total_prospects": campaign.total_prospects,
            "sent": total_sent,
            "delivered": total_delivered,
            "opens": {
                "total": row.total_opens or 0,
                "unique": unique_opens,
                "rate": round(open_rate, 2),
            },
            "clicks": {
                "total": row.total_clicks or 0,
                "unique": unique_clicks,
                "rate": round(click_rate, 2),
                "click_to_open_rate": round(click_to_open, 2),
            },
            "bounces": {
                "total": total_bounces,
                "rate": round(bounce_rate, 2),
                "breakdown": bounce_types,
            },
            "replies": {
                "total": total_replies,
                "rate": round(reply_rate, 2),
            },
            "unsubscribes": campaign.unsubscribed_count or 0,
            "delivery_rate": round(
                (total_delivered / total_sent * 100) if total_sent > 0 else 0.0, 2
            ),
            "computed_at": datetime.utcnow().isoformat(),
        }

        # Cache for 5 minutes
        await redis_client.set_json(cache_key, stats, ex=STATS_CACHE_TTL)

        return stats

    async def handle_unsubscribe(self, tracking_id: str) -> dict:
        """Process an unsubscribe request from a tracking link.

        Parameters
        ----------
        tracking_id : str
            Tracking identifier from the unsubscribe URL.

        Returns
        -------
        dict
            Result with prospect_email and actions taken.
        """
        mapping = await redis_client.get_json(f"tracking:{tracking_id}")
        if not mapping:
            return {"status": "unknown_tracking_id"}

        campaign_id = mapping["campaign_id"]
        prospect_id = mapping["prospect_id"]

        async with async_session_maker() as session:
            # Update prospect status
            result = await session.execute(
                select(Prospect).where(Prospect.id == prospect_id)
            )
            prospect = result.scalar_one_or_none()

            if not prospect:
                return {"status": "prospect_not_found"}

            prospect.status = "unsubscribed"
            prospect.updated_at = datetime.utcnow()

            # Update campaign prospect enrollment
            await session.execute(
                update(CampaignProspect)
                .where(CampaignProspect.campaign_id == campaign_id)
                .where(CampaignProspect.prospect_id == prospect_id)
                .values(
                    unsubscribed=True,
                    status="unsubscribed",
                )
            )

            # Increment unsubscribe counter
            await session.execute(
                update(Campaign)
                .where(Campaign.id == campaign_id)
                .values(
                    unsubscribed_count=Campaign.unsubscribed_count + 1,
                    updated_at=datetime.utcnow(),
                )
            )

            await session.commit()

        logger.info(
            "Unsubscribe processed: prospect=%s campaign=%s",
            prospect_id,
            campaign_id,
        )

        return {
            "status": "unsubscribed",
            "prospect_id": prospect_id,
            "prospect_email": prospect.email if prospect else "",
            "campaign_id": campaign_id,
        }

    # ------------------------------------------------------------------ #
    #  Internal database update helpers
    # ------------------------------------------------------------------ #

    async def _update_open_in_db(
        self,
        campaign_id: str,
        prospect_id: str,
        opened_at: datetime,
    ) -> None:
        """Update SendLog and CampaignProspect records for an open event."""
        async with async_session_maker() as session:
            # Update SendLog
            await session.execute(
                update(SendLog)
                .where(SendLog.campaign_id == campaign_id)
                .where(SendLog.prospect_id == prospect_id)
                .where(SendLog.first_open_at.is_(None))
                .values(
                    first_open_at=opened_at,
                    opened_at=opened_at,
                    open_count=SendLog.open_count + 1,
                    status="opened",
                )
            )

            # Also update if already opened (increment count)
            await session.execute(
                update(SendLog)
                .where(SendLog.campaign_id == campaign_id)
                .where(SendLog.prospect_id == prospect_id)
                .where(SendLog.first_open_at.isnot(None))
                .values(
                    opened_at=opened_at,
                    open_count=SendLog.open_count + 1,
                )
            )

            # Update CampaignProspect
            await session.execute(
                update(CampaignProspect)
                .where(CampaignProspect.campaign_id == campaign_id)
                .where(CampaignProspect.prospect_id == prospect_id)
                .values(opened=True)
            )

            # Update Campaign aggregate
            await session.execute(
                update(Campaign)
                .where(Campaign.id == campaign_id)
                .values(
                    opened_count=Campaign.opened_count + 1,
                    updated_at=datetime.utcnow(),
                )
            )

            await session.commit()

    async def _update_click_in_db(
        self,
        campaign_id: str,
        prospect_id: str,
        url: str,
        clicked_at: datetime,
    ) -> None:
        """Update SendLog and CampaignProspect records for a click event."""
        async with async_session_maker() as session:
            # Update SendLog
            await session.execute(
                update(SendLog)
                .where(SendLog.campaign_id == campaign_id)
                .where(SendLog.prospect_id == prospect_id)
                .where(SendLog.first_click_at.is_(None))
                .values(
                    first_click_at=clicked_at,
                    clicked_at=clicked_at,
                    click_count=SendLog.click_count + 1,
                    status="clicked",
                )
            )

            # Also update if already clicked (increment count)
            await session.execute(
                update(SendLog)
                .where(SendLog.campaign_id == campaign_id)
                .where(SendLog.prospect_id == prospect_id)
                .where(SendLog.first_click_at.isnot(None))
                .values(
                    clicked_at=clicked_at,
                    click_count=SendLog.click_count + 1,
                )
            )

            # Update CampaignProspect
            await session.execute(
                update(CampaignProspect)
                .where(CampaignProspect.campaign_id == campaign_id)
                .where(CampaignProspect.prospect_id == prospect_id)
                .values(clicked=True)
            )

            # Update Campaign aggregate
            await session.execute(
                update(Campaign)
                .where(Campaign.id == campaign_id)
                .values(
                    clicked_count=Campaign.clicked_count + 1,
                    updated_at=datetime.utcnow(),
                )
            )

            await session.commit()


# Singleton instance
tracking_service = TrackingService()
