"""
Prospect Research Service.

Orchestrates per-prospect research: LinkedIn discovery, company/person enrichment
via Perplexity Sonar, knowledge graph storage, and model updates.

Reuses the existing ResearchService (Perplexity via OpenRouter) for web search.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.db.redis import redis_client

logger = logging.getLogger(__name__)

# LinkedIn URL pattern
LINKEDIN_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9_-]+/?",
    re.IGNORECASE,
)


class ProspectResearchService:
    """Research pipeline for individual prospects.

    Uses Perplexity Sonar (via OpenRouter) for web search, then stores
    findings in PostgreSQL (Prospect model) and FalkorDB (knowledge graph).
    """

    # ------------------------------------------------------------------
    # LinkedIn discovery
    # ------------------------------------------------------------------

    async def find_linkedin_url(self, prospect: Dict) -> Optional[str]:
        """Search the web for a prospect's LinkedIn profile URL.

        Uses Perplexity Sonar which has built-in web search capability.
        """
        from app.services.ai.openrouter_service import OpenRouterClient
        from app.core.config import settings

        first = prospect.get("first_name", "")
        last = prospect.get("last_name", "")
        company = prospect.get("company_name", "")
        title = prospect.get("job_title", "")

        name = f"{first} {last}".strip()
        if not name:
            return None

        parts = [f'"{name}"']
        if company:
            parts.append(f'"{company}"')
        if title:
            parts.append(title)
        parts.append("site:linkedin.com/in")

        query = " ".join(parts)

        client = OpenRouterClient()
        try:
            response = await client.chat_completion(
                model=settings.research_model,  # perplexity/sonar-pro
                messages=[{
                    "role": "user",
                    "content": (
                        f"Find the LinkedIn profile URL for this person. "
                        f"Search query: {query}\n\n"
                        f"Return ONLY the LinkedIn URL if found, or 'NOT_FOUND' if you cannot find it. "
                        f"The URL should look like: https://www.linkedin.com/in/username"
                    ),
                }],
                max_tokens=200,
                temperature=0.1,
            )

            # Extract LinkedIn URL from response
            match = LINKEDIN_URL_PATTERN.search(response)
            if match:
                url = match.group(0)
                logger.info("Found LinkedIn URL for %s: %s", name, url)
                return url

            logger.debug("No LinkedIn URL found for %s", name)
            return None

        except Exception as e:
            logger.warning("LinkedIn search failed for %s: %s", name, e)
            return None

    # ------------------------------------------------------------------
    # Full research flow
    # ------------------------------------------------------------------

    async def research_prospect(self, prospect_id: str) -> Dict[str, Any]:
        """Full research pipeline for a single prospect.

        1. Load prospect from Postgres
        2. If linkedin_url missing → search for it
        3. Run full company/person research via Perplexity
        4. Extract location + timezone from research data
        5. Store in FalkorDB knowledge graph
        6. Update Prospect model with enriched fields
        """
        from app.db.postgres import async_session_maker
        from app.models.campaign import Prospect
        from app.services.ai.openrouter_service import research_service
        from sqlalchemy import select, update

        # 1. Load prospect
        async with async_session_maker() as session:
            result = await session.execute(
                select(Prospect).where(Prospect.id == prospect_id)
            )
            prospect = result.scalar_one_or_none()
            if not prospect:
                return {"error": f"Prospect {prospect_id} not found"}

            prospect_data = {
                "id": str(prospect.id),
                "email": prospect.email,
                "first_name": prospect.first_name,
                "last_name": prospect.last_name,
                "company_name": prospect.company_name,
                "company_domain": prospect.company_domain,
                "job_title": prospect.job_title,
                "linkedin_url": prospect.linkedin_url,
                "title": prospect.job_title,
            }

        # 2. LinkedIn discovery
        linkedin_url = prospect_data.get("linkedin_url")
        linkedin_connection_status = None

        if not linkedin_url:
            linkedin_url = await self.find_linkedin_url(prospect_data)
            if linkedin_url:
                linkedin_connection_status = "pending"  # flag for manual review

        # 3. Full research via Perplexity Sonar
        research_data = await research_service.research_prospect(prospect_data)

        # 4. Extract location + timezone
        location = self._extract_location(research_data)
        tz = self._infer_timezone(location)

        # 5. Store in knowledge graph (best-effort)
        await self._store_in_graph(prospect_data, research_data)

        # 6. Update Prospect model
        update_values = {
            "research_status": "completed",
            "research_completed_at": datetime.now(timezone.utc),
        }
        if linkedin_url:
            update_values["linkedin_url"] = linkedin_url
        if linkedin_connection_status:
            update_values["linkedin_connection_status"] = linkedin_connection_status
        if location:
            update_values["location"] = location
        if tz:
            update_values["timezone"] = tz

        # Update bio/interests from research if available
        hooks = research_data.get("personalization_hooks", [])
        if hooks and isinstance(hooks, list):
            update_values["interests"] = hooks

        persona = research_data.get("persona_details", {})
        if persona.get("responsibilities"):
            bio_parts = []
            if prospect_data.get("job_title"):
                bio_parts.append(prospect_data["job_title"])
            if persona.get("responsibilities"):
                bio_parts.append(". ".join(persona["responsibilities"][:3]))
            if bio_parts:
                update_values["bio"] = " — ".join(bio_parts)

        async with async_session_maker() as session:
            await session.execute(
                update(Prospect)
                .where(Prospect.id == prospect_id)
                .values(**update_values)
            )
            await session.commit()

        logger.info(
            "Research complete for prospect %s (%s): location=%s, tz=%s, linkedin=%s",
            prospect_id, prospect_data.get("email"), location, tz, linkedin_url,
        )

        return {
            "prospect_id": prospect_id,
            "linkedin_url": linkedin_url,
            "location": location,
            "timezone": tz,
            "research_data": research_data,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_location(self, research_data: Dict) -> Optional[str]:
        """Extract location from research data."""
        # Try company_info first
        company_info = research_data.get("company_info", {})
        # Perplexity sometimes includes HQ location in description
        desc = company_info.get("description", "")

        # Try triggers for expansion/HQ signals
        triggers = research_data.get("triggers", {})
        expansion = triggers.get("expansion", "")

        # Look for common location patterns in the raw data
        raw = json.dumps(research_data).lower()

        # Common US tech hubs
        location_signals = {
            "san francisco": "San Francisco, CA",
            "new york": "New York, NY",
            "austin": "Austin, TX",
            "seattle": "Seattle, WA",
            "los angeles": "Los Angeles, CA",
            "chicago": "Chicago, IL",
            "boston": "Boston, MA",
            "denver": "Denver, CO",
            "miami": "Miami, FL",
            "atlanta": "Atlanta, GA",
            "london": "London, UK",
            "berlin": "Berlin, Germany",
            "paris": "Paris, France",
            "toronto": "Toronto, Canada",
            "sydney": "Sydney, Australia",
            "singapore": "Singapore",
            "tokyo": "Tokyo, Japan",
            "bangalore": "Bangalore, India",
            "mumbai": "Mumbai, India",
            "tel aviv": "Tel Aviv, Israel",
        }

        for signal, location in location_signals.items():
            if signal in raw:
                return location

        return None

    def _infer_timezone(self, location: Optional[str]) -> Optional[str]:
        """Map a location string to an IANA timezone."""
        if not location:
            return None

        location_lower = location.lower()

        # Direct mappings for common locations
        tz_map = {
            "san francisco": "America/Los_Angeles",
            "los angeles": "America/Los_Angeles",
            "seattle": "America/Los_Angeles",
            "denver": "America/Denver",
            "austin": "America/Chicago",
            "chicago": "America/Chicago",
            "new york": "America/New_York",
            "boston": "America/New_York",
            "miami": "America/New_York",
            "atlanta": "America/New_York",
            "london": "Europe/London",
            "berlin": "Europe/Berlin",
            "paris": "Europe/Paris",
            "toronto": "America/Toronto",
            "sydney": "Australia/Sydney",
            "singapore": "Asia/Singapore",
            "tokyo": "Asia/Tokyo",
            "bangalore": "Asia/Kolkata",
            "mumbai": "Asia/Kolkata",
            "tel aviv": "Asia/Jerusalem",
        }

        for city, tz in tz_map.items():
            if city in location_lower:
                return tz

        return None

    async def _store_in_graph(self, prospect_data: Dict, research_data: Dict) -> None:
        """Store research findings in FalkorDB knowledge graph (best-effort)."""
        try:
            from app.db.falkordb import graph_db

            if not graph_db.is_available():
                return

            email = prospect_data.get("email", "")
            if not email:
                return

            # Update prospect node with research data
            company_info = research_data.get("company_info", {})
            persona = research_data.get("persona_details", {})
            hooks = research_data.get("personalization_hooks", [])

            graph_db.update_prospect_research(
                email=email,
                research_data={
                    "bio": "; ".join(hooks) if hooks else "",
                    "interests": json.dumps(hooks) if hooks else "[]",
                    "responsibilities": "; ".join(persona.get("responsibilities", [])),
                    "challenges": "; ".join(persona.get("challenges", [])),
                },
            )

            # Update company node
            company_domain = prospect_data.get("company_domain", "")
            if company_domain and company_info:
                graph_db.update_company_details(
                    domain=company_domain,
                    details={
                        "industry": company_info.get("industry", ""),
                        "description": company_info.get("description", "")[:500],
                        "size": company_info.get("size", ""),
                        "revenue": company_info.get("revenue", ""),
                    },
                )

        except Exception as e:
            logger.warning("Failed to store research in graph: %s", e)

    # ------------------------------------------------------------------
    # Batch research
    # ------------------------------------------------------------------

    async def research_batch(
        self,
        prospect_ids: List[str],
        concurrency: int = 3,
        delay_seconds: float = 2.0,
    ) -> List[Dict]:
        """Research a batch of prospects with rate limiting."""
        import asyncio

        results = []
        semaphore = asyncio.Semaphore(concurrency)

        async def _research_one(pid: str):
            async with semaphore:
                result = await self.research_prospect(pid)
                await asyncio.sleep(delay_seconds)
                return result

        tasks = [_research_one(pid) for pid in prospect_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return [
            r if isinstance(r, dict) else {"error": str(r)}
            for r in results
        ]


# Module singleton
prospect_research_service = ProspectResearchService()
