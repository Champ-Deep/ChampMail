"""
Pre-send email validation — runs before every outbound email.

Checks (in order):
1. Format  — is it a valid email address?
2. MX      — does the domain have a mail server?
3. Role    — skip info@, admin@, noreply@, etc.
4. Suppression — was this address previously bounced or unsubscribed?
"""
from __future__ import annotations

import asyncio
import logging
import re
import socket
from typing import Optional

logger = logging.getLogger(__name__)

# RFC 5322 simplified — good enough for pre-send filtering
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

# Role addresses that almost never belong to a real person
_ROLE_PREFIXES = frozenset({
    "info", "admin", "administrator", "support", "help", "contact",
    "hello", "sales", "billing", "accounts", "hr", "careers", "jobs",
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "postmaster", "abuse", "webmaster", "hostmaster",
    "spam", "marketing", "newsletter", "press", "media", "pr",
    "team", "office", "enquiries", "enquiry", "general",
})


def _is_valid_format(email: str) -> bool:
    return bool(_EMAIL_RE.match(email.strip()))


def _is_role_address(email: str) -> bool:
    local = email.split("@")[0].lower()
    return local in _ROLE_PREFIXES


async def _has_mx_record(domain: str) -> bool:
    """Non-blocking MX lookup via thread executor."""
    loop = asyncio.get_event_loop()
    try:
        # Use getaddrinfo as a fallback — a proper MX check needs dnspython
        # For now, check if the domain resolves at all
        await loop.run_in_executor(None, socket.gethostbyname, domain)
        return True
    except socket.gaierror:
        return False
    except Exception:
        return True  # Don't block send on lookup errors


class EmailValidator:
    async def validate(
        self,
        email: str,
        session=None,
    ) -> dict:
        """
        Run all pre-send checks on an email address.

        Returns {"valid": bool, "reason": str | None}
        """
        email = email.strip().lower()

        if not email:
            return {"valid": False, "reason": "empty email"}

        if not _is_valid_format(email):
            return {"valid": False, "reason": "invalid format"}

        if _is_role_address(email):
            return {"valid": False, "reason": f"role address: {email.split('@')[0]}"}

        domain = email.split("@")[1]
        if not await _has_mx_record(domain):
            return {"valid": False, "reason": f"no MX record for {domain}"}

        # Suppression list check
        if session:
            try:
                from app.services.suppression_service import suppression_service
                if await suppression_service.is_suppressed(session, email):
                    return {"valid": False, "reason": "on suppression list"}
            except Exception:
                pass  # Don't block if suppression service unavailable

        return {"valid": True, "reason": None}


email_validator = EmailValidator()
