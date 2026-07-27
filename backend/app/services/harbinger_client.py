"""Contact-verification waterfall client for ChampHarbinger.

Wires new contacts entering cadence to Harbinger's owned-first enrichment
waterfall (POST /api/v1/enrich/waterfall) before personalize_emails() runs,
so a send never goes out to an address nobody has checked. Mirrors
champiq_emit.py's fire-and-forget shape: an unset or unreachable Harbinger
must never fail a campaign pipeline run.

Auth: Harbinger's v1 routes take `Authorization: Bearer chh_<key>`, a
per-workspace BYOK key validated against its own userApiKeys table (see
ChampHarbinger src/lib/api/validate-api-key.ts) - there is no shared secret
this process can derive one from. HARBINGER_API_KEY must be a real key
issued through Harbinger's own key-management route.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


async def verify_contact(prospect: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Run one prospect through Harbinger's waterfall.

    Returns the raw EnrichmentResult dict (contactId, status, resolvedTier,
    fields, confidenceScore, completenessScore, ...) or None when
    verification is unset, unreachable, or the prospect has no identifier
    Harbinger can use.
    """
    if not settings.harbinger_url or not settings.harbinger_api_key:
        return None

    body: dict[str, Any] = {"required_fields": ["email"]}
    if prospect.get("email"):
        body["email"] = prospect["email"]
    full_name = prospect.get("full_name") or " ".join(
        p for p in (prospect.get("first_name"), prospect.get("last_name")) if p
    )
    if full_name:
        body["name"] = full_name
    if prospect.get("company_name"):
        body["company"] = prospect["company_name"]
    if prospect.get("company_domain"):
        body["domain"] = prospect["company_domain"]
    if prospect.get("linkedin_url"):
        body["linkedin"] = prospect["linkedin_url"]

    if not any(k in body for k in ("email", "name", "company", "domain", "linkedin")):
        return None

    url = f"{settings.harbinger_url.rstrip('/')}/api/v1/enrich/waterfall"
    headers = {
        "Authorization": f"Bearer {settings.harbinger_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=body, headers=headers)
        if resp.status_code >= 400:
            logger.warning(
                "harbinger waterfall -> HTTP %s for prospect %s",
                resp.status_code,
                prospect.get("id"),
            )
            return None
        return resp.json()
    except Exception:
        logger.exception("harbinger waterfall call failed for prospect %s", prospect.get("id"))
        return None
