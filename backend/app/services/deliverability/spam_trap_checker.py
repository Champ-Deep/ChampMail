"""
Spam trap checker — blocks known spam traps, honeypots, and role-based addresses.

Sources:
1. Local file: data/spam_traps.txt (user-editable, one entry per line)
2. Role-based address patterns (abuse@, postmaster@, noreply@, etc.)
3. Redis cache of the file (auto-refreshed every 10 minutes)
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Set

logger = logging.getLogger(__name__)

# Role-based prefixes that are almost always traps or unmonitored
ROLE_PREFIXES = frozenset({
    "abuse",
    "admin",
    "compliance",
    "devnull",
    "dns",
    "ftp",
    "hostmaster",
    "honeypot",
    "info",
    "mailer-daemon",
    "marketing",
    "noc",
    "noreply",
    "no-reply",
    "phishing",
    "postmaster",
    "root",
    "sales",
    "security",
    "spam",
    "support",
    "sysadmin",
    "undisclosed-recipients",
    "usenet",
    "uucp",
    "webmaster",
    "www",
})

# How often to reload the trap file from disk (seconds)
RELOAD_INTERVAL = 600  # 10 minutes

# Path to the spam trap file — relative to the backend root
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # backend/
TRAP_FILE = _BACKEND_ROOT / "data" / "spam_traps.txt"


class SpamTrapChecker:
    """Check emails against known spam traps and role-based patterns."""

    def __init__(self):
        self._exact_traps: Set[str] = set()     # full emails
        self._domain_traps: Set[str] = set()    # @domain entries
        self._loaded_at: float = 0

    def _needs_reload(self) -> bool:
        return (time.time() - self._loaded_at) > RELOAD_INTERVAL

    def _load_file(self) -> None:
        """Load spam_traps.txt into memory sets."""
        exact: Set[str] = set()
        domains: Set[str] = set()

        if not TRAP_FILE.exists():
            logger.warning("Spam trap file not found: %s", TRAP_FILE)
            self._loaded_at = time.time()
            return

        try:
            with open(TRAP_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    entry = line.strip().lower()
                    if not entry or entry.startswith("#"):
                        continue
                    if entry.startswith("@"):
                        domains.add(entry[1:])  # strip leading @
                    else:
                        exact.add(entry)

            self._exact_traps = exact
            self._domain_traps = domains
            self._loaded_at = time.time()
            logger.debug(
                "Loaded spam traps: %d exact, %d domain entries",
                len(exact), len(domains),
            )
        except Exception as e:
            logger.error("Failed to load spam trap file: %s", e)

    async def is_spam_trap(self, email: str) -> bool:
        """Check if an email is a known spam trap.

        Checks (in order):
        1. Role-based prefix pattern
        2. Exact email match from file
        3. Domain-wide block from file
        """
        if not email:
            return False

        email_lower = email.lower().strip()

        # 1. Role-based prefix check
        local_part = email_lower.split("@")[0] if "@" in email_lower else ""
        if local_part in ROLE_PREFIXES:
            return True

        # Reload file if stale
        if self._needs_reload():
            self._load_file()

        # 2. Exact email match
        if email_lower in self._exact_traps:
            return True

        # 3. Domain-wide block
        if "@" in email_lower:
            domain = email_lower.split("@")[1]
            if domain in self._domain_traps:
                return True

        return False

    async def add_trap(self, email: str) -> None:
        """Append a newly discovered trap to the file and memory set."""
        email_lower = email.lower().strip()

        # Add to memory immediately
        if email_lower.startswith("@"):
            self._domain_traps.add(email_lower[1:])
        else:
            self._exact_traps.add(email_lower)

        # Append to file
        try:
            with open(TRAP_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n{email_lower}")
            logger.info("Added spam trap: %s", email_lower)
        except Exception as e:
            logger.error("Failed to write spam trap to file: %s", e)


# Module singleton
spam_trap_checker = SpamTrapChecker()
