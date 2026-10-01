"""
DNS-based blacklist (DNSBL) checker.

Checks sending domain MX IPs against major blacklists:
- Spamhaus ZEN (SBL + XBL + PBL)
- Barracuda Central
- SpamCop

Results are cached in Redis for 6 hours per domain.
"""

from __future__ import annotations

import json
import logging
import socket
from typing import Dict, List, Optional

import dns.resolver

from app.db.redis import redis_client

logger = logging.getLogger(__name__)

DNSBL_SERVERS = [
    "zen.spamhaus.org",
    "b.barracudacentral.org",
    "bl.spamcop.net",
]

CACHE_TTL = 6 * 3600  # 6 hours


def _reverse_ip(ip: str) -> str:
    """Reverse an IPv4 address for DNSBL lookup (1.2.3.4 → 4.3.2.1)."""
    return ".".join(reversed(ip.split(".")))


class BlacklistChecker:
    """Check domain MX IPs against DNS-based blacklists."""

    async def _resolve_mx_ips(self, domain_name: str) -> List[str]:
        """Get the IP addresses behind a domain's MX records."""
        ips: List[str] = []
        try:
            mx_records = dns.resolver.resolve(domain_name, "MX")
            for mx in mx_records:
                mx_host = str(mx.exchange).rstrip(".")
                try:
                    a_records = dns.resolver.resolve(mx_host, "A")
                    for a in a_records:
                        ips.append(str(a))
                except Exception:
                    pass
        except Exception as e:
            logger.debug("MX lookup failed for %s: %s", domain_name, e)
            # Fall back to A record of the domain itself
            try:
                a_records = dns.resolver.resolve(domain_name, "A")
                for a in a_records:
                    ips.append(str(a))
            except Exception:
                pass
        return ips

    def _check_ip_sync(self, ip: str, dnsbl: str) -> Optional[str]:
        """Check a single IP against a single DNSBL (synchronous DNS query).

        Returns the listing reason string if listed, None otherwise.
        """
        query = f"{_reverse_ip(ip)}.{dnsbl}"
        try:
            answers = dns.resolver.resolve(query, "A")
            # If we get an answer, the IP is listed
            return str(answers[0])
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            return None
        except dns.resolver.LifetimeTimeout:
            logger.debug("DNSBL timeout: %s on %s", ip, dnsbl)
            return None
        except Exception as e:
            logger.debug("DNSBL error for %s on %s: %s", ip, dnsbl, e)
            return None

    async def check_domain(self, domain_name: str) -> Dict:
        """Check if a domain's MX IPs appear on any DNSBL.

        Returns:
            {"listed": bool, "listings": [{"server": ..., "ip": ..., "result": ...}]}
        """
        cache_key = f"blacklist:{domain_name}:result"

        # Check cache first
        cached = await redis_client.get_json(cache_key)
        if cached is not None:
            return cached

        ips = await self._resolve_mx_ips(domain_name)
        if not ips:
            result = {"listed": False, "listings": [], "ips_checked": 0}
            await redis_client.set_json(cache_key, result, ex=CACHE_TTL)
            return result

        listings = []
        for ip in ips[:3]:  # Check max 3 IPs to keep it fast
            for dnsbl in DNSBL_SERVERS:
                bl_result = self._check_ip_sync(ip, dnsbl)
                if bl_result:
                    listings.append({
                        "server": dnsbl,
                        "ip": ip,
                        "result": bl_result,
                    })

        result = {
            "listed": len(listings) > 0,
            "listings": listings,
            "ips_checked": len(ips[:3]),
        }

        await redis_client.set_json(cache_key, result, ex=CACHE_TTL)

        if listings:
            logger.warning(
                "Domain %s is blacklisted: %s",
                domain_name, json.dumps(listings),
            )

        return result

    async def check_domain_by_id(self, domain_id: str) -> Dict:
        """Check a domain by its database ID. Loads domain name from cache."""
        from app.services.deliverability.rate_limiter import rate_limiter
        meta = await rate_limiter._get_domain_meta(domain_id)
        if not meta:
            return {"listed": False, "listings": [], "error": "Domain not found"}

        result = await self.check_domain(meta["domain_name"])

        # Also store under domain_id key for the send gate to read
        await redis_client.set_json(
            f"domain:{domain_id}:blacklist", result, ex=CACHE_TTL,
        )
        return result


# Module singleton
blacklist_checker = BlacklistChecker()
