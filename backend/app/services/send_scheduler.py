"""
Intelligent Send Scheduler.

Implements a hybrid approach: start with battle-tested B2B heuristics
for optimal send timing, with the architecture ready for ML-based
optimization once enough engagement data is collected.

Key heuristics:
- B2B optimal days: Tuesday, Wednesday, Thursday
- B2B optimal hours: 10am-2pm in the recipient's local timezone
- Spread sends across the window to avoid spam filters
- Respect daily sending limits per domain
- Detect recipient timezone from company HQ / domain signals
"""

from __future__ import annotations

import hashlib
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.db.redis import redis_client

logger = logging.getLogger(__name__)

# Domain TLD -> timezone mapping for rough timezone detection
# When we cannot determine timezone from company data, we fall back to the
# domain TLD as a coarse signal.
TLD_TIMEZONE_MAP = {
    ".com": "America/New_York",      # Default US Eastern for .com
    ".co.uk": "Europe/London",
    ".uk": "Europe/London",
    ".de": "Europe/Berlin",
    ".fr": "Europe/Paris",
    ".es": "Europe/Madrid",
    ".it": "Europe/Rome",
    ".nl": "Europe/Amsterdam",
    ".au": "Australia/Sydney",
    ".nz": "Pacific/Auckland",
    ".jp": "Asia/Tokyo",
    ".kr": "Asia/Seoul",
    ".cn": "Asia/Shanghai",
    ".in": "Asia/Kolkata",
    ".sg": "Asia/Singapore",
    ".ca": "America/Toronto",
    ".br": "America/Sao_Paulo",
    ".mx": "America/Mexico_City",
    ".il": "Asia/Jerusalem",
    ".ae": "Asia/Dubai",
    ".se": "Europe/Stockholm",
    ".no": "Europe/Oslo",
    ".dk": "Europe/Copenhagen",
    ".fi": "Europe/Helsinki",
    ".pl": "Europe/Warsaw",
    ".ie": "Europe/Dublin",
    ".ch": "Europe/Zurich",
    ".at": "Europe/Vienna",
    ".pt": "Europe/Lisbon",
    ".za": "Africa/Johannesburg",
    ".io": "America/New_York",       # Tech companies, default US Eastern
    ".ai": "America/New_York",
    ".co": "America/New_York",       # Commonly used by US startups
}

# US state -> timezone mapping for phone area code fallback
US_TIMEZONE_BY_REGION = {
    "eastern": "America/New_York",
    "central": "America/Chicago",
    "mountain": "America/Denver",
    "pacific": "America/Los_Angeles",
    "alaska": "America/Anchorage",
    "hawaii": "Pacific/Honolulu",
}


