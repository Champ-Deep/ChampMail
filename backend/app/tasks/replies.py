"""
Celery task for campaign reply detection.

Runs every 5 minutes via Celery Beat.
Scans each user's IMAP mailbox for new replies and DSN bounces,
matches them to SendLog entries, and updates campaign stats.
"""

from __future__ import annotations

import asyncio
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="check_campaign_replies", queue="sending", max_retries=1)
def check_campaign_replies(self) -> dict:
    """Scan all users' IMAP mailboxes for replies and bounces.

    Delegates to CampaignReplyDetector.check_all_users() which:
    1. Loads all users with verified IMAP settings
    2. Connects to each user's IMAP
    3. Fetches new messages since last check (tracked via Redis UID)
    4. Matches In-Reply-To / References headers to SendLog.message_id
    5. Records replies (updates SendLog.replied_at, Campaign.replied_count)
    6. Detects DSN bounces and records them in BounceLog

    Returns
    -------
    dict
        Summary with users_checked, total_replies, total_bounces.
    """

    async def _check():
        from app.services.reply_detector import campaign_reply_detector

        return await campaign_reply_detector.check_all_users()

    try:
        return asyncio.run(_check())
    except Exception as exc:
        logger.error("check_campaign_replies failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=120)
