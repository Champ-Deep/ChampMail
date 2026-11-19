"""Read-only, stateless public-DNS observations for ONE domain: SPF, DKIM, DMARC, MX, MTA-STS, domain DNSBLs.

Reuses the resolver and record parsers in mx_checks (the daily job's checker); nothing here touches the database,
writes DNS or opens an SMTP connection. Every check is pass, warn, fail, info or unknown. A resolver failure, an
absent selector or a blocked blocklist query is `unknown`, never `pass`. These are DNS facts only: they are not
inbox-placement proof and there is deliberately no overall score.

CLI (live DNS, prints JSON): python -m app.services.domain_probe example.com --selector s1 [--nameserver 1.1.1.1]
"""
from __future__ import annotations

import asyncio
import json
import platform
import re
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Iterable, Optional

from app.services import mx_checks as mx

# Same shape the API uses to validate a domain order (api/v1/domains.py); copied to keep services free of API imports.
DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")
SELECTOR_RE = re.compile(r"^[a-z0-9]([a-z0-9_-]{0,61}[a-z0-9])?$")
# Provider-default selectors plus common ones. A miss on these proves nothing: DKIM selectors cannot be enumerated.
COMMON_SELECTORS = ["google", "selector1", "selector2", "default", "k1", "s1", "s2", "mail", "dkim"]
# Domain-keyed lists only: the sending IPs of a domain are not public DNS facts we can know.
# `control` is each list's documented always-listed test point (surbl.org/faqs2#testpoints, Spamhaus DBL docs);
# `refused` is SURBL's documented "access blocked" answer (surbl.org/guidelines item 8).
ZONES = [SimpleNamespace(name="surbl", zone="multi.surbl.org", kind="domain", enabled=True, control="test.surbl.org", refused=("127.0.0.1",)),
         SimpleNamespace(name="spamhaus_dbl", zone="dbl.spamhaus.org", kind="domain", enabled=True, control="dbltest.com", refused=())]
SPF_LOOKUP_TERM = re.compile(r"^(include:|exists:|redirect=|(a|mx|ptr)([:/]|$))")  # "all" must not match "a"
NOTE = ("Public DNS observations only. Not inbox-placement proof and not a deliverability score. "
        "Absent or unreachable evidence is shown as unknown, never as a pass.")


def normalize_domain(raw: str) -> str:
    d = (raw or "").strip().lower().rstrip(".")
    if not DOMAIN_RE.match(d):
        raise ValueError("not a valid domain name")
    return d


def normalize_selectors(raw: Iterable[str]) -> list[str]:
    out = []
    for s in raw:
        s = (s or "").strip().lower()
        if not SELECTOR_RE.match(s):
            raise ValueError(f"not a valid DKIM selector: {s!r}")
        if s not in out:
            out.append(s)
    return out


def _c(status: str, detail: str, **extra) -> dict:
    return {"status": status, "detail": detail, **extra}


async def _spf(d, lookup):
    txt = await lookup(d, "TXT")
    if txt is None:
        return _c("unknown", "resolver failure while reading TXT")
    spf = [t for t in txt if t.lower().startswith("v=spf1")]
    if not spf:
        return _c("fail", "no SPF record", records=[])
    if len(spf) > 1:
        return _c("fail", "more than one SPF record (permerror)", records=spf)
    terms = spf[0].lower().split()[1:]
    n = sum(1 for t in terms if SPF_LOOKUP_TERM.match(t.lstrip("+-~?")))
    allq = next((t for t in terms if t.lstrip("+-~?") == "all"), None)
    # shortcut: top-level terms only, nested includes are not expanded; upgrade if IT needs the full lookup count.
    if n > 10:
        return _c("fail", f"{n} DNS-lookup terms at the top level, over the limit of 10", records=spf, lookup_terms_top_level=n)
    return _c("pass" if allq else "warn", "one SPF record" + ("" if allq else ", no all term"), records=spf, lookup_terms_top_level=n, all_term=allq)


async def _dkim(d, selectors, lookup):
    tried = selectors + [s for s in COMMON_SELECTORS if s not in selectors]
    found, failed, revoked = [], 0, []
    for sel in tried:
        txt = await lookup(f"{sel}._domainkey.{d}", "TXT")
        if txt is None:
            failed += 1
            continue
        for t in txt:
            tags = mx._tags(t)
            if tags.get("v", "DKIM1").upper() == "DKIM1" and "p" in tags:
                (found if tags["p"] else revoked).append(sel)
    base = dict(selectors_tried=tried, selectors_supplied=selectors)
    if found:
        return _c("pass", "live DKIM key at selector(s) " + ", ".join(found), selectors_found=found, **base)
    if revoked:
        return _c("fail", "DKIM key revoked (empty p=) at " + ", ".join(revoked), **base)
    why = "resolver failure on some lookups; " if failed else ""
    hint = "" if selectors else "no selector supplied; "
    return _c("unknown", f"{why}{hint}no key at the selectors tried (the real selector may be elsewhere)", **base)