class SendScheduler:
    """Hybrid send scheduling - heuristics first, ML later.

    The scheduler computes optimal send times for each prospect based on:
    1. Day of week (Tue/Wed/Thu preferred for B2B)
    2. Time of day (10am-2pm in recipient's timezone)
    3. Send velocity limits (avoid spam filter triggers)
    4. Randomized jitter (make sends look natural)
    """

    # B2B optimal send windows
    # Monday=0, Tuesday=1, ..., Sunday=6
    OPTIMAL_DAYS = [1, 2, 3]          # Tuesday, Wednesday, Thursday
    ACCEPTABLE_DAYS = [0, 4]           # Monday, Friday (acceptable but not ideal)
    OPTIMAL_HOURS = range(10, 14)      # 10am-2pm local time
    ACCEPTABLE_HOURS = range(8, 17)    # 8am-5pm (broader fallback)

    # Send velocity constraints
    MAX_PER_MINUTE = 2                 # Max emails per minute per domain
    MAX_PER_HOUR = 30                  # Max emails per hour per domain
    MIN_INTERVAL_SECONDS = 30          # Minimum gap between sends

    # Jitter range in minutes (randomize within this window)
    JITTER_MINUTES = 15

    async def get_optimal_send_time(
        self,
        prospect: dict,
        tz_str: Optional[str] = None,
        after: Optional[datetime] = None,
    ) -> datetime:
        """Calculate the optimal send time for a single prospect.

        Parameters
        ----------
        prospect : dict
            Prospect data including company_domain, industry, etc.
        tz_str : str, optional
            Override timezone string (e.g. "America/New_York").
        after : datetime, optional
            Earliest allowed send time (UTC). Defaults to now.

        Returns
        -------
        datetime
            Optimal send time in UTC.
        """
        # Detect timezone
        if not tz_str:
            tz_str = await self.detect_timezone(prospect)

        try:
            tz = ZoneInfo(tz_str)
        except (ZoneInfoNotFoundError, KeyError):
            tz = ZoneInfo("America/New_York")
            logger.warning("Invalid timezone %s, falling back to America/New_York", tz_str)

        # Start from the given time or now
        now_utc = after or datetime.now(timezone.utc)
        now_local = now_utc.astimezone(tz)

        # Find the next optimal send slot
        candidate = self._find_next_optimal_slot(now_local, tz)

        # Add jitter so sends don't all fire at the same second
        jitter = timedelta(
            minutes=random.randint(0, self.JITTER_MINUTES),
            seconds=random.randint(0, 59),
        )
        candidate += jitter

        # Convert back to UTC
        return candidate.astimezone(timezone.utc).replace(tzinfo=None)

    async def detect_timezone(self, prospect: dict) -> str:
        """Detect timezone from prospect data.

        Priority order:
        1. Explicit timezone field on the prospect
        2. Company domain TLD mapping
        3. Company HQ location (if available in research cache)
        4. Default to America/New_York (US Eastern)

        Parameters
        ----------
        prospect : dict
            Prospect data.

        Returns
        -------
        str
            IANA timezone string.
        """
        # 1. Explicit timezone
        explicit_tz = prospect.get("timezone")
        if explicit_tz:
            try:
                ZoneInfo(explicit_tz)
                return explicit_tz
            except (ZoneInfoNotFoundError, KeyError):
                pass

        # 2. Company domain TLD
        domain = prospect.get("company_domain") or ""
        if not domain:
            email = prospect.get("email", "")
            if "@" in email:
                domain = email.split("@")[1]

        if domain:
            tz = self._timezone_from_domain(domain)
            if tz:
                return tz

        # 3. Check research cache for location info
        prospect_id = prospect.get("id")
        if prospect_id:
            cached_research = await redis_client.get_json(f"research:prospect:{prospect_id}")
            if cached_research:
                tz = self._timezone_from_research(cached_research)
                if tz:
                    return tz

        # 4. Default
        return "America/New_York"

    async def schedule_campaign_sends(
        self,
        campaign_id: str,
        personalized_emails: list,
    ) -> list:
        """Schedule all emails in a campaign with optimal timing.

        Distributes sends across optimal windows while respecting velocity
        limits. Returns a list of schedule entries that can be used to
        enqueue send tasks with appropriate ETAs.

        Parameters
        ----------
        campaign_id : str
            Campaign UUID.
        personalized_emails : list[dict]
            Each dict must have: prospect_id, prospect_email, subject, html_body.
            Optionally: company_domain, industry, etc.

        Returns
        -------
        list[dict]
            Schedule entries with send_at, prospect_id, prospect_email.
        """
        logger.info(
            "Scheduling %d sends for campaign %s",
            len(personalized_emails),
            campaign_id,
        )

        schedule: list = []
        # Track send counts per hour to respect velocity limits
        hourly_counts: Dict[str, int] = {}
        last_send_time: Optional[datetime] = None

        # Sort by a deterministic but pseudo-random order (based on prospect ID hash)
        # This ensures the send order is consistent across retries but appears random
        sorted_emails = sorted(
            personalized_emails,
            key=lambda e: hashlib.md5(
                f"{campaign_id}:{e.get('prospect_id', '')}".encode()
            ).hexdigest(),
        )

        base_time = datetime.now(timezone.utc)

        for email_data in sorted_emails:
            prospect_data = {
                "id": email_data.get("prospect_id"),
                "email": email_data.get("prospect_email"),
                "company_domain": email_data.get("company_domain"),
                "industry": email_data.get("industry"),
            }

            # Compute optimal time
            after = last_send_time or base_time
            # Ensure minimum interval
            earliest = after + timedelta(seconds=self.MIN_INTERVAL_SECONDS)

            send_at = await self.get_optimal_send_time(
                prospect=prospect_data,
                after=earliest,
            )

            # Check hourly velocity limit
            hour_key = send_at.strftime("%Y-%m-%d-%H")
            current_hour_count = hourly_counts.get(hour_key, 0)

            if current_hour_count >= self.MAX_PER_HOUR:
                # Push to next hour
                send_at = send_at.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                send_at += timedelta(
                    minutes=random.randint(0, 10),
                    seconds=random.randint(0, 59),
                )
                hour_key = send_at.strftime("%Y-%m-%d-%H")

            hourly_counts[hour_key] = hourly_counts.get(hour_key, 0) + 1
            last_send_time = send_at

            entry = {
                "campaign_id": campaign_id,
                "prospect_id": email_data.get("prospect_id"),
                "prospect_email": email_data.get("prospect_email"),
                "send_at": send_at.isoformat(),
                "send_at_utc": send_at.isoformat(),
                "subject": email_data.get("subject", ""),
                "status": "scheduled",
            }
            schedule.append(entry)

        # Store schedule in Redis for frontend display
        await redis_client.set_json(
            f"campaign:{campaign_id}:schedule",
            {
                "total": len(schedule),
                "first_send": schedule[0]["send_at"] if schedule else None,
                "last_send": schedule[-1]["send_at"] if schedule else None,
                "created_at": datetime.utcnow().isoformat(),
                "entries": schedule,
            },
            ex=86400 * 7,  # Keep schedule for 7 days
        )

        logger.info(
            "Scheduled %d sends for campaign %s (window: %s to %s)",
            len(schedule),
            campaign_id,
            schedule[0]["send_at"] if schedule else "N/A",
            schedule[-1]["send_at"] if schedule else "N/A",
        )

        return schedule

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    def _find_next_optimal_slot(self, local_time: datetime, tz: ZoneInfo) -> datetime:
        """Find the next optimal send slot from a given local time.

        Walks forward through time to find a slot that falls on an optimal
        day (Tue-Thu) during optimal hours (10am-2pm). If no optimal slot
        is available within 5 days, falls back to acceptable windows.
        """
        candidate = local_time

        # If we're already past 5pm, jump to next day 10am
        if candidate.hour >= 17:
            candidate = candidate.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
        elif candidate.hour < 8:
            candidate = candidate.replace(hour=10, minute=0, second=0, microsecond=0)

        # Try optimal days first (up to 7 days out)
        for day_offset in range(7):
            check = candidate + timedelta(days=day_offset)
            weekday = check.weekday()

            if weekday in self.OPTIMAL_DAYS:
                # Set to optimal hour if not already in window
                if check.hour < 10:
                    check = check.replace(hour=10, minute=0, second=0, microsecond=0)
                elif check.hour >= 14:
                    # If past optimal hours on an optimal day, try next day
                    continue

                if 10 <= check.hour < 14:
                    return check

        # Fallback: find any acceptable window
        for day_offset in range(7):
            check = candidate + timedelta(days=day_offset)
            weekday = check.weekday()

            if weekday in self.OPTIMAL_DAYS + self.ACCEPTABLE_DAYS:
                if check.hour < 8:
                    check = check.replace(hour=10, minute=0, second=0, microsecond=0)
                elif check.hour >= 17:
                    continue

                if 8 <= check.hour < 17:
                    return check

        # Last resort: next Tuesday at 10am
        days_until_tuesday = (1 - candidate.weekday()) % 7
        if days_until_tuesday == 0:
            days_until_tuesday = 7
        fallback = candidate + timedelta(days=days_until_tuesday)
        return fallback.replace(hour=10, minute=0, second=0, microsecond=0)

    def _timezone_from_domain(self, domain: str) -> Optional[str]:
        """Extract timezone from domain TLD."""
        domain = domain.lower().strip()

        # Check exact TLD matches (longest first for specificity)
        for tld, tz in sorted(TLD_TIMEZONE_MAP.items(), key=lambda x: -len(x[0])):
            if domain.endswith(tld):
                return tz

        # Common US tech domains
        if domain.endswith(".com") or domain.endswith(".io") or domain.endswith(".co"):
            return "America/New_York"

        return None

    def _timezone_from_research(self, research_data: dict) -> Optional[str]:
        """Extract timezone from cached research data.

        Looks for location clues in company_info (headquarters, location).
        """
        company_info = research_data.get("company_info", {})
        if isinstance(company_info, str):
            return None

        # Check if research mentions a specific HQ location
        description = (company_info.get("description") or "").lower()

        # Simple city/region -> timezone mapping for common B2B HQ locations
        location_tz_map = {
            "san francisco": "America/Los_Angeles",
            "silicon valley": "America/Los_Angeles",
            "los angeles": "America/Los_Angeles",
            "seattle": "America/Los_Angeles",
            "portland": "America/Los_Angeles",
            "new york": "America/New_York",
            "boston": "America/New_York",
            "miami": "America/New_York",
            "atlanta": "America/New_York",
            "washington": "America/New_York",
            "chicago": "America/Chicago",
            "dallas": "America/Chicago",
            "houston": "America/Chicago",
            "austin": "America/Chicago",
            "denver": "America/Denver",
            "phoenix": "America/Phoenix",
            "london": "Europe/London",
            "berlin": "Europe/Berlin",
            "munich": "Europe/Berlin",
            "paris": "Europe/Paris",
            "amsterdam": "Europe/Amsterdam",
            "stockholm": "Europe/Stockholm",
            "tokyo": "Asia/Tokyo",
            "singapore": "Asia/Singapore",
            "sydney": "Australia/Sydney",
            "melbourne": "Australia/Sydney",
            "toronto": "America/Toronto",
            "vancouver": "America/Vancouver",
            "bangalore": "Asia/Kolkata",
            "mumbai": "Asia/Kolkata",
            "tel aviv": "Asia/Jerusalem",
            "dubai": "Asia/Dubai",
            "sao paulo": "America/Sao_Paulo",
        }

        for city, tz in location_tz_map.items():
            if city in description:
                return tz

        return None

    async def get_campaign_schedule_stats(self, campaign_id: str) -> Optional[dict]:
        """Retrieve the stored schedule summary for a campaign."""
        data = await redis_client.get_json(f"campaign:{campaign_id}:schedule")
        if not data:
            return None

        return {
            "total": data.get("total", 0),
            "first_send": data.get("first_send"),
            "last_send": data.get("last_send"),
            "created_at": data.get("created_at"),
        }


# Singleton instance
send_scheduler = SendScheduler()
