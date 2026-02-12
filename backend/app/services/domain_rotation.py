import os
from typing import Optional
from app.db.postgres import async_session
from app.services.domain_service import domain_service


class DomainRotator:
    def __init__(self):
        self.cache = {}

    async def select_domain(self, team_id: Optional[str] = None) -> str:
        async def _select():
            async with async_session() as session:
                domains = await domain_service.get_verified_domains(session, team_id)

                if not domains:
                    raise ValueError("No verified domains available for sending")

                selected_domain = None
                lowest_utilization = float("inf")

                for domain in domains:
                    utilization = domain.sent_today / domain.daily_send_limit

                    if utilization < lowest_utilization:
                        lowest_utilization = utilization
                        selected_domain = domain

                    if utilization == 0:
                        break

                if selected_domain is None:
                    raise ValueError("All domains have reached their daily limit")

                return selected_domain.id

        return await _select()

    async def get_optimal_domain(self, prospect_count: int, team_id: Optional[str] = None) -> str:
        async def _get():
            async with async_session() as session:
                domains = await domain_service.get_verified_domains(session, team_id)

                candidates = []
                for domain in domains:
                    remaining_capacity = domain.daily_send_limit - domain.sent_today
                    if remaining_capacity >= prospect_count:
                        utilization = domain.sent_today / domain.daily_send_limit
                        candidates.append((domain, utilization))

                if not candidates:
                    return await self.select_domain(team_id)

                candidates.sort(key=lambda x: x[1])
                return candidates[0][0].id

        return await _get()


domain_rotator = DomainRotator()