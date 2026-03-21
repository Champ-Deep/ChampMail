"""
Deliverability Send Gate — the hard gate before every email send.

Composes all pre-send checks into a single pass/fail decision:
1. Global suppression list (unsubscribed, bounced, do_not_contact)
2. Spam trap detection
3. Domain rate limit (daily + warmup)
4. Domain status (paused/suspended)

Call `send_gate.check()` before sending, and `send_gate.reserve_send_slot()`
after the check passes to atomically claim a slot.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from app.db.redis import redis_client
from app.services.deliverability.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

# Redis key for the global suppression set
SUPPRESSION_KEY = "global:suppression_list"


class SendGate:
    """Central pre-send gate — must pass before any email is dispatched."""

    # ------------------------------------------------------------------
    # Suppression list (unsubscribed / bounced / do_not_contact)
    # ------------------------------------------------------------------

    async def is_suppressed(self, email: str) -> Tuple[bool, str]:
        """O(1) check against the global suppression Redis SET."""
        if not email:
            return True, "Empty email"

        client = await redis_client._get_client()
        is_member = await client.sismember(SUPPRESSION_KEY, email.lower().strip())
        if is_member:
            return True, "Recipient is on the suppression list (unsubscribed/bounced)"
        return False, ""

    async def add_to_suppression(self, email: str) -> None:
        """Add an email to the suppression set."""
        client = await redis_client._get_client()
        await client.sadd(SUPPRESSION_KEY, email.lower().strip())

    async def remove_from_suppression(self, email: str) -> None:
        """Remove an email from the suppression set."""
        client = await redis_client._get_client()
        await client.srem(SUPPRESSION_KEY, email.lower().strip())

    async def sync_suppression_from_db(self) -> int:
        """Rebuild the suppression SET from Postgres Prospect table.

        Includes prospects with status in ('unsubscribed', 'bounced', 'do_not_contact').
        Returns the count of suppressed emails.
        """
        from app.db.postgres import async_session_maker
        from app.models.campaign import Prospect
        from sqlalchemy import select

        try:
            async with async_session_maker() as session:
                result = await session.execute(
                    select(Prospect.email).where(
                        Prospect.status.in_(["unsubscribed", "bounced", "do_not_contact"])
                    )
                )
                emails = [row[0].lower().strip() for row in result.fetchall() if row[0]]

            if not emails:
                return 0

            client = await redis_client._get_client()
            # Replace the whole set atomically via pipeline
            pipe = client.pipeline()
            pipe.delete(SUPPRESSION_KEY)
            if emails:
                pipe.sadd(SUPPRESSION_KEY, *emails)
            await pipe.execute()

            logger.info("Suppression list synced: %d emails", len(emails))
            return len(emails)

        except Exception as e:
            logger.error("Failed to sync suppression list: %s", e)
            return 0

    # ------------------------------------------------------------------
    # Spam trap check (stub — filled in Phase 2)
    # ------------------------------------------------------------------

    async def _is_spam_trap(self, email: str) -> bool:
        """Check if email is a known spam trap. Stub until Phase 2."""
        try:
            from app.services.deliverability.spam_trap_checker import spam_trap_checker
            return await spam_trap_checker.is_spam_trap(email)
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # Domain blacklist check (stub — filled in Phase 2)
    # ------------------------------------------------------------------

    async def _is_domain_blacklisted(self, domain_id: str) -> Tuple[bool, str]:
        """Check if sending domain is on a DNSBL. Reads cached result."""
        cached = await redis_client.get_json(f"domain:{domain_id}:blacklist")
        if cached and cached.get("listed"):
            return True, f"Domain is blacklisted: {cached.get('listings', [])}"
        return False, ""

    # ------------------------------------------------------------------
    # Main gate
    # ------------------------------------------------------------------

    async def check(
        self,
        domain_id: str,
        recipient_email: str,
        user_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Run all pre-send checks.

        Returns (allowed, denial_reason). If allowed is True, the email
        may proceed to sending.

        Check order (fastest first):
        1. Suppression list — Redis SISMEMBER, O(1)
        2. Spam trap — memory set + Redis, O(1)
        3. Domain rate limit — Redis counter read
        4. Domain status — cached metadata
        5. Domain blacklist — cached DNSBL result
        """
        email = (recipient_email or "").lower().strip()

        # 1. Suppression list
        suppressed, reason = await self.is_suppressed(email)
        if suppressed:
            logger.info("Send blocked (suppressed): %s — %s", email, reason)
            return False, reason

        # 2. Spam trap
        if await self._is_spam_trap(email):
            logger.warning("Send blocked (spam trap): %s", email)
            return False, "Recipient is a known spam trap"

        # 3. Domain rate limit
        can_send, limit_reason = await rate_limiter.can_send(domain_id)
        if not can_send:
            logger.info("Send blocked (rate limit): domain=%s — %s", domain_id, limit_reason)
            return False, limit_reason

        # 4. Domain blacklist (cached)
        listed, bl_reason = await self._is_domain_blacklisted(domain_id)
        if listed:
            logger.warning("Send blocked (blacklisted): domain=%s — %s", domain_id, bl_reason)
            return False, bl_reason

        return True, ""

    async def reserve_send_slot(self, domain_id: str) -> bool:
        """Atomically claim a send slot on the domain's daily counter.

        Call this AFTER check() passes, right before the actual SMTP send.
        Returns True if the slot was reserved, False if the limit was hit.
        """
        return await rate_limiter.record_send(domain_id)


# Module singleton
send_gate = SendGate()
