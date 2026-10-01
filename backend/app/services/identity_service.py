"""Identity spine — stable person_id + external_ids across the Champ suite.

Today a prospect is keyed only on `email`, which breaks on job-changes, role
accounts, and cross-source dedup. This adds a suite-global `person_id` (and
`account_id` for the company) plus an `external_ids` map
({lake_id, linkedin_urn, clerk_id, champutm_visitor_id, email_sha256, domain}).

In production ids are minted/resolved by ChampGraph/Graphiti (it already does
temporal entity resolution). When ChampGraph isn't wired, this derives a STABLE
deterministic id locally (UUIDv5 over the strongest available natural key:
linkedin_urn > lake_id > email), so re-imports of the same person collapse to one
id without a live ChampGraph. The derivation is pure → unit-tested offline.
"""
from __future__ import annotations

import hashlib
import re
import uuid

# Fixed namespaces so ids are stable across processes/runs.
_PERSON_NS = uuid.UUID("a3f1c2d4-0001-4a2b-9c3d-1e2f3a4b5c6d")
_ACCOUNT_NS = uuid.UUID("a3f1c2d4-0002-4a2b-9c3d-1e2f3a4b5c6d")

# Priority order of natural keys for person identity (strongest first).
_PERSON_KEY_ORDER = ("linkedin_urn", "lake_id", "clerk_id", "email")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def email_sha256(email: str) -> str:
    return hashlib.sha256(normalize_email(email).encode()).hexdigest()


def normalize_linkedin(url: str) -> str:
    """Reduce a LinkedIn URL/URN to a stable slug key."""
    if not url:
        return ""
    m = re.search(r"linkedin\.com/in/([^/?#]+)", url, re.IGNORECASE)
    if m:
        return "in/" + m.group(1).lower()
    m = re.search(r"urn:li:person:([\w-]+)", url, re.IGNORECASE)
    if m:
        return "person/" + m.group(1)
    return url.strip().lower()


def domain_of(email: str, fallback: str = "") -> str:
    e = normalize_email(email)
    if "@" in e:
        return e.rsplit("@", 1)[1]
    return (fallback or "").strip().lower()


def derive_person_id(external_ids: dict | None, email: str = "") -> str:
    """Deterministic person_id from the strongest available natural key.

    Same person (same linkedin_urn, or same email when no urn) → same id, so
    repeated imports dedup. Returns a UUID string.
    """
    ext = dict(external_ids or {})
    for key in _PERSON_KEY_ORDER:
        val = ext.get(key) or (email if key == "email" else "")
        if not val:
            continue
        if key == "linkedin_urn":
            val = normalize_linkedin(val)
        elif key == "email":
            val = normalize_email(val)
        if val:
            return str(uuid.uuid5(_PERSON_NS, f"{key}:{val}"))
    # Last resort: random (no natural key at all).
    return str(uuid.uuid4())


def derive_account_id(company_domain: str = "", email: str = "") -> str:
    dom = (company_domain or "").strip().lower() or domain_of(email)
    if not dom:
        return ""
    return str(uuid.uuid5(_ACCOUNT_NS, f"domain:{dom}"))


def build_external_ids(*, email: str = "", linkedin_url: str = "",
                       lake_id: str = "", clerk_id: str = "",
                       champutm_visitor_id: str = "",
                       existing: dict | None = None) -> dict:
    """Assemble/merge the external_ids map. Never drops existing keys."""
    out = dict(existing or {})
    if email:
        out["email_sha256"] = email_sha256(email)
        out.setdefault("domain", domain_of(email))
    if linkedin_url:
        out["linkedin_urn"] = normalize_linkedin(linkedin_url)
    if lake_id:
        out["lake_id"] = lake_id
    if clerk_id:
        out["clerk_id"] = clerk_id
    if champutm_visitor_id:
        out["champutm_visitor_id"] = champutm_visitor_id
    return out


def resolve_identity(*, email: str = "", linkedin_url: str = "",
                     company_domain: str = "", lake_id: str = "",
                     clerk_id: str = "", champutm_visitor_id: str = "",
                     existing_external_ids: dict | None = None) -> dict:
    """One call → {person_id, account_id, external_ids} for upsert."""
    ext = build_external_ids(
        email=email, linkedin_url=linkedin_url, lake_id=lake_id,
        clerk_id=clerk_id, champutm_visitor_id=champutm_visitor_id,
        existing=existing_external_ids,
    )
    return {
        "person_id": derive_person_id(ext, email),
        "account_id": derive_account_id(company_domain, email),
        "external_ids": ext,
    }
