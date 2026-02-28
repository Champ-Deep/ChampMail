"""
Celery task for executing scheduled campaign sends.

Runs every 30 seconds via Celery Beat.
Scans Redis for scheduled sends that are due and executes them.
Includes retry logic with exponential backoff for failed sends.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from celery import shared_task

from app.db.redis import redis_client

logger = logging.getLogger(__name__)

MAX_RETRY_ATTEMPTS = 3
RETRY_DELAYS = [30, 120, 300]  # 30s, 2min, 5min


@shared_task(bind=True, name="execute_due_sends", max_retries=3, default_retry_delay=30)
def execute_due_sends_task(self) -> Dict[str, Any]:
    """Check for scheduled sends that are due and execute them.

    Runs every 30 seconds via Celery Beat.

    1. Scan Redis for campaign schedules
    2. For each schedule, find entries where send_at <= now() and status == "scheduled"
    3. Call campaign_send_service.execute_single_send() for each
    4. Handle failures: mark as "failed", log error, continue to next
    5. When all entries for a campaign are sent/failed → mark campaign COMPLETED
    """

    async def _execute():
        from app.services.campaign_send_service import campaign_send_service

        now = datetime.now(timezone.utc)

        cursor = 0
        processed_campaigns = set()
        total_sent = 0
        total_failed = 0

        while True:
            keys = await redis_client.redis.scan(
                cursor=cursor,
                match="campaign:*:schedule",
                count=100,
            )

            if not keys or len(keys) == 0:
                break

            cursor = keys[0]
            schedule_keys = keys[1]

            for schedule_key in schedule_keys:
                campaign_id = (
                    schedule_key.decode()
                    .replace("campaign:", "")
                    .replace(":schedule", "")
                )

                if campaign_id in processed_campaigns:
                    continue

                schedule_data = await redis_client.get_json(schedule_key.decode())
                if not schedule_data:
                    continue

                entries = schedule_data.get("entries", [])
                due_entries = [
                    e
                    for e in entries
                    if e.get("status") == "scheduled"
                    and datetime.fromisoformat(e["send_at"]).replace(
                        tzinfo=timezone.utc
                    )
                    <= now
                ]

                if not due_entries:
                    continue

                logger.info(
                    "Found %d due sends for campaign %s",
                    len(due_entries),
                    campaign_id,
                )

                for entry in due_entries:
                    prospect_id = entry.get("prospect_id")
                    retry_count = entry.get("retry_count", 0)

                    if not prospect_id:
                        continue

                    try:
                        result = await campaign_send_service.execute_single_send(
                            campaign_id=campaign_id,
                            prospect_id=prospect_id,
                        )

                        entry["status"] = "sent"
                        entry["sent_at"] = datetime.now(timezone.utc).isoformat()
                        total_sent += 1

                        logger.info(
                            "Sent email for campaign %s to prospect %s",
                            campaign_id,
                            prospect_id,
                        )

                    except Exception as e:
                        entry["retry_count"] = retry_count + 1

                        if retry_count < MAX_RETRY_ATTEMPTS - 1:
                            entry["status"] = "scheduled"
                            entry["error"] = str(e)
                            retry_delay = RETRY_DELAYS[retry_count]
                            entry["send_at"] = (
                                datetime.now(timezone.utc)
                                + timedelta(seconds=retry_delay)
                            ).isoformat()
                            logger.warning(
                                "Retry %d/%d for campaign %s prospect %s: %s",
                                retry_count + 1,
                                MAX_RETRY_ATTEMPTS,
                                campaign_id,
                                prospect_id,
                                str(e),
                            )
                        else:
                            entry["status"] = "failed"
                            entry["error"] = (
                                f"Failed after {MAX_RETRY_ATTEMPTS} attempts: {str(e)}"
                            )
                            total_failed += 1
                            logger.error(
                                "Failed to send for campaign %s to prospect %s after %d retries: %s",
                                campaign_id,
                                prospect_id,
                                MAX_RETRY_ATTEMPTS,
                                str(e),
                            )

                await redis_client.set_json(
                    f"campaign:{campaign_id}:schedule",
                    schedule_data,
                    ex=86400 * 7,
                )

                all_done = all(e.get("status") in ["sent", "failed"] for e in entries)
                if all_done:
                    await redis_client.set_json(
                        f"campaign:{campaign_id}:status",
                        {
                            "status": "completed",
                            "sent": total_sent,
                            "failed": total_failed,
                        },
                        ex=86400 * 7,
                    )
                    processed_campaigns.add(campaign_id)

            if cursor == 0:
                break

        return {
            "total_sent": total_sent,
            "total_failed": total_failed,
            "campaigns_processed": len(processed_campaigns),
        }

    try:
        return asyncio.run(_execute())
    except Exception as e:
        logger.error("execute_due_sends_task failed: %s", str(e))
        raise self.retry(exc=e)