async def _dmarc(d, lookup):
    txt = await lookup(f"_dmarc.{d}", "TXT")
    if txt is None:
        return _c("unknown", "resolver failure while reading TXT")
    recs = [t for t in txt if mx._tags(t).get("v", "").upper() == "DMARC1"]
    if len(recs) != 1 or not mx._tags(recs[0]).get("p"):
        return _c("fail", "no valid DMARC record" if not recs else "more than one DMARC record or no p=", records=recs)
    tags = mx._tags(recs[0])
    p = tags["p"].lower()
    return _c("pass" if p in ("quarantine", "reject") else "warn",
              f"policy p={p}" + (" (monitoring only, nothing is enforced)" if p == "none" else ""),
              policy=p, rua=tags.get("rua"), pct=tags.get("pct"), records=recs)


async def _mx(d, lookup):
    r = await lookup(d, "MX")
    if r is None:
        return _c("unknown", "resolver failure while reading MX")
    return _c("info", f"{len(r)} MX record(s)" if r else "no MX records", records=sorted(r))


async def _sts(d, lookup):
    txt = await lookup(f"_mta-sts.{d}", "TXT")
    if txt is None:
        return _c("unknown", "resolver failure while reading TXT")
    ok = any(mx._tags(t).get("v", "").upper() == "STSV1" and mx._tags(t).get("id") for t in txt)
    return _c("info", "MTA-STS TXT record present (policy file not fetched)" if ok else "no MTA-STS record")


async def _dnsbl(d, lookup):
    hits, errors = await mx.dnsbl_check(d, [], ZONES, lookup)
    per = {z.name: "listed" if z.name in hits else "unknown" if z.name in errors else "not_listed" for z in ZONES}
    # Raw control answers shown so a reader can see each list answered this resolver.
    controls = {z.name: await lookup(f"{z.control}.{z.zone}", "A") for z in ZONES}
    # Raw return codes for humans to read against each list's own documentation; we do not interpret them.
    codes = {z.name: await lookup(f"{d}.{z.zone}", "A") for z in ZONES if z.name in hits}
    status = "fail" if hits else "unknown" if errors else "pass"
    return _c(status, f"listed on {', '.join(hits)}" if hits else
              f"no usable answer from {', '.join(errors)} (resolver blocked or failed, or the list's test point did not answer; not a clean result)" if errors else "not listed (test points answered)",
              zones=per, answers=codes, controls=controls)


async def probe(domain: str, lookup: Optional[mx.Lookup] = None, selectors: Iterable[str] = ()) -> dict:
    """Observe `domain` once. Raises ValueError on a malformed domain or selector (no lookups are made then)."""
    d, sels = normalize_domain(domain), normalize_selectors(selectors)
    lookup = lookup or mx.resolver_lookup()
    names = ["spf", "dkim", "dmarc", "mx", "mta_sts", "dnsbl"]
    results = await asyncio.gather(_spf(d, lookup), _dkim(d, sels, lookup), _dmarc(d, lookup), _mx(d, lookup), _sts(d, lookup), _dnsbl(d, lookup))
    checks = dict(zip(names, results))
    attention = [n for n, c in checks.items() if c["status"] in ("fail", "warn", "unknown")]
    bad = [n for n in attention if checks[n]["status"] in ("fail", "warn")]
    rec = (f"IT review recommended for: {', '.join(bad)}. This is a recommendation only: nothing is paused, rotated or changed automatically."
           if bad else None)
    return {"domain": d, "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": ("live public DNS via dnspython, run on host " + platform.node() + ", nameservers used: "
                       + (", ".join(ns) if (ns := getattr(lookup, "nameservers", None)) else "unspecified (injected lookup)")
                       + "; DNSBL zones: " + ", ".join(z.zone for z in ZONES)),
            "note": NOTE, "checks": checks, "attention": attention, "it_recommendation": rec}


if __name__ == "__main__":
    args = sys.argv[1:]
    def flag(f):
        return [args[i + 1] for i, a in enumerate(args) if a == f and i + 1 < len(args)]
    sel, ns = flag("--selector"), flag("--nameserver")
    dom = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or args[i - 1] not in ("--selector", "--nameserver"))]
    if len(dom) != 1:
        sys.exit("usage: python -m app.services.domain_probe DOMAIN [--selector S ...] [--nameserver IP]")
    try:
        print(json.dumps(asyncio.run(probe(dom[0], mx.resolver_lookup(ns or None), sel)), indent=2))
    except ValueError as e:
        sys.exit(f"error: {e}")
