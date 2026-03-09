"""
Test mode utilities for development testing.
Allows bypassing DNS verification when testing with services like Ethereal.
"""
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


def is_test_mode_enabled() -> bool:
    """
    Check if test mode is enabled.

    When test mode is active, DNS verification is bypassed to allow
    testing with services like Ethereal mail that don't have real DNS records.

    Returns:
        bool: True if test mode is enabled, False otherwise
    """
    if settings.test_mode:
        logger.warning("⚠️  TEST MODE ACTIVE - DNS verification bypassed")
        return True
    return False


def get_test_mode_domain_id() -> str:
    """
    Return a fixed test domain ID when in test mode.

    Returns:
        str: Fixed UUID for test mode domain
    """
    return "00000000-0000-0000-0000-000000000001"
