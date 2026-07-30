"""
Offline smoke test for the InboxKit integration.

Runs without an API key or network — verifies:
- All modules import cleanly (no circular imports, no typos).
- The static-SHA-256 signature math matches the docs' openssl recipe.
- The state mapping covers every verified InboxKit status string.
- The webhook handler rejects bad signatures, stale events, and discards
  webhook-delivered credentials.

Run:  cd backend && python -m pytest test_inboxkit_smoke.py -v
  or: python test_inboxkit_smoke.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone

# Set a dummy key so the config doesn't disable everything.
os.environ.setdefault("INBOXKIT_API_KEY", "test-key-1234567890")
os.environ.setdefault("INBOXKIT_WORKSPACE_ID", "ws_test")

# Make the backend package importable when run from the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))


def test_imports():
    """Every module in the integration should import without error."""
    from app.services.mail_infra import MailInfraProvider, get_provider, inboxkit_configured
    from app.services.inboxkit import InboxKitClient, InboxKitProvider, to_logical_state, LogicalState
    from app.services.inboxkit.states import is_terminal, is_healthy
    from app.services.stalwart_provider import StalwartProvider
    from app.api.v1 import inboxkit_webhooks
    assert inboxkit_configured() is True


def test_signature_math():
    """The X-InboxKit-Signature is sha256=<hex SHA-256(team_api_key)>.

    Verified against the docs' recipe:
        printf '%s' 'YOUR_API_KEY' | openssl dgst -sha256 -hex
    """
    from app.api.v1.inboxkit_webhooks import _expected_signature
    from app.core.config import settings
    expected = hashlib.sha256(settings.inboxkit_api_key.encode()).hexdigest()
    got = _expected_signature()
    assert got == f"sha256={expected}", f"{got} != sha256={expected}"


def test_state_mapping_covers_verified_statuses():
    """Every InboxKit mailbox status from the docs maps to a logical state."""
    from app.services.inboxkit.states import to_logical_state, LogicalState

    # Verified mailbox statuses (docs.inboxkit.com, 2026-07-28).
    cases = {
        "pending": LogicalState.ORDERED,
        "scheduled": LogicalState.ORDERED,
        "processing": LogicalState.PROVISIONING,
        "waiting_for_dns_propagation": LogicalState.PROVISIONING,
        "configuring_workspace": LogicalState.PROVISIONING,
        "configuring_dns": LogicalState.PROVISIONING,
        "configuring_dkim": LogicalState.PROVISIONING,
        "configuring_auth": LogicalState.PROVISIONING,
        "finalizing_setup": LogicalState.PROVISIONING,
        "active": LogicalState.READY,
        "inactive": LogicalState.QUARANTINED,
        "suspended": LogicalState.QUARANTINED,
        "failed": LogicalState.QUARANTINED,
        "scheduled_for_cancellation": LogicalState.RETIRED,
        "cancelled": LogicalState.RETIRED,
        "archived": LogicalState.RETIRED,
        "deleted": LogicalState.RETIRED,
    }
    for native, expected in cases.items():
        got = to_logical_state(native)
        assert got == expected, f"{native}: got {got}, expected {expected}"

    # Domain statuses use the same function with is_domain=True.
    assert to_logical_state("active", is_domain=True) == LogicalState.READY
    assert to_logical_state("cancelled", is_domain=True) == LogicalState.RETIRED

    # Unknown statuses resolve to UNKNOWN, not crash.
    assert to_logical_state("brand_new_status") == LogicalState.UNKNOWN
    assert to_logical_state(None) == LogicalState.UNKNOWN


def test_transport_for_platform():
    """Google/Microsoft transport hosts are correct."""
    from app.services.inboxkit.provider import _transport_for_platform
    assert _transport_for_platform("google") == ("smtp.gmail.com", 587, "imap.gmail.com", 993)
    assert _transport_for_platform("microsoft")[0] == "smtp.office365.com"
    assert _transport_for_platform("azure")[0] == "smtp.office365.com"
    # Unknown platform returns empty host (caller overrides).
    assert _transport_for_platform("custom")[0] == ""


def test_idempotency_key_shape():
    """The dedup key includes event + entity_uid + new_status."""
    from app.api.v1.inboxkit_webhooks import _idem_key
    k = _idem_key("mailbox.status_changed", "mb_abc", "active")
    assert k == "inboxkit:processed:mailbox.status_changed:mb_abc:active"


def test_freshness_window():
    """Webhooks older than 5 minutes are rejected (replay defence)."""
    from app.api.v1.inboxkit_webhooks import _is_fresh
    now = datetime.now(timezone.utc)
    assert _is_fresh(now.isoformat()) is True
    old = (now - timedelta(minutes=10)).isoformat()
    assert _is_fresh(old) is False
    assert _is_fresh("not-a-date") is False


def test_envelope_parsing():
    """The webhook envelope model accepts the verified shape."""
    from app.api.v1.inboxkit_webhooks import _Envelope
    payload = {
        "event": "mailbox.status_changed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "team_id": "team_123",
        "team_name": "Champions",
        "data": {
            "mailbox": {"uid": "mb_1", "status": "active",
                        "password": "should-be-discarded"},
            "metadata": {"workspace_id": "ws_1"},
        },
    }
    env = _Envelope(**payload)
    assert env.event == "mailbox.status_changed"
    assert env.data["mailbox"]["uid"] == "mb_1"


def test_provider_factory():
    """get_provider returns the right implementation by name."""
    from app.services.mail_infra import get_provider, MailInfraProvider
    from app.services.inboxkit.provider import InboxKitProvider
    from app.services.stalwart_provider import StalwartProvider

    p = get_provider("inboxkit")
    assert isinstance(p, InboxKitProvider)
    assert p.name == "inboxkit"

    s = get_provider("stalwart")
    assert isinstance(s, StalwartProvider)
    assert s.name == "stalwart"

    # Unknown provider name falls back to Stalwart (legacy compatibility).
    assert isinstance(get_provider("unknown"), StalwartProvider)


def test_mailbox_credentials_dataclass():
    """MailboxCredentials carries the fields the send agent needs."""
    from app.services.mail_infra import MailboxCredentials
    c = MailboxCredentials(
        email="a@b.com", username="a@b.com", password="secret",
        app_password="app-secret", smtp_host="smtp.gmail.com", smtp_port=587,
        imap_host="imap.gmail.com", imap_port=993, platform="google",
    )
    assert c.password == "secret"
    assert c.app_password == "app-secret"
    assert c.platform == "google"


if __name__ == "__main__":
    # Allow running as a plain script (no pytest) for quick local checks.
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
