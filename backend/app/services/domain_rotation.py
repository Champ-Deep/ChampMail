import logging
from typing import Optional
from app.db.postgres import async_session_maker
from app.services.domain_service import domain_service
from app.services.deliverability.rate_limiter import rate_limiter
from app.utils.test_mode import is_test_mode_enabled, get_test_mode_domain_id

logger = logging.getLogger(__name__)


class DomainRotator:
    def __init__(self):
        self.cache = {}

    async def select_domain(self, team_id: Optional[str] = None) -> str:
        """Select the domain with the most remaining capacity (via Redis counters)."""
        async with async_session_maker() as session:
            domains = await domain_service.get_verified_domains(session, team_id)

        if not domains:
            if is_test_mode_enabled():
                logger.warning("TEST MODE: No domains found, using test domain ID")
                return get_test_mode_domain_id()
            raise ValueError("No verified domains available for sending")

        best_domain = None
        best_remaining = -1

        for domain in domains:
            domain_id = str(domain["id"])
            remaining = await rate_limiter.get_remaining(domain_id)

            if remaining > best_remaining:
                best_remaining = remaining
                best_domain = domain

        if best_domain is None or best_remaining <= 0:
            raise ValueError("All domains have reached their daily limit")

        effective = await rate_limiter.get_effective_limit(str(best_domain["id"]))
        used = effective - best_remaining
        utilization = (used / effective * 100) if effective > 0 else 0

        logger.info(
            "Selected domain %s for sending (remaining: %d, utilization: %.1f%%)",
            best_domain["domain_name"], best_remaining, utilization,
        )
        return best_domain["id"]

    async def get_optimal_domain(self, prospect_count: int, team_id: Optional[str] = None) -> str:
        """Find the domain with enough capacity for the full prospect batch."""
        async with async_session_maker() as session:
            domains = await domain_service.get_verified_domains(session, team_id)

        candidates = []
        for domain in domains:
            domain_id = str(domain["id"])
            remaining = await rate_limiter.get_remaining(domain_id)
            if remaining >= prospect_count:
                candidates.append((domain, remaining))

        if not candidates:
            logger.info(
                "No domains with sufficient capacity for %d prospects, falling back to select_domain",
                prospect_count,
            )
            return await self.select_domain(team_id)

        # Pick the domain with the most remaining capacity
        candidates.sort(key=lambda x: x[1], reverse=True)
        optimal = candidates[0][0]
        logger.info(
            "Selected optimal domain %s for %d prospects (remaining: %d)",
            optimal["domain_name"], prospect_count, candidates[0][1],
        )
        return optimal["id"]


domain_rotator = DomainRotator()