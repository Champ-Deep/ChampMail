"""Cloudflare DNS automation for a new sending domain: SPF, DMARC, the provider's DKIM CNAMEs and the
`track.<domain>` CNAME to the edge Worker, plus the per-zone Worker route that makes the CNAME serve.

All-or-nothing: every object created is remembered, and a failure on any later step deletes them in reverse
order before `CloudflareError` is raised (the v2 donor left the first records behind). A record that already
exists at the name (an SPF or DMARC TXT) is left alone, not duplicated: two SPF records is a permerror.
Only runs when CLOUDFLARE_API_TOKEN is set and the zone is already in the account; otherwise `provision`
returns None and nothing is touched.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx
from sqlalchemy import select

from app.config import get_settings
from app.models import Domain
from app.services import mx_checks as mx

log = logging.getLogger("champmail.cloudflare")
API = "https://api.cloudflare.com/client/v4"
PUBLIC_RESOLVERS = (["1.1.1.1"], ["8.8.8.8"])


class CloudflareError(Exception):
    """A Cloudflare call failed. Anything already created has been deleted by the time this is raised."""


@dataclass
class Record:
    type: str
    name: str
    content: str
    proxied: bool = False


def spf_value(platform: Optional[str]) -> str:
    return f"v=spf1 include:{mx.SPF_INCLUDE[mx.platform(platform) or 'google']} ~all"


def dmarc_value(brand_id: Optional[str]) -> str:
    rua = get_settings().dmarc_rua_address.replace("{brand}", brand_id or "default").strip()
    return "v=DMARC1; p=quarantine" + (f"; rua=mailto:{rua}" if rua else "")


def plan(domain: str, brand_id: Optional[str], platform: Optional[str], dkim: list[tuple[str, str]]) -> list[Record]:
    """The records to create, in creation order."""
    s = get_settings()
    return [Record("TXT", domain, spf_value(platform)), Record("TXT", f"_dmarc.{domain}", dmarc_value(brand_id)),
            *[Record("CNAME", n if n.endswith(domain) else f"{n}.{domain}", v) for n, v in dkim],
            Record("CNAME", f"track.{domain}", s.edge_worker_hostname, proxied=True)]  # proxied: a Worker route only runs behind the proxy


async def _call(http: httpx.AsyncClient, method: str, path: str, **kw) -> dict:
    try:
        r = await http.request(method, f"{API}{path}", **kw)
        body = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise CloudflareError(f"{method} {path}: {e}") from e
    if r.status_code >= 400 or not body.get("success", False):
        raise CloudflareError(f"{method} {path}: HTTP {r.status_code} {body.get('errors')}")
    return body


async def _rollback(http: httpx.AsyncClient, created: list[str]) -> None:
    for path in reversed(created):
        try:
            await _call(http, "DELETE", path)
        except CloudflareError:
            log.exception("rollback could not delete %s; remove it by hand", path)


async def provision(domain: str, brand_id: Optional[str], platform: Optional[str], dkim: list[tuple[str, str]],
                    http: Optional[httpx.AsyncClient] = None) -> Optional[list[Record]]:
    """Create the records. The records created, or None when automation is off or the zone is not in the account."""
    s = get_settings()
    token = s.cloudflare_api_token.strip()
    if not token:
        return None
    if not s.edge_worker_hostname:
        raise CloudflareError("EDGE_WORKER_HOSTNAME is not set; the track CNAME has no target")
    own = http is None
    http = http or httpx.AsyncClient(timeout=15)
    http.headers["Authorization"] = f"Bearer {token}"
    created: list[str] = []
    try:
        zones = (await _call(http, "GET", "/zones", params={"name": domain}))["result"]
        if not zones:
            log.info("cloudflare: zone %s is not in this account; DNS automation skipped", domain)
            return None
        zone = zones[0]["id"]
        made = []
        for rec in plan(domain, brand_id, platform, dkim):
            if rec.type == "TXT":  # leave an existing SPF/DMARC alone
                tag = rec.content.split(";")[0].split(" ")[0].lower()
                found = (await _call(http, "GET", f"/zones/{zone}/dns_records", params={"type": "TXT", "name": rec.name}))["result"]
                if any(str(f.get("content", "")).strip('"').lower().startswith(tag) for f in found):
                    log.info("cloudflare: %s already has a %s record; left as is", rec.name, tag)
                    continue
            res = await _call(http, "POST", f"/zones/{zone}/dns_records", json={
                "type": rec.type, "name": rec.name, "content": rec.content, "ttl": 1, "proxied": rec.proxied})
            created.append(f"/zones/{zone}/dns_records/{res['result']['id']}")
            made.append(rec)
        res = await _call(http, "POST", f"/zones/{zone}/workers/routes", json={"pattern": f"track.{domain}/*", "script": s.edge_worker_script})
        created.append(f"/zones/{zone}/workers/routes/{res['result']['id']}")
        return made
    except CloudflareError:
        await _rollback(http, created)
        raise
    finally:
        if own:
            await http.aclose()


async def propagated(domain: str, lookups=None) -> bool:
    """SPF, DMARC and the track host are all visible on both 1.1.1.1 and 8.8.8.8."""
    for look in lookups or [mx.resolver_lookup(ns) for ns in PUBLIC_RESOLVERS]:
        spf = [t for t in await look(domain, "TXT") or [] if t.lower().startswith("v=spf1")]
        dmarc = await mx.dmarc_policy(domain, look)
        if not spf or dmarc is None or not await look(f"track.{domain}", "A"):
            return False
    return True


async def promote_pending(Session, lookups=None) -> int:
    """Worker tick: domains whose records were created but not yet visible. Visible ones become `propagated`,
    and an order still at `ordered` becomes `ready`; any later InboxKit state is left as it is."""
    async with Session() as s:
        pending = list((await s.execute(select(Domain).where(Domain.dns_status == "pending"))).scalars())
        n = 0
        for d in pending:
            try:
                if await propagated(d.domain_name, lookups):
                    mark_propagated(d)
                    n += 1
            except Exception:
                log.exception("propagation check failed for %s", d.domain_name)
        await s.commit()
    return n


def mark_propagated(d: Domain) -> None:
    d.dns_status = "propagated"
    if d.status == "ordered":
        d.status = "ready"
