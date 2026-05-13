#!/usr/bin/env python3
"""
Postfix pipe handler for VERP bounce addresses.

Postfix calls this script when mail arrives for bounce+{prospect_id}@mail.domain.com.
It parses the DSN, extracts the prospect_id from the VERP address, classifies the
bounce type, and enqueues a Celery task.

Postfix alias config (add to /etc/aliases or master.cf pipe):
  bounce: |/usr/local/bin/python3 /app/bounce_handler.py
"""

import sys
import email
import re
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bounce_handler")

# VERP pattern: bounce+{uuid}@domain
VERP_RE = re.compile(r"bounce\+([a-f0-9\-]{36})@", re.IGNORECASE)


def classify_bounce(msg: email.message.Message) -> str:
    """Classify bounce as hard, soft, or complaint from DSN headers."""
    # Check for spam complaint (ARF format)
    content_type = msg.get_content_type()
    if "report" in content_type and "feedback" in content_type:
        return "complaint"

    # Walk DSN parts for status codes
    for part in msg.walk():
        if part.get_content_type() == "message/delivery-status":
            payload = part.get_payload()
            if isinstance(payload, str):
                # Status codes: 5.x.x = permanent (hard), 4.x.x = temporary (soft)
                if re.search(r"Status:\s*5\.", payload):
                    return "hard"
                if re.search(r"Status:\s*4\.", payload):
                    return "soft"

    # Check subject line for common bounce indicators
    subject = msg.get("Subject", "").lower()
    if any(w in subject for w in ["undeliverable", "delivery failed", "permanent", "does not exist"]):
        return "hard"
    if any(w in subject for w in ["temporarily", "try again", "over quota", "full"]):
        return "soft"

    return "hard"  # Default to hard if unclear


def main():
    raw = sys.stdin.buffer.read()
    if not raw:
        sys.exit(0)

    msg = email.message_from_bytes(raw)

    # Extract prospect_id from VERP To address
    to_header = msg.get("To", "") or msg.get("Delivered-To", "")
    match = VERP_RE.search(to_header)
    if not match:
        # Try original recipient from Postfix env
        original_recipient = os.getenv("ORIGINAL_RECIPIENT", "")
        match = VERP_RE.search(original_recipient)

    if not match:
        logger.warning("No VERP prospect_id found in bounce — discarding")
        sys.exit(0)

    prospect_id = match.group(1)
    bounce_type = classify_bounce(msg)

    logger.info("Bounce: prospect=%s type=%s", prospect_id, bounce_type)

    # Enqueue Celery task
    try:
        import django  # noqa — not used, just ensuring path
    except ImportError:
        pass

    sys.path.insert(0, "/app")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "")

    try:
        from app.tasks.bounces import process_single_bounce
        process_single_bounce.delay(
            prospect_id=prospect_id,
            bounce_type=bounce_type,
        )
        logger.info("Enqueued bounce task for prospect %s", prospect_id)
    except Exception as e:
        logger.error("Failed to enqueue bounce task: %s", e)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
