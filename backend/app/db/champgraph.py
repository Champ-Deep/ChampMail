"""
ChampGraph HTTP client.

Talks to the graphiti-knowledge-graph-champ-graph container via its REST API.
All graph operations (prospects, companies, sequences, emails) are mapped
to ChampGraph's ingest / query / hooks endpoints.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class GraphDatabase:
    """ChampGraph HTTP client for the knowledge graph."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._base_url: str = ""
        self._api_key: str = ""
        self._connected: bool = False

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        self._base_url = settings.champgraph_url.rstrip("/")
        self._api_key = settings.champgraph_api_key
        self._client = httpx.AsyncClient(timeout=30.0)
        self._connected = True

    def disconnect(self) -> None:
        self._client = None
        self._connected = False

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self.connect()
        return self._client

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            h["X-API-Key"] = self._api_key
        return h

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------

    async def _get(self, path: str, params: dict | None = None) -> dict:
        r = await self.client.get(
            f"{self._base_url}{path}",
            headers=self._headers(),
            params=params,
        )
        r.raise_for_status()
        return r.json()

    async def _post(self, path: str, data: dict | None = None) -> dict:
        r = await self.client.post(
            f"{self._base_url}{path}",
            headers=self._headers(),
            json=data or {},
        )
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # Query — uses ChampGraph /api/query
    # ------------------------------------------------------------------

    async def query(self, query_text: str, account_name: str = "champmail") -> list[dict]:
        """
        Semantic query against ChampGraph.

        This replaces raw Cypher — ChampGraph does its own NL→graph resolution.
        """
        try:
            result = await self._post("/api/query", {
                "account": account_name,
                "query": query_text,
                "num_results": 50,
            })
            return self._flatten_query_result(result)
        except Exception as e:
            logger.warning("ChampGraph query failed: %s", e)
            return []

    def _flatten_query_result(self, result: dict) -> list[dict]:
        """Normalize ChampGraph query response into a flat list of dicts."""
        if not result.get("success"):
            return []
        data = result.get("data", {})
        items: list[dict] = []
        for node in data.get("nodes", []):
            items.append({
                "type": "node",
                "name": node.get("name", ""),
                "labels": node.get("labels", []),
                "summary": node.get("summary", ""),
                **{k: v for k, v in node.items() if k not in ("name", "labels", "summary")},
            })
        for edge in data.get("edges", []):
            items.append({
                "type": "edge",
                "fact": edge.get("fact", ""),
                "name": edge.get("name", ""),
                **{k: v for k, v in edge.items() if k not in ("fact", "name")},
            })
        return items or [data] if data else []

    # ------------------------------------------------------------------
    # Ingest — maps old create_* methods to ChampGraph /api/ingest
    # ------------------------------------------------------------------

    async def _ingest(self, content: str, name: str, account_name: str = "champmail", source: str = "champmail") -> dict:
        """Ingest a single episode into ChampGraph."""
        try:
            return await self._post("/api/ingest", {
                "account_name": account_name,
                "mode": "raw",
                "content": content,
                "name": name,
                "source_description": source,
            })
        except httpx.ConnectError:
            logger.warning("ChampGraph ingest failed: cannot connect to %s", self._base_url)
            return {"success": False, "error": f"Cannot connect to ChampGraph at {self._base_url}"}
        except Exception as e:
            logger.warning("ChampGraph ingest failed: %s: %s", type(e).__name__, e)
            return {"success": False, "error": f"{type(e).__name__}: {e}"}

    async def create_prospect(
        self,
        email: str,
        first_name: str = "",
        last_name: str = "",
        title: str = "",
        phone: str = "",
        linkedin_url: str = "",
        **extra_fields,
    ) -> dict:
        """Ingest a prospect into ChampGraph."""
        parts = [f"Prospect: {first_name} {last_name}".strip()]
        parts.append(f"Email: {email}")
        if title:
            parts.append(f"Title: {title}")
        if phone:
            parts.append(f"Phone: {phone}")
        if linkedin_url:
            parts.append(f"LinkedIn: {linkedin_url}")
        for k, v in extra_fields.items():
            if v:
                parts.append(f"{k}: {v}")

        content = "\n".join(parts)
        # Use email domain as account name for grouping
        account = email.split("@")[1] if "@" in email else "champmail"

        result = await self._ingest(
            content=content,
            name=f"Prospect: {first_name} {last_name} ({email})",
            account_name=account,
            source="prospect_import",
        )
        return {
            "p": {
                "properties": {
                    "email": email.lower(),
                    "first_name": first_name,
                    "last_name": last_name,
                    "title": title,
                    "phone": phone,
                    "linkedin_url": linkedin_url,
                },
            },
            "ingested": result.get("success", result.get("message", "") != ""),
        }

    async def get_prospect_by_email(self, email: str) -> dict | None:
        """Query ChampGraph for a prospect by email."""
        account = email.split("@")[1] if "@" in email else "champmail"
        results = await self.query(
            f"Find the prospect with email {email}. What is their role, company, and interaction history?",
            account_name=account,
        )
        if results:
            return {"p": results[0], "results": results}
        return None

    async def get_prospect_by_id(self, prospect_id: int) -> dict | None:
        """Query ChampGraph for a prospect by ID (best-effort semantic lookup)."""
        results = await self.query(f"Find prospect with ID {prospect_id}")
        if results:
            return {"p": results[0], "results": results}
        return None

    async def create_company(
        self,
        name: str,
        domain: str,
        industry: str = "",
        employee_count: int = 0,
        **extra_fields,
    ) -> dict:
        """Ingest a company into ChampGraph."""
        parts = [f"Company: {name}", f"Domain: {domain}"]
        if industry:
            parts.append(f"Industry: {industry}")
        if employee_count:
            parts.append(f"Employee Count: {employee_count}")
        for k, v in extra_fields.items():
            if v:
                parts.append(f"{k}: {v}")

        result = await self._ingest(
            content="\n".join(parts),
            name=f"Company: {name}",
            account_name=domain,
            source="company_import",
        )
        return {
            "c": {
                "properties": {"name": name, "domain": domain.lower(), "industry": industry},
            },
            "ingested": result.get("success", result.get("message", "") != ""),
        }

    async def link_prospect_to_company(
        self,
        prospect_email: str,
        company_domain: str,
        title: str = "",
        is_current: bool = True,
    ) -> dict:
        """Record the WORKS_AT relationship via ingest."""
        content = (
            f"Employment Record\n"
            f"Person: {prospect_email}\n"
            f"Company Domain: {company_domain}\n"
            f"Title: {title}\n"
            f"Current: {is_current}"
        )
        result = await self._ingest(
            content=content,
            name=f"Employment: {prospect_email} at {company_domain}",
            account_name=company_domain,
            source="employment_link",
        )
        return {"ingested": result.get("success", result.get("message", "") != "")}

    async def search_prospects(
        self,
        query_text: str = "",
        industry: str = "",
        limit: int = 50,
        skip: int = 0,
    ) -> list[dict]:
        """Search prospects via ChampGraph semantic query."""
        search = query_text or "all prospects"
        if industry:
            search += f" in {industry} industry"
        return await self.query(f"Find prospects: {search}")

    async def create_sequence(
        self,
        name: str,
        owner_id: str,
        steps_count: int = 0,
    ) -> dict:
        """Ingest an email sequence into ChampGraph."""
        content = (
            f"Email Sequence Created\n"
            f"Name: {name}\n"
            f"Owner: {owner_id}\n"
            f"Steps: {steps_count}\n"
            f"Status: draft"
        )
        result = await self._ingest(
            content=content,
            name=f"Sequence: {name}",
            account_name="champmail",
            source="sequence_creation",
        )
        return {
            "s": {
                "properties": {
                    "name": name,
                    "owner_id": owner_id,
                    "steps_count": steps_count,
                    "status": "draft",
                },
            },
            "ingested": result.get("success", result.get("message", "") != ""),
        }

    async def enroll_prospect_in_sequence(
        self,
        prospect_email: str,
        sequence_id: int,
    ) -> dict:
        """Record sequence enrollment via ingest."""
        content = (
            f"Sequence Enrollment\n"
            f"Prospect: {prospect_email}\n"
            f"Sequence ID: {sequence_id}\n"
            f"Status: active\n"
            f"Current Step: 1"
        )
        account = prospect_email.split("@")[1] if "@" in prospect_email else "champmail"
        result = await self._ingest(
            content=content,
            name=f"Enrollment: {prospect_email} → Sequence {sequence_id}",
            account_name=account,
            source="sequence_enrollment",
        )
        return {"ingested": result.get("success", result.get("message", "") != "")}

    async def record_email_sent(
        self,
        prospect_email: str,
        sequence_id: int,
        step_number: int,
        subject: str,
        body_hash: str,
    ) -> dict:
        """Record a sent email via the email hook endpoint."""
        account = prospect_email.split("@")[1] if "@" in prospect_email else "champmail"
        try:
            return await self._post("/api/hooks/email", {
                "from_address": "champmail@champmail.dev",
                "to_address": prospect_email,
                "subject": subject,
                "body": f"[Sequence {sequence_id}, Step {step_number}] body_hash={body_hash}",
                "direction": "outbound",
                "account_name": account,
            })
        except Exception as e:
            logger.warning("ChampGraph email hook failed: %s", e)
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Account-level intelligence (new — exposed from ChampGraph)
    # ------------------------------------------------------------------

    async def get_email_context(
        self,
        account_name: str,
        contact_email: str | None = None,
        contact_name: str | None = None,
        subject: str | None = None,
    ) -> dict:
        """Get full context for composing an email follow-up."""
        params: dict[str, str] = {}
        if contact_email:
            params["contact_email"] = contact_email
        if contact_name:
            params["contact_name"] = contact_name
        if subject:
            params["subject"] = subject
        try:
            return await self._get(f"/api/accounts/{account_name}/email-context", params)
        except Exception as e:
            logger.warning("ChampGraph email-context failed: %s", e)
            return {"success": False}

    async def get_account_briefing(self, account_name: str) -> dict:
        """Get pre-interaction briefing for an account."""
        try:
            return await self._get(f"/api/accounts/{account_name}/briefing")
        except Exception as e:
            logger.warning("ChampGraph briefing failed: %s", e)
            return {"success": False}

    async def get_stakeholder_map(self, account_name: str) -> dict:
        """Get stakeholder mapping for an account."""
        try:
            return await self._get(f"/api/accounts/{account_name}/intelligence/stakeholder-map")
        except Exception as e:
            logger.warning("ChampGraph stakeholder-map failed: %s", e)
            return {"success": False}

    async def get_engagement_gaps(self, account_name: str, days: int = 30) -> dict:
        """Find contacts not interacted with recently."""
        try:
            return await self._get(
                f"/api/accounts/{account_name}/intelligence/engagement-gaps",
                {"days": days},
            )
        except Exception as e:
            logger.warning("ChampGraph engagement-gaps failed: %s", e)
            return {"success": False}


# Global database instance
graph_db = GraphDatabase()


@asynccontextmanager
async def get_graph_db():
    """Dependency for getting graph database connection."""
    try:
        if not graph_db._connected:
            graph_db.connect()
        yield graph_db
    finally:
        pass  # httpx client handles connection pooling


def init_graph_db() -> bool:
    """Initialize graph database connection on startup.

    Returns:
        True if connection succeeded, False otherwise.
    """
    try:
        graph_db.connect()
        logger.info("ChampGraph client initialized: %s", settings.champgraph_url)
        return True
    except Exception as e:
        logger.warning("Could not initialize ChampGraph client: %s", e)
        logger.warning("Running in degraded mode - graph features disabled")
        return False


def close_graph_db():
    """Close graph database connection on shutdown."""
    graph_db.disconnect()
