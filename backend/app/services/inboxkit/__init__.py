"""InboxKit integration package — mailbox infrastructure provider.

Implements MailInfraProvider against api.inboxkit.com (verified surface, see
docs.inboxkit.com). Four webhook events are routed through webhooks.py using
the re-fetch pattern mandated by the build spec: every event is a hint, never
a fact.
"""
from app.services.inboxkit.client import InboxKitClient
from app.services.inboxkit.provider import InboxKitProvider
from app.services.inboxkit.states import to_logical_state, LogicalState

__all__ = ["InboxKitClient", "InboxKitProvider", "to_logical_state", "LogicalState"]
