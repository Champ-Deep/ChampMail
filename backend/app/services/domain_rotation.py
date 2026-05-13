from typing import Optional
from app.db.postgres import async_session_maker as async_session
from app.services.domain_service import domain_service
from app.services.warmup_schedule import effective_daily_limit


class DomainRotator:
    async def select_domain(self, team_id: Optional[str] = None) -> Optional[str]:
        async with async_session() as session:
            domains = await domain_service.get_verified_domains(session, team_id)

            if not domains:
                return None

            selected = None
            lowest_utilization = float("inf")

            for domain in domains:
                # Skip paused or blacklisted domains
                if domain.get("paused") or domain.get("blacklisted"):
                    continue

                cap = effective_daily_limit(domain)
                sent = domain.get("sent_today", 0)

                if sent >= cap:
                    continue  # This domain is at its warmup/daily limit

                utilization = sent / max(cap, 1)
                if utilization < lowest_utilization:
                    lowest_utilization = utilization
                    selected = domain

                if utilization == 0:
                    break

            return selected["id"] if selected else None

    async def get_optimal_domain(self, prospect_count: int, team_id: Optional[str] = None) -> Optional[str]:
        async with async_session() as session:
            domains = await domain_service.get_verified_domains(session, team_id)

            candidates = []
            for domain in domains:
                if domain.get("paused") or domain.get("blacklisted"):
                    continue

                cap = effective_daily_limit(domain)
                remaining = cap - domain.get("sent_today", 0)

                if remaining >= prospect_count:
                    utilization = domain.get("sent_today", 0) / max(cap, 1)
                    candidates.append((domain, utilization))

            if not candidates:
                return await self.select_domain(team_id)

            candidates.sort(key=lambda x: x[1])
            return candidates[0][0]["id"]


domain_rotator = DomainRotator()
