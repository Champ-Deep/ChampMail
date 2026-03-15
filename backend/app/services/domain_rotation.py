import os
import logging
from typing import Optional
from app.db.postgres import async_session_maker
from app.services.domain_service import domain_service
from app.utils.test_mode import is_test_mode_enabled, get_test_mode_domain_id

logger = logging.getLogger(__name__)


class DomainRotator:
    def __init__(self):
        self.cache = {}

    async def select_domain(self, team_id: Optional[str] = None) -> str:
        async def _select():
            async with async_session_maker() as session:
                domains = await domain_service.get_verified_domains(session, team_id)

                if not domains:
                    # Test mode fallback: use test domain ID
                    if is_test_mode_enabled():
                        logger.warning("TEST MODE: No domains found, using test domain ID")
                        return get_test_mode_domain_id()
                    raise ValueError("No verified domains available for sending")

                selected_domain = None
                lowest_utilization = float("inf")

                for domain in domains:
                    utilization = domain["sent_today"] / domain["daily_send_limit"]

                    if utilization < lowest_utilization:
                        lowest_utilization = utilization
                        selected_domain = domain

                    if utilization == 0:
                        break

                if selected_domain is None:
                    raise ValueError("All domains have reached their daily limit")

                logger.info("Selected domain %s for sending (utilization: %.2f%%)",
                           selected_domain["domain_name"], lowest_utilization * 100)
                return selected_domain["id"]

        return await _select()

    async def get_optimal_domain(self, prospect_count: int, team_id: Optional[str] = None) -> str:
        async def _get():
            async with async_session_maker() as session:
                domains = await domain_service.get_verified_domains(session, team_id)

                candidates = []
                for domain in domains:
                    remaining_capacity = domain["daily_send_limit"] - domain["sent_today"]
                    if remaining_capacity >= prospect_count:
                        utilization = domain["sent_today"] / domain["daily_send_limit"]
                        candidates.append((domain, utilization))

                if not candidates:
                    logger.info("No domains with sufficient capacity for %d prospects, falling back to select_domain", prospect_count)
                    return await self.select_domain(team_id)

                candidates.sort(key=lambda x: x[1])
                optimal_domain = candidates[0][0]
                logger.info("Selected optimal domain %s for %d prospects (utilization: %.2f%%)",
                           optimal_domain["domain_name"], prospect_count, candidates[0][1] * 100)
                return optimal_domain["id"]

        return await _get()


domain_rotator = DomainRotator()