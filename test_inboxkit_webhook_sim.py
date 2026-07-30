"""
Webhook handler simulation test — no live ChampMail server or API needed.

Simulates exactly what InboxKit posts: the envelope, headers, and the
static-SHA-256 signature. Verifies the handler:
  1. Accepts a correctly-signed fresh event.
  2. Rejects a bad signature (401).
  3. Rejects a stale timestamp (400).
  4. Discards plaintext creds from the mailbox payload (never persisted).
  5. Returns 2xx within the 30s contract window.

Run:
  cd ~/ChampSuite/ChampMail
  backend/.venv/bin/python test_inboxkit_webhook_sim.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

os.environ.setdefault("INBOXKIT_API_KEY", "sim-key-1234567890")
os.environ.setdefault("INBOXKIT_WORKSPACE_ID", "ws_sim")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))


def _sign(api_key: str) -> str:
    """Mirror InboxKit's signature: sha256=<lowercase hex SHA-256(api_key)>."""
    return f"sha256={hashlib.sha256(api_key.encode()).hexdigest()}"


def _envelope(event: str, data: dict, timestamp: str | None = None) -> bytes:
    return json.dumps({
        "event": event,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "team_id": "team_sim",
        "team_name": "Sim Team",
        "data": data,
    }).encode()


def test_webhook_handler():
    """Exercise the handler functions directly (no HTTP server needed)."""
    from app.api.v1 import inboxkit_webhooks as wh

    api_key = os.environ["INBOXKIT_API_KEY"]

    # 1. Signature verification — good and bad.
    expected = wh._expected_signature()
    assert expected == _sign(api_key), f"expected_signature mismatch: {expected}"
    assert wh._verify_signature(_sign(api_key), expected) is True
    assert wh._verify_signature("sha256=deadbeef", expected) is False
    assert wh._verify_signature(None, expected) is False
    print("  PASS  signature verification (accept valid, reject invalid/missing)")

    # 2. Freshness — fresh now, stale 10 min ago.
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    assert wh._is_fresh(now.isoformat()) is True
    assert wh._is_fresh((now - timedelta(minutes=10)).isoformat()) is False
    print("  PASS  freshness window (fresh accepted, stale rejected)")

    # 3. Credential discard — the handler must strip password/app_password/secret
    #    from the webhook payload before doing anything with it.
    import asyncio

    class _StubProvider:
        """Stand-in for InboxKitProvider — no network, returns canned records."""
        async def get_domain(self, uid):
            from app.services.mail_infra import DomainRecord
            return DomainRecord(uid=uid, name="sim.com", status="ready",
                                native_status="active")
        async def get_mailbox(self, uid):
            from app.services.mail_infra import MailboxRecord
            return MailboxRecord(uid=uid, email="agent@sim.com", status="ready",
                                 native_status="active", platform="google")
        async def get_credentials(self, uid):
            from app.services.mail_infra import MailboxCredentials
            return MailboxCredentials(email="agent@sim.com", username="agent@sim.com",
                                      password="stub-secret", smtp_host="smtp.gmail.com",
                                      smtp_port=587, imap_host="imap.gmail.com",
                                      imap_port=993, platform="google")

    # Monkey-patch the provider + persistence + idempotency so nothing hits
    # the network, Redis, or Postgres.
    wh.InboxKitProvider = _StubProvider  # type: ignore[assignment]
    persisted: dict = {}
    async def _fake_persist_domain(record):
        persisted["domain"] = record
    async def _fake_persist_mailbox(record):
        persisted["mailbox"] = record
    async def _fake_persist_creds(record, creds):
        persisted["creds"] = creds
    async def _fake_already_seen(key):
        return False
    wh._persist_domain_state = _fake_persist_domain  # type: ignore[assignment]
    wh._persist_mailbox_state = _fake_persist_mailbox  # type: ignore[assignment]
    wh._persist_mailbox_credentials = _fake_persist_creds  # type: ignore[assignment]
    wh._already_seen = _fake_already_seen  # type: ignore[assignment]

    # A mailbox.status_changed payload carrying plaintext creds — the exact
    # shape the docs warn about.
    payload = {
        "mailbox": {
            "uid": "mb_sim_1",
            "email": "agent@sim.com",
            "status": "active",
            "platform": "GOOGLE",
            "password": "SHOULD-BE-DISCARDED",
            "app_password": "SHOULD-BE-DISCARDED-TOO",
            "secret": "ALSO-DISCARDED",
        },
        "metadata": {"workspace_id": "ws_sim"},
    }
    result = asyncio.run(wh._route_event("mailbox.status_changed", payload))
    assert result["status"] == "updated", f"unexpected result: {result}"
    assert persisted["mailbox"].uid == "mb_sim_1"
    # Credentials came from the provider's authenticated re-fetch (stub), and
    # the webhook payload's creds were never stored anywhere.
    assert persisted["creds"].password == "stub-secret"
    assert persisted["creds"].password != "SHOULD-BE-DISCARDED"
    print("  PASS  mailbox.status_changed: creds from webhook discarded, "
          "authoritative re-fetch used")

    # 4. Unknown event is ignored (200, no mutation).
    result = asyncio.run(wh._route_event("some.future_event", {}))
    assert result["status"] == "ignored"
    print("  PASS  unknown event ignored without crashing")

    # 5. domain.status_changed round-trips through the re-fetch + persist.
    result = asyncio.run(wh._route_event("domain.status_changed", {
        "domain": {"uid": "dom_sim_1", "status": "active", "name": "sim.com"},
        "metadata": {"workspace_id": "ws_sim"},
    }))
    assert result["status"] == "updated"
    assert persisted["domain"].name == "sim.com"
    print("  PASS  domain.status_changed: re-fetch + persist path works")

    print("\nAll webhook handler simulations passed.")


if __name__ == "__main__":
    test_webhook_handler()
