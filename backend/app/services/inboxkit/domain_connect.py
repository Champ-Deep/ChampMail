"""Connect an EXISTING domain to InboxKit (bring-your-own-domain).

The gap this fills
------------------
`client.py` implements `/v1/api/domains/register` — buying a *fresh* domain
through InboxKit, which then owns its DNS end to end. There was no path at all
for "we already own championsmail.com, we only want to buy mailboxes on it".

That path needs InboxKit to be able to write DNS records on your domain, because
provisioning a Google Workspace or Microsoft 365 mailbox means setting MX, SPF
(TXT), DKIM (CNAME/TXT) and usually a verification TXT record. InboxKit exposes
a **Cloudflare Domains** category for exactly this: you delegate the domain's
DNS to Cloudflare, hand InboxKit a scoped Cloudflare API token, and it writes
the records itself.

Two modes are supported here, because not everyone will move DNS to Cloudflare:

  MANAGED  — give InboxKit a Cloudflare token; it writes every record itself.
             Fastest, and the only mode where provisioning is fully hands-off.

  MANUAL   — InboxKit returns the required records and you (or the lead) create
             them in whatever DNS provider you use, then trigger verification.
             Slower and needs a human, but it works with Route53, Namecheap,
             GoDaddy, anything.

Path verification status
------------------------
!! The endpoint paths below are NOT live-verified. !!

The public docs list this category and its operations by name — connect, list,
disconnect (5 endpoints) — but not their concrete paths, and docs.inboxkit.com
serves only the OpenAPI fragment for whichever page is fetched. Rather than
hardcode one guess, each operation declares ordered candidate paths and
`_resolve()` remembers whichever answers, exactly as
`deliverability.py` does.

To pin them down, with a real key set:

    INBOXKIT_API_KEY=... INBOXKIT_WORKSPACE_ID=... \\
        python -m app.services.inboxkit.domain_connect --probe

That prints the winning path per operation. Paste them into the `_*_PATHS`
tuples as single-element tuples with a verified-on date, matching client.py's
convention (`# verified live 2026-xx-xx`).

Security note on the Cloudflare token
-------------------------------------
The token is a credential that can rewrite your domain's DNS. It is accepted
here, forwarded to InboxKit over TLS, and **never persisted by ChampMail** —
there is deliberately no column for it. If InboxKit needs it again, the operator
re-supplies it. Storing a DNS-write token next to mailbox credentials would turn
one database compromise into a domain takeover.

Scope the token to the minimum before handing it over:
  Permissions : Zone → DNS → Edit
  Zone        : the single sending domain, never "All zones"
  TTL         : set an expiry; revoke once provisioning is confirmed
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Optional

from .client import InboxKitAPIError, InboxKitClient

logger = logging.getLogger(__name__)


# --- candidate paths (UNVERIFIED — see module docstring) --------------------

_CF_CONNECT_PATHS = (
    "/v1/api/cloudflare-domains/connect",
    "/v1/api/cloudflare/domains/connect",
    "/v1/api/domains/cloudflare/connect",
)

_CF_LIST_PATHS = (
    "/v1/api/cloudflare-domains/list",
    "/v1/api/cloudflare/domains/list",
    "/v1/api/domains/cloudflare/list",
)

_CF_DISCONNECT_PATHS = (
    "/v1/api/cloudflare-domains/disconnect",
    "/v1/api/cloudflare/domains/disconnect",
    "/v1/api/domains/cloudflare/disconnect",
)

_DNS_RECORDS_PATHS = (
    "/v1/api/dns/records",
    "/v1/api/domains/dns-records",
    "/v1/api/dns/list",
)

_DNS_VERIFY_PATHS = (
    "/v1/api/dns/validate",
    "/v1/api/dns/verify",
    "/v1/api/domains/verify-dns",
)

_resolved: dict[str, Optional[str]] = {}


class ConnectMode(str, Enum):
    """How DNS for a bring-your-own domain gets written."""

    MANAGED = "managed"   # InboxKit writes records via a Cloudflare token
    MANUAL = "manual"     # operator writes the records InboxKit specifies


@dataclass
class DnsRecord:
    """One DNS record the domain needs before mailboxes can be provisioned."""

    type: str                 # MX | TXT | CNAME
    name: str                 # host, e.g. "@" or "selector1._domainkey"
    value: str
    priority: Optional[int] = None   # MX only
    ttl: Optional[int] = None
    purpose: Optional[str] = None    # mx | spf | dkim | dmarc | verification

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "type": self.type,
            "name": self.name,
            "value": self.value,
        }
        if self.priority is not None:
            out["priority"] = self.priority
        if self.ttl is not None:
            out["ttl"] = self.ttl
        if self.purpose:
            out["purpose"] = self.purpose
        return out


@dataclass
class ConnectResult:
    """Outcome of a connect attempt."""

    domain: str
    mode: ConnectMode
    connected: bool
    domain_uid: Optional[str] = None
    native_status: Optional[str] = None
    records_required: list[DnsRecord] = field(default_factory=list)
    message: Optional[str] = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def needs_manual_dns(self) -> bool:
        """True when a human still has to create records before provisioning."""
        return bool(self.records_required)


class DomainConnectClient:
    """Attach an already-owned domain to an InboxKit workspace."""

    def __init__(self, client: Optional[InboxKitClient] = None) -> None:
        from .client import get_client

        self._client = client or get_client()

    # --- path resolution --------------------------------------------------

    async def _resolve(
        self,
        operation: str,
        paths: Iterable[str],
        *,
        method: str = "POST",
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> Optional[Any]:
        """Call the first candidate path that answers; None if none do."""
        if operation in _resolved:
            known = _resolved[operation]
            if known is None:
                return None
            try:
                return await self._client._request(method, known, json=json, params=params)
            except InboxKitAPIError as exc:
                if exc.status in (404, 405):
                    logger.info(
                        "inboxkit %s: cached path %s now %s — re-probing",
                        operation, known, exc.status,
                    )
                    _resolved.pop(operation, None)
                else:
                    raise

        for path in paths:
            try:
                result = await self._client._request(
                    method, path, json=json, params=params
                )
            except InboxKitAPIError as exc:
                if exc.status in (404, 405):
                    continue
                # A 4xx that isn't "wrong path" means we found the right path and
                # the *request* was rejected — record the path, re-raise so the
                # caller sees the real validation error rather than a silent None.
                _resolved[operation] = path
                raise
            _resolved[operation] = path
            logger.info("inboxkit %s: resolved to %s", operation, path)
            return result

        _resolved[operation] = None
        logger.warning(
            "inboxkit %s: no candidate path answered. Run `python -m "
            "app.services.inboxkit.domain_connect --probe` with a real key to "
            "discover the correct path and pin it.",
            operation,
        )
        return None

    # --- operations -------------------------------------------------------

    async def connect_managed(
        self,
        domain: str,
        *,
        cloudflare_api_token: str,
        cloudflare_account_id: Optional[str] = None,
        cloudflare_zone_id: Optional[str] = None,
    ) -> ConnectResult:
        """Hand InboxKit a Cloudflare token so it can write DNS itself.

        The token is forwarded and not stored. See the module docstring for the
        minimum scope it should carry.
        """
        if not cloudflare_api_token:
            raise ValueError("cloudflare_api_token is required for MANAGED mode")

        body: dict[str, Any] = {
            "domain_name": domain,
            "cloudflare_api_token": cloudflare_api_token,
        }
        if cloudflare_account_id:
            body["cloudflare_account_id"] = cloudflare_account_id
        if cloudflare_zone_id:
            body["cloudflare_zone_id"] = cloudflare_zone_id

        data = await self._resolve("cf_connect", _CF_CONNECT_PATHS, json=body)
        if data is None:
            return ConnectResult(
                domain=domain,
                mode=ConnectMode.MANAGED,
                connected=False,
                message=(
                    "Cloudflare connect endpoint not found — path needs pinning "
                    "(see module docstring) or the plan lacks this feature."
                ),
            )

        body_out = _unwrap(data)
        return ConnectResult(
            domain=domain,
            mode=ConnectMode.MANAGED,
            connected=_truthy(body_out, ("connected", "success", "ok")),
            domain_uid=_first_str(body_out, ("uid", "domain_uid", "id")),
            native_status=_first_str(body_out, ("status", "domain_status")),
            records_required=_parse_records(body_out),
            message=_first_str(body_out, ("message", "detail")),
        )

    async def required_records(self, domain: str) -> list[DnsRecord]:
        """The DNS records this domain needs, for MANUAL mode.

        Hand these to whoever controls DNS. Nothing is provisioned until they
        exist and `verify_dns()` passes.
        """
        data = await self._resolve(
            "dns_records", _DNS_RECORDS_PATHS, method="GET", params={"domain": domain}
        )
        if data is None:
            return []
        return _parse_records(_unwrap(data))

    async def verify_dns(self, domain: str) -> ConnectResult:
        """Ask InboxKit to re-check the domain's DNS.

        Call after records have been created manually. Safe to poll — this is a
        read plus a validation pass, not a mutation.
        """
        data = await self._resolve(
            "dns_verify", _DNS_VERIFY_PATHS, json={"domain_name": domain}
        )
        if data is None:
            return ConnectResult(
                domain=domain,
                mode=ConnectMode.MANUAL,
                connected=False,
                message="DNS verify endpoint not found — path needs pinning.",
            )
        body_out = _unwrap(data)
        return ConnectResult(
            domain=domain,
            mode=ConnectMode.MANUAL,
            connected=_truthy(body_out, ("valid", "verified", "connected", "success")),
            domain_uid=_first_str(body_out, ("uid", "domain_uid", "id")),
            native_status=_first_str(body_out, ("status", "domain_status")),
            records_required=_parse_records(body_out),
            message=_first_str(body_out, ("message", "detail")),
        )

    async def list_connected(self) -> list[dict]:
        """Domains already connected to this workspace."""
        data = await self._resolve("cf_list", _CF_LIST_PATHS, method="GET")
        if data is None:
            return []
        body_out = _unwrap(data)
        for key in ("domains", "results", "data", "items"):
            value = body_out.get(key)
            if isinstance(value, list):
                return value
        return []

    async def disconnect(self, domain: str) -> bool:
        """Detach a domain from InboxKit's DNS management.

        ! This does not delete mailboxes and does not remove DNS records — it
        ! stops InboxKit managing them. Mailboxes on the domain keep working
        ! until they are cancelled separately, so this is not a teardown.
        """
        data = await self._resolve(
            "cf_disconnect", _CF_DISCONNECT_PATHS, json={"domain_name": domain}
        )
        if data is None:
            return False
        return _truthy(_unwrap(data), ("disconnected", "success", "ok"))


# --- payload helpers -------------------------------------------------------


def _unwrap(data: Any) -> dict:
    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, dict):
            return inner
        return data
    return {}


def _first_str(body: dict, names: tuple[str, ...]) -> Optional[str]:
    for name in names:
        value = body.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def _truthy(body: dict, names: tuple[str, ...]) -> bool:
    for name in names:
        value = body.get(name)
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "ok", "success"):
            return True
    return False


def _parse_records(body: dict) -> list[DnsRecord]:
    """Pull DNS records out of whichever key the response used."""
    raw: list = []
    for key in ("records", "dns_records", "required_records", "missing_records"):
        value = body.get(key)
        if isinstance(value, list):
            raw = value
            break
    out: list[DnsRecord] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        rtype = entry.get("type") or entry.get("record_type")
        name = entry.get("name") or entry.get("host") or "@"
        value = entry.get("value") or entry.get("content") or entry.get("data")
        if not rtype or value is None:
            continue
        out.append(
            DnsRecord(
                type=str(rtype).upper(),
                name=str(name),
                value=str(value),
                priority=entry.get("priority"),
                ttl=entry.get("ttl"),
                purpose=entry.get("purpose") or entry.get("kind"),
            )
        )
    return out


_domain_connect_client: Optional[DomainConnectClient] = None


def get_domain_connect_client() -> DomainConnectClient:
    global _domain_connect_client
    if _domain_connect_client is None:
        _domain_connect_client = DomainConnectClient()
    return _domain_connect_client


# --- path discovery --------------------------------------------------------


async def probe() -> dict[str, Optional[str]]:
    """Discover which candidate path each operation actually lives at.

    Uses only read-shaped calls (list + records) so probing cannot mutate
    anything. Connect/disconnect paths are inferred from the list path's prefix,
    since the docs group them under one category.
    """
    client = DomainConnectClient()
    found: dict[str, Optional[str]] = {}

    _resolved.pop("cf_list", None)
    await client.list_connected()
    found["cf_list"] = _resolved.get("cf_list")

    _resolved.pop("dns_records", None)
    await client.required_records("example.com")
    found["dns_records"] = _resolved.get("dns_records")

    # Connect/disconnect are POSTs with side effects — never probed live.
    # Infer their prefix from whichever list path answered.
    if found["cf_list"]:
        prefix = found["cf_list"].rsplit("/", 1)[0]
        found["cf_connect (inferred)"] = f"{prefix}/connect"
        found["cf_disconnect (inferred)"] = f"{prefix}/disconnect"

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
    for operation, path in results.items():
        print(f"  {operation:28s} {path or 'NOT FOUND'}")
    print(f"\nProbed at {datetime.now(timezone.utc).isoformat()}")
    print(
        "\nNOTE: connect/disconnect are inferred, not probed — they have side "
        "effects. Confirm against the docs before relying on them."
    )
