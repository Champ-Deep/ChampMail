"""
DNS-based IP reputation / blacklist checker.

Works entirely via standard DNS lookups — no external API keys needed.
DNSBL protocol: reverse the IP octets, append the blacklist zone, do an
A-record lookup. Any response = listed. NXDOMAIN = clean.

Usage:
    from app.services.ip_blacklist import blacklist_checker
    summary = await blacklist_checker.check_ip("1.2.3.4")
"""
from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Blacklist zones to check
# zen.spamhaus.org is the most important — it covers SBL + XBL + PBL combined.
# ---------------------------------------------------------------------------

BLACKLIST_ZONES: list[tuple[str, str]] = [
    ("zen.spamhaus.org",       "Spamhaus ZEN (SBL+XBL+PBL)"),
    ("b.barracudacentral.org", "Barracuda BRBL"),
    ("bl.spamcop.net",         "SpamCop"),
    ("dnsbl.sorbs.net",        "SORBS"),
    ("dnsbl-1.uceprotect.net", "UCEProtect L1"),
    ("ix.dnsbl.manitu.net",    "Manitu"),
]

# Private IP ranges — skip these, they are never on public blacklists
_PRIVATE_PREFIXES = ("127.", "10.", "172.16.", "172.17.", "172.18.", "172.19.",
                     "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
                     "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
                     "172.30.", "172.31.", "192.168.", "::1", "fc", "fd")


@dataclass
class BlacklistHit:
    zone: str
    name: str
    lookup_host: str


@dataclass
class BlacklistReport:
    ip: str
    blacklisted: bool
    hits: list[BlacklistHit] = field(default_factory=list)
    checked: int = 0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "ip": self.ip,
            "blacklisted": self.blacklisted,
            "hits": [{"zone": h.zone, "name": h.name} for h in self.hits],
            "hit_count": len(self.hits),
            "checked": self.checked,
            "clean": self.checked - len(self.hits),
        }

    def health_penalty(self) -> float:
        """Points to deduct from health_score (0–100 scale). Each hit = 25 pts."""
        return min(100.0, len(self.hits) * 25.0)


def _is_private(ip: str) -> bool:
    for prefix in _PRIVATE_PREFIXES:
        if ip.startswith(prefix):
            return True
    return False


def _reverse_ip(ip: str) -> str:
    parts = ip.strip().split(".")
    return ".".join(reversed(parts))


async def _lookup_one(reversed_ip: str, zone: str, name: str) -> tuple[bool, Optional[BlacklistHit]]:
    """Single DNS blacklist lookup in a thread executor (socket is blocking)."""
    host = f"{reversed_ip}.{zone}"
    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, socket.gethostbyname, host)
        # Got a result → listed
        return True, BlacklistHit(zone=zone, name=name, lookup_host=host)
    except socket.gaierror:
        # NXDOMAIN or timeout → not listed
        return False, None
    except Exception as exc:
        logger.debug("BL lookup error %s on %s: %s", zone, host, exc)
        return False, None


class IPBlacklistChecker:
    """Async IP blacklist checker using DNS-based lookups."""

    async def check_ip(self, ip: str) -> BlacklistReport:
        """Check an IP against all configured blacklist zones."""
        if not ip:
            return BlacklistReport(ip=ip, blacklisted=False, error="empty IP")

        if _is_private(ip):
            return BlacklistReport(ip=ip, blacklisted=False, error="private IP, skip")

        parts = ip.strip().split(".")
        if len(parts) != 4 or not all(p.isdigit() for p in parts):
            return BlacklistReport(ip=ip, blacklisted=False, error=f"invalid IP: {ip}")

        reversed_ip = _reverse_ip(ip)

        tasks = [
            _lookup_one(reversed_ip, zone, name)
            for zone, name in BLACKLIST_ZONES
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        hits: list[BlacklistHit] = []
        checked = 0

        for res in results:
            if isinstance(res, Exception):
                continue
            listed, hit = res
            checked += 1
            if listed and hit:
                hits.append(hit)

        blacklisted = len(hits) > 0
        if blacklisted:
            logger.warning(
                "IP %s is blacklisted on %d/%d zones: %s",
                ip, len(hits), checked, [h.name for h in hits],
            )
        else:
            logger.info("IP %s is clean across %d zones", ip, checked)

        return BlacklistReport(
            ip=ip,
            blacklisted=blacklisted,
            hits=hits,
            checked=checked,
        )

    async def get_vps_ip(self) -> Optional[str]:
        """
        Attempt to determine the outbound public IP of this server.
        Falls back to None if detection fails.
        """
        import os
        # 1. Explicit env var (most reliable — set VPS_PUBLIC_IP in .env)
        env_ip = os.getenv("VPS_PUBLIC_IP", "").strip()
        if env_ip:
            return env_ip

        # 2. Try connecting to a public IP to detect outbound IP
        loop = asyncio.get_event_loop()
        try:
            def _detect():
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                s.close()
                return ip
            return await loop.run_in_executor(None, _detect)
        except Exception as exc:
            logger.debug("Could not detect outbound IP: %s", exc)
            return None


blacklist_checker = IPBlacklistChecker()
