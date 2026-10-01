"""The IAL health gate and its circuit breaker.

`InboxKitProvider.health()` used to compute:

    infraguard_clean = logical.value in ("ready", "warming", "sending")

— deriving deliverability health from provisioning state, so a fully
blacklisted mailbox reported clean. These tests pin the two properties that
replacement has to get right:

1. a metric that is *unknown* must never block sending (fail open), and
2. a metric that is *bad* must block it.

Getting (1) wrong halts every campaign the moment a metrics endpoint moves.
Getting (2) wrong is the bug this whole module exists to fix.
"""
from __future__ import annotations

import pytest

from app.services.mail_infra import (
    BOUNCE_RATE_QUARANTINE,
    COMPLAINT_RATE_QUARANTINE,
    PLACEMENT_PCT_QUARANTINE,
    HealthSnapshot,
)


# --- fail open on unknown --------------------------------------------------


def test_completely_unknown_health_does_not_block():
    """An InboxKit plan without InfraGuard reports nothing. That must not stop
    outbound — the per-mailbox daily cap already bounds the downside."""
    assert HealthSnapshot().send_block_reason() is None
    assert HealthSnapshot().is_send_blocked() is False


def test_unknown_infraguard_is_not_treated_as_dirty():
    """None means 'cannot see', which is different from False ('confirmed
    dirty'). Conflating them pulls healthy mailboxes out of rotation."""
    snap = HealthSnapshot(infraguard_clean=None, bounce_rate=0.0)
    assert snap.send_block_reason() is None


def test_partial_telemetry_still_evaluates_what_is_known():
    """One unavailable product must not blank out the readable metrics."""
    snap = HealthSnapshot(bounce_rate=0.20, placement_pct=None, infraguard_clean=None)
    assert snap.is_send_blocked() is True
    assert "bounce" in snap.send_block_reason().lower()


# --- block on bad ---------------------------------------------------------


def test_healthy_mailbox_is_allowed():
    snap = HealthSnapshot(
        bounce_rate=0.01, complaint_rate=0.0005, placement_pct=94.0,
        infraguard_clean=True,
    )
    assert snap.send_block_reason() is None


def test_bounce_rate_at_threshold_blocks():
    snap = HealthSnapshot(bounce_rate=BOUNCE_RATE_QUARANTINE)
    assert snap.is_send_blocked() is True


def test_bounce_rate_just_below_threshold_does_not_block():
    snap = HealthSnapshot(bounce_rate=BOUNCE_RATE_QUARANTINE - 0.001)
    assert snap.send_block_reason() is None


def test_complaint_rate_at_threshold_blocks():
    """0.3% is where Google and Microsoft start filtering — a low absolute
    number, which is exactly why it needs its own check rather than being
    folded into bounce rate."""
    snap = HealthSnapshot(complaint_rate=COMPLAINT_RATE_QUARANTINE)
    assert snap.is_send_blocked() is True


def test_blacklisted_domain_blocks():
    snap = HealthSnapshot(infraguard_clean=False)
    reason = snap.send_block_reason()
    assert reason is not None and "blacklist" in reason.lower()


def test_poor_placement_blocks():
    snap = HealthSnapshot(placement_pct=PLACEMENT_PCT_QUARANTINE - 1)
    assert snap.is_send_blocked() is True


def test_good_placement_does_not_block():
    snap = HealthSnapshot(placement_pct=PLACEMENT_PCT_QUARANTINE + 1)
    assert snap.send_block_reason() is None


# --- the reason is usable in a log line -----------------------------------


@pytest.mark.parametrize(
    "snapshot",
    [
        HealthSnapshot(bounce_rate=0.4),
        HealthSnapshot(complaint_rate=0.05),
        HealthSnapshot(infraguard_clean=False),
        HealthSnapshot(placement_pct=10.0),
    ],
)
def test_block_reason_is_descriptive(snapshot: HealthSnapshot):
    reason = snapshot.send_block_reason()
    assert reason and len(reason) > 10, (
        "a quarantine must say why, or operators cannot act on it"
    )


# --- the provider no longer fabricates -----------------------------------


def test_provider_health_no_longer_infers_from_provisioning_state():
    """Regression guard on the specific fabrication that was removed."""
    import inspect

    from app.services.inboxkit import provider

    src = inspect.getsource(provider.InboxKitProvider.health)
    assert 'infraguard_clean=logical.value in' not in src.replace(" ", ""), (
        "health() is inferring deliverability from provisioning state again"
    )
    assert "get_deliverability_client" in src, (
        "health() should read real telemetry"
    )
