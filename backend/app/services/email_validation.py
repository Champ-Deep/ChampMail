"""
Email validation service.

Validates email addresses for syntax and optionally checks MX records.
"""

import re
import logging
from typing import Optional, Tuple
import dns.resolver

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


class EmailValidator:
    """Validates email addresses."""

    def validate_syntax(self, email: str) -> Tuple[bool, Optional[str]]:
        """Validate email syntax.

        Args:
            email: Email address to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not email:
            return False, "Email is empty"

        if not EMAIL_REGEX.match(email):
            return False, "Invalid email format"

        local, domain = email.rsplit("@", 1)

        if len(local) > 64:
            return False, "Local part too long"

        if len(domain) > 255:
            return False, "Domain too long"

        return True, None

    async def validate_mx(self, email: str) -> Tuple[bool, Optional[str]]:
        """Validate email has valid MX records.

        Args:
            email: Email address to validate

        Returns:
            Tuple of (has_mx, error_message)
        """
        _, domain = email.rsplit("@", 1)

        try:
            mx_records = dns.resolver.resolve(domain, "MX")
            if not mx_records:
                return False, f"No MX records for {domain}"
            return True, None
        except dns.resolver.NXDOMAIN:
            return False, f"Domain {domain} does not exist"
        except dns.resolver.NoAnswer:
            return False, f"No MX records found for {domain}"
        except Exception as e:
            logger.warning(f"MX lookup failed for {domain}: {e}")
            return True, None

    async def validate(
        self, email: str, check_mx: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """Validate email address.

        Args:
            email: Email address to validate
            check_mx: Whether to check MX records (optional, slower)

        Returns:
            Tuple of (is_valid, error_message)
        """
        is_valid, error = self.validate_syntax(email)
        if not is_valid:
            return False, error

        if check_mx:
            has_mx, mx_error = await self.validate_mx(email)
            if not has_mx:
                return False, mx_error

        return True, None

    def is_disposable_email(self, email: str) -> bool:
        """Check if email is from a disposable email provider.

        Args:
            email: Email address to check

        Returns:
            True if email is from disposable provider
        """
        _, domain = email.rsplit("@", 1)
        domain = domain.lower()

        disposable_domains = {
            "tempmail.com",
            "throwaway.email",
            "10minutemail.com",
            "guerrillamail.com",
            "mailinator.com",
            "trashmail.com",
            "getnada.com",
            "yopmail.com",
            "dispostable.com",
        }

        return domain in disposable_domains


email_validator = EmailValidator()
