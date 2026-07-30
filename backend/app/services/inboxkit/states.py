"""
InboxKit mailbox/domain status <-> logical spec states.

The ChampMail Build Spec (doc 2, §1) names a logical state machine:
    Ordered -> Provisioning -> Warming -> Ready -> Sending
             -> Throttled / Quarantined -> Retired

InboxKit's real webhook/API statuses are finer-grained and DO NOT include
Warming / Sending / Throttled (warmup is a separate subscription; sending +
throttling are sequencer concerns). This module is the single place that
maps the two vocabularies, so downstream code keys off LogicalState only.

Verified against docs.inboxkit.com (mailbox.status_changed + domain.status_
changed event pages) on 2026-07-28. Open question raised with the InboxKit
team (#championsmail-inboxkit Slack): whether `throttled`/`quarantied` are
ever returned by get-mailbox-details / get-mailbox-health — until confirmed,
we treat `suspended`/`inactive` as Quarantined and never emit Throttled from
InboxKit alone (the send agent may set it from its own bounce-rate watching).
"""
from __future__ import annotations

from enum import Enum


class LogicalState(str, Enum):
    """Provider-agnostic mailbox/domain lifecycle state."""
    ORDERED = "ordered"
    PROVISIONING = "provisioning"
    WARMING = "warming"
    READY = "ready"
    SENDING = "sending"
    THROTTLED = "throttled"
    QUARANTINED = "quarantined"
    RETIRED = "retired"
    UNKNOWN = "unknown"


# InboxKit mailbox statuses (verified) -> logical state.
# Sources: docs.inboxkit.com mailbox.status_changed event page.
_MAILBOX_MAP = {
    # Pre-active
    "pending":                       LogicalState.ORDERED,
    "scheduled":                     LogicalState.ORDERED,
    "processing":                    LogicalState.PROVISIONING,
    "waiting_for_dns_propagation":   LogicalState.PROVISIONING,
    "waiting_for_activation_email":  LogicalState.PROVISIONING,
    "activation_email_received":     LogicalState.PROVISIONING,
    "configuring_workspace":         LogicalState.PROVISIONING,
    "configuring_dns":               LogicalState.PROVISIONING,
    "configuring_dkim":              LogicalState.PROVISIONING,
    "configuring_auth":              LogicalState.PROVISIONING,
    "finalizing_setup":              LogicalState.PROVISIONING,

    # Active
    "active":                        LogicalState.READY,
    "inactive":                      LogicalState.QUARANTINED,  # paused

    # Terminal / failure
    "suspended":                     LogicalState.QUARANTINED,
    "failed":                        LogicalState.QUARANTINED,
    "renewal_failed":                LogicalState.QUARANTINED,
    "scheduled_for_cancellation":    LogicalState.RETIRED,
    "cancelled":                     LogicalState.RETIRED,
    "archived":                      LogicalState.RETIRED,
    "deleted":                       LogicalState.RETIRED,
}

# InboxKit domain statuses (verified) -> logical state.
# Sources: docs.inboxkit.com domain.status_changed event page.
_DOMAIN_MAP = {
    "cart":                          LogicalState.ORDERED,
    "registration_in_progress":      LogicalState.PROVISIONING,
    "dns_setup_pending":             LogicalState.PROVISIONING,
    "waiting_for_dns_propagation":   LogicalState.PROVISIONING,
    "active":                        LogicalState.READY,
    "inactive":                      LogicalState.QUARANTINED,
    "payment_failed":                LogicalState.QUARANTINED,
    "cancelled":                     LogicalState.RETIRED,
    "deleted":                       LogicalState.RETIRED,
}


def to_logical_state(native_status: str | None, *, is_domain: bool = False) -> LogicalState:
    """Map an InboxKit native status string to a LogicalState.

    Unknown values resolve to UNKNOWN rather than raising — a brand-new
    InboxKit status we haven't catalogued should not crash the webhook
    handler; it surfaces in logs and on the domain row's `status` for review.
    """
    if not native_status:
        return LogicalState.UNKNOWN
    table = _DOMAIN_MAP if is_domain else _MAILBOX_MAP
    return table.get(native_status.lower(), LogicalState.UNKNOWN)


def is_terminal(state: LogicalState) -> bool:
    """True for states that no longer transition forward."""
    return state in (LogicalState.RETIRED,)


def is_healthy(state: LogicalState) -> bool:
    """True for states that are cleared to send (Ready/Sending/Warming)."""
    return state in (LogicalState.READY, LogicalState.SENDING, LogicalState.WARMING)
