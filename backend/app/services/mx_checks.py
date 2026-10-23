"""Read-only DNS facts about our own sending domains: SPF, DKIM, DMARC, MTA-STS and DNSBL listings.

A resolver is any `async (name, rtype) -> list[str] | None`: a list of answers (TXT strings joined and
unquoted, A as an address, CNAME as a target), [] for NXDOMAIN or no data, None when the resolver itself
failed (timeout, SERVFAIL). None is never read as "absent" or "listed": it is an error the caller logs.
Query-only: nothing here writes DNS or sends mail.
"""
from __future__ import annotations

import ipaddress
import logging
from typing import Awaitable, Callable, Iterable, Optional

import dns.asyncresolver
import dns.exception
import dns.resolver

log = logging.getLogger("champmail.mx")

Lookup = Callable[[str, str], Awaitable[Optional[list[str]]]]

SPF_INCLUDE = {"google": "_spf.google.com", "microsoft": "spf.protection.outlook.com"}
DKIM_SELECTORS = {"google": ["google"], "microsoft": ["selector1", "selector2"]}


def platform(raw: Optional[str]) -> Optional[str]:
    """InboxKit's mailbox platform string as `google`, `microsoft`, or None (self-hosted SMTP, unknown)."""
    p = (raw or "").lower()
    return "google" if p.startswith("google") else "microsoft" if p.startswith(("microsoft", "azure", "m365", "outlook")) else None


def resolver_lookup(nameservers: Optional[list[str]] = None, timeout: float = 3.0) -> Lookup:
    """A Lookup backed by dnspython. `nameservers` pins it (the propagation check asks 1.1.1.1 and 8.8.8.8 directly)."""
    r = dns.asyncresolver.Resolver(configure=nameservers is None)
    if nameservers:
        r.nameservers = nameservers
    r.lifetime = r.timeout = timeout

    async def look(name: str, rtype: str) -> Optional[list[str]]:
        try:
            answer = await r.resolve(name, rtype)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return []
        except (dns.exception.Timeout, dns.resolver.NoNameservers):
            return None
        except dns.exception.DNSException:
            log.exception("dns %s %s failed", rtype, name)
            return None
        if rtype == "TXT":
            return [b"".join(rd.strings).decode("utf-8", "replace") for rd in answer]
        if rtype == "CNAME":
            return [rd.target.to_text() for rd in answer]
        return [rd.to_text() for rd in answer]

    return look


async def _txt(lookup: Lookup, name: str) -> list[str]:
    return await lookup(name, "TXT") or []


def _tags(record: str) -> dict[str, str]:
    out = {}
    for part in record.split(";"):
        k, _, v = part.strip().partition("=")
        if k:
            out[k.strip().lower()] = v.strip()
    return out


async def spf_ok(domain: str, platforms: Iterable[str], lookup: Lookup) -> bool:
    """Exactly one SPF record (two is a permerror) that includes every known provider's SPF host."""
    spf = [t for t in await _txt(lookup, domain) if t.lower().startswith("v=spf1")]
    if len(spf) != 1:
        return False
    return all(f"include:{SPF_INCLUDE[p]}" in spf[0].lower() for p in platforms)


async def dkim_ok(domain: str, platforms: Iterable[str], extra_selectors: Iterable[str], lookup: Lookup) -> bool:
    """A live (non-empty p=) DKIM key at one of the provider's selectors. TXT resolution follows M365's CNAMEs."""
    selectors = [s for p in platforms for s in DKIM_SELECTORS[p]] + list(extra_selectors)
    for sel in selectors:
        for t in await _txt(lookup, f"{sel}._domainkey.{domain}"):
            tags = _tags(t)
            if tags.get("v", "").upper() == "DKIM1" and tags.get("p"):
                return True
    return False


async def dmarc_policy(domain: str, lookup: Lookup) -> Optional[str]:
    """The `p=` of the domain's DMARC record, lowercase, or None when there is no valid record."""
    for t in await _txt(lookup, f"_dmarc.{domain}"):
        tags = _tags(t)
        if tags.get("v", "").upper() == "DMARC1" and tags.get("p"):
            return tags["p"].lower()
    return None


async def mta_sts_ok(domain: str, lookup: Lookup) -> bool:
    """The `_mta-sts` TXT record exists with an id. shortcut: the policy file at mta-sts.<domain> is not fetched,
    upgrade when we host inbound mail ourselves (Workspace and M365 own inbound today)."""
    return any(_tags(t).get("v", "").upper() == "STSV1" and _tags(t).get("id") for t in await _txt(lookup, f"_mta-sts.{domain}"))


def _is_listing(answer: str) -> bool:
    # Spamhaus answers 127.255.255.x to refused or rate-limited resolvers: an error, never a listing.
    return answer.startswith("127.") and not answer.startswith("127.255.255.")


async def dnsbl_check(domain: str, ips: Iterable[str], zones: Iterable, lookup: Lookup) -> tuple[list[str], list[str]]:
    """(zone names that list us, zone names we could not get an answer from). Disabled zones are skipped."""
    v4 = []
    for ip in ips:
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if a.version == 4:
            v4.append(".".join(reversed(str(a).split("."))))
    hits, errors = [], []
    for z in zones:
        if not z.enabled:
            continue
        names = [f"{r}.{z.zone}" for r in v4] if z.kind == "ip" else [f"{domain}.{z.zone}"]
        failed = listed = False
        for n in names:
            ans = await lookup(n, "A")
            if ans is None or any(a.startswith("127.255.255.") for a in ans):
                failed = True  # resolver failure, or Spamhaus saying our resolver is refused: no answer either way
            elif any(_is_listing(a) for a in ans):
                listed = True
        if listed:
            hits.append(z.name)
        elif failed:
            errors.append(z.name)
    return hits, errors
