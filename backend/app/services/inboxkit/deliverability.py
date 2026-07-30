"""InboxKit deliverability telemetry — Email Insights, InfraGuard, Inbox Placement.

Why this module exists
----------------------
`InboxKitProvider.health()` returned a fabricated snapshot:

    infraguard_clean = logical.value in ("ready", "warming", "sending")

That derives "is this mailbox healthy" from "did this mailbox finish being
created", which is not a health signal at all. Every downstream deliverability
decision — the IAL health gate, whether to keep sending through a mailbox, when
to quarantine one — rested on it.

InboxKit does publish the real data. Its API spans 70+ endpoints across 14
categories; ChampMail's client implements 11 across 4. Three of the unused
categories are exactly what the health gate needs:

  Email Insights   — per-mailbox bounce rate and engagement
  InfraGuard       — 50+ blacklist providers checked every 6h, DNS/auth drift,
                     bounce thresholds with alerting
  Inbox Placement  — measured placement % across major providers

Path verification status
------------------------
!! The endpoint paths below are NOT live-verified. !!

Every path in client.py carries a live-verified provenance comment (e.g.
`_MAILBOXES_LIST = "/v1/api/mailboxes/list"  # POST only (GET 404s)`) because
someone exercised it against a real key. These do not, because the public docs
expose endpoint *names* ("Get bounce metrics", "Get blacklist check history",
"Create Test") without their concrete paths, and docs.inboxkit.com only serves
the OpenAPI fragment for whichever page is fetched.

Rather than guess one path and silently return empty health forever, each
capability declares an ordered tuple of candidate paths. `_try_paths()` walks
them, remembers the first that answers, and caches it for the process. A 404 on
every candidate is logged once at WARNING and degrades that one field to None —
it never fakes a value and never raises into the send path.

To lock this down: run `python -m app.services.inboxkit.deliverability --probe`
with INBOXKIT_API_KEY set. It prints the winning path per capability; paste
those into the `_*_PATHS` tuples as single-element tuples with a verified-on
date, matching client.py's convention.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from .client import InboxKitAPIError, InboxKitClient

logger = logging.getLogger(__name__)

# --- candidate paths (UNVERIFIED — see module docstring) --------------------

_BOUNCE_METRICS_PATHS = (
    "/v1/api/email-insights/bounce-metrics",
    "/v1/api/insights/bounce-metrics",
    "/v1/api/email-insights/bounces",
)

_ENGAGEMENT_PATHS = (
    "/v1/api/email-insights/engagement",
    "/v1/api/insights/engagement",
    "/v1/api/email-insights/metrics",
)

_INFRAGUARD_STATUS_PATHS = (
    "/v1/api/infraguard/status",
    "/v1/api/infraguard/subscriptions",
    "/v1/api/infraguard/domains",
)

_BLACKLIST_PATHS = (
    "/v1/api/infraguard/blacklist-checks",
    "/v1/api/infraguard/blacklist",
    "/v1/api/infraguard/blacklist-history",
)

_PLACEMENT_PATHS = (
    "/v1/api/inbox-placement/tests",
    "/v1/api/placement/tests",
    "/v1/api/inbox-placement/results",
)

# Cache of capability -> path that answered, so the probe cost is paid once.
_resolved: dict[str, Optional[str]] = {}


class DeliverabilityClient:
    """Read-only telemetry reads. Never raises into a caller's send path."""

    def __init__(self, client: Optional[InboxKitClient] = None) -> None:
        from .client import get_client

        self._client = client or get_client()

    async def _try_paths(
        self,
        capability: str,
        paths: Iterable[str],
        *,
        params: Optional[dict] = None,
    ) -> Optional[dict]:
        """Return the first path that answers, or None if none do.

        A previously-resolved miss is cached as None so a deployment against an
        InboxKit plan without InfraGuard does not re-probe three URLs on every
        single health check.
        """
        if capability in _resolved:
            known = _resolved[capability]
            if known is None:
                return None
            try:
                return await self._client._request("GET", known, params=params)
            except InboxKitAPIError as exc:
                # The path worked before and doesn't now — forget it and re-probe.
                logger.info(
                    "inboxkit %s: cached path %s now returns %s; re-probing",
                    capability, known, exc.status,
                )
                _resolved.pop(capability, None)
            except Exception:
                logger.exception("inboxkit %s: request failed on %s", capability, known)
                return None

        for path in paths:
            try:
                result = await self._client._request("GET", path, params=params)
            except InboxKitAPIError as exc:
                if exc.status in (404, 405):
                    continue  # wrong guess — try the next candidate
                if exc.status in (401, 403):
                    logger.warning(
                        "inboxkit %s: %s -> HTTP %s (key lacks scope, or the "
                        "plan does not include this product)",
                        capability, path, exc.status,
                    )
                    _resolved[capability] = None
                    return None
                logger.warning("inboxkit %s: %s -> HTTP %s", capability, path, exc.status)
                continue
            except Exception:
                logger.exception("inboxkit %s: network failure on %s", capability, path)
                return None
            _resolved[capability] = path
            logger.info("inboxkit %s: resolved to %s", capability, path)
            return result

        _resolved[capability] = None
        logger.warning(
            "inboxkit %s: none of the candidate paths answered — this health "
            "field degrades to unknown. Run `python -m "
            "app.services.inboxkit.deliverability --probe` to discover the real "
            "path and pin it in _%s_PATHS.",
            capability, capability.upper(),
        )
        return None

    # --- individual capabilities -----------------------------------------

    async def bounce_rate(self, mailbox_uid: str) -> Optional[float]:
        """Bounce rate for one mailbox as a 0-1 fraction."""
        data = await self._try_paths(
            "bounce_metrics", _BOUNCE_METRICS_PATHS, params={"uid": mailbox_uid}
        )
        return _first_ratio(data, ("bounce_rate", "bounceRate", "bounce_percentage"))

    async def complaint_rate(self, mailbox_uid: str) -> Optional[float]:
        data = await self._try_paths(
            "engagement", _ENGAGEMENT_PATHS, params={"uid": mailbox_uid}
        )
        return _first_ratio(
            data, ("complaint_rate", "complaintRate", "spam_rate", "spamRate")
        )

    async def placement_pct(self, mailbox_uid: str) -> Optional[float]:
        """Inbox placement as a 0-100 percentage."""
        data = await self._try_paths(
            "placement", _PLACEMENT_PATHS, params={"uid": mailbox_uid}
        )
        pct = _first_number(
            data, ("inbox_placement", "placement_pct", "inboxRate", "inbox_rate")
        )
        if pct is None:
            return None
        # Accept either convention: some endpoints report 0-1, others 0-100.
        return pct * 100.0 if pct <= 1.0 else pct

    async def infraguard_clean(self, domain_name: str) -> Optional[bool]:
        """True when InfraGuard reports no blacklist or DNS problem.

        Returns None — explicitly "unknown" — when InfraGuard is not enabled for
        the domain. That is deliberately different from False: "we cannot see"
        must not read as "confirmed dirty" and pull a working mailbox out of
        rotation.
        """
        data = await self._try_paths(
            "blacklist", _BLACKLIST_PATHS, params={"domain": domain_name}
        )
        if data is None:
            return None
        listings = _coerce_list(data, ("listings", "blacklists", "results", "data"))
        if listings:
            return not any(_is_listed(entry) for entry in listings)
        flag = _first_bool(data, ("clean", "is_clean", "healthy"))
        return flag


# --- payload helpers -------------------------------------------------------
#
# InboxKit's response envelopes vary between endpoint families (some wrap in
# `data`, some return bare objects), and these fields are unverified, so every
# accessor is written to tolerate absence rather than assume a shape.


def _unwrap(data: Any) -> dict:
    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, dict):
            return inner
        return data
    return {}


def _first_number(data: Any, names: tuple[str, ...]) -> Optional[float]:
    body = _unwrap(data)
    for name in names:
        value = body.get(name)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _first_ratio(data: Any, names: tuple[str, ...]) -> Optional[float]:
    """A 0-1 fraction, normalising values that arrive as percentages."""
    value = _first_number(data, names)
    if value is None:
        return None
    return value / 100.0 if value > 1.0 else value


def _first_bool(data: Any, names: tuple[str, ...]) -> Optional[bool]:
    body = _unwrap(data)
    for name in names:
        value = body.get(name)
        if isinstance(value, bool):
            return value
    return None


def _coerce_list(data: Any, names: tuple[str, ...]) -> list:
    body = _unwrap(data)
    for name in names:
        value = body.get(name)
        if isinstance(value, list):
            return value
    return []


def _is_listed(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    for key in ("listed", "is_listed", "blacklisted"):
        if isinstance(entry.get(key), bool):
            return entry[key]
    status = str(entry.get("status", "")).lower()
    return status in ("listed", "blacklisted", "fail", "failed")


_deliverability_client: Optional[DeliverabilityClient] = None


def get_deliverability_client() -> DeliverabilityClient:
    global _deliverability_client
    if _deliverability_client is None:
        _deliverability_client = DeliverabilityClient()
    return _deliverability_client


# --- path discovery --------------------------------------------------------


async def probe() -> dict[str, Optional[str]]:
    """Probe every candidate path and report which one answers.

    Run with a real INBOXKIT_API_KEY to turn the guesses above into verified
    constants:

        python -m app.services.inboxkit.deliverability --probe
    """
    client = DeliverabilityClient()
    capabilities = {
        "bounce_metrics": _BOUNCE_METRICS_PATHS,
        "engagement": _ENGAGEMENT_PATHS,
        "infraguard_status": _INFRAGUARD_STATUS_PATHS,
        "blacklist": _BLACKLIST_PATHS,
        "placement": _PLACEMENT_PATHS,
    }
    found: dict[str, Optional[str]] = {}
    for name, paths in capabilities.items():
        _resolved.pop(name, None)
        await client._try_paths(name, paths)
        found[name] = _resolved.get(name)
    return found


if __name__ == "__main__":  # pragma: no cover
    import asyncio
    import sys

    if "--probe" not in sys.argv:
        print(__doc__)
        sys.exit(0)

    logging.basicConfig(level=logging.INFO)
    results = asyncio.run(probe())
    print("\nResolved paths (paste into the _*_PATHS tuples):")
    for capability, path in results.items():
        marker = path or "NOT FOUND — check plan entitlement or docs"
        print(f"  {capability:20s} {marker}")
    print(f"\nProbed at {datetime.now(timezone.utc).isoformat()}")
