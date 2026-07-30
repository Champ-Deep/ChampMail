"""
Infrastructure Abstraction Layer (IAL) for mailbox provisioning.

The one interface ChampMail's sending engine talks to, so it never knows or
cares whether a mailbox is InboxKit-provisioned or Stalwart-native. Mirrors
the architecture doc's MailInfraProvider protocol (Sections 2.1-2.3) and the
ChampMail Build Spec §1.

Two implementations live alongside this ABC:
- InboxKitProvider   (services/inboxkit/provider.py) — buys + manages mailboxes via api.inboxkit.com
- StalwartProvider   (services/email_provider.py)    — the existing self-hosted SMTP/IMAP stack

State machine (logical, provider-agnostic — providers map their own native
statuses onto these via states.py):
    Ordered -> Provisioning -> Warming -> Ready -> Sending -> Throttled/Quarantined -> Retired

A provider that cannot reach the upstream API should raise, never silently
return a stale record — the send agent treats an unreachable provider as a
hard failure for that mailbox, not as "use the last known creds."
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.core.config import settings


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------

@dataclass
class MailboxCredentials:
    """SMTP/IMAP credentials for a single mailbox.

    Plaintext only in-memory between the provider and the secret store; the
    InboxKitProvider re-fetches these from GET /mailboxes/show-credentials
    (never from a webhook payload) and the caller is responsible for
    encrypting them before persistence.
    """
    email: str
    username: str
    password: str
    app_password: Optional[str] = None
    secret: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    platform: Optional[str] = None          # google | microsoft | azure | smtp
    fetched_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DomainRecord:
    """A domain bought through / known to the provider."""
    uid: str                                # provider-native id
    name: str
    status: str                             # logical status (states.LogicalState)
    native_status: Optional[str] = None     # provider's raw status string
    renewal_date: Optional[str] = None
    workspace_uid: Optional[str] = None


@dataclass
class MailboxRecord:
    """A mailbox bought through / known to the provider."""
    uid: str
    email: str
    status: str                             # logical status
    native_status: Optional[str] = None
    platform: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    domain_uid: Optional[str] = None
    domain_name: Optional[str] = None
    workspace_uid: Optional[str] = None


#: Thresholds at which a mailbox is pulled from rotation.
#:
#: Grounded in what mailbox providers actually act on, not in round numbers:
#: sustained bounce above ~5% and complaint above ~0.3% are the levels at which
#: Google and Microsoft begin throttling or filtering a sender. Placement below
#: 70% means nearly a third of sends are already not being seen, so continuing
#: to send is spending reputation for no return.
BOUNCE_RATE_QUARANTINE = 0.05
COMPLAINT_RATE_QUARANTINE = 0.003
PLACEMENT_PCT_QUARANTINE = 70.0


@dataclass
class HealthSnapshot:
    """Mailbox/domain deliverability health — the IAL health gate inputs.

    Every metric is Optional and None means **unknown**, never "fine". A
    provider that cannot report bounce rate must not be indistinguishable from
    one reporting 0%.
    """
    placement_pct: Optional[float] = None       # inbox placement, 0-100
    bounce_rate: Optional[float] = None         # 0-1
    complaint_rate: Optional[float] = None      # 0-1
    infraguard_clean: Optional[bool] = None
    warmup_day: Optional[int] = None
    last_checked: Optional[datetime] = None

    def send_block_reason(self) -> Optional[str]:
        """Why this mailbox should stop sending, or None if it may continue.

        The circuit breaker. Returns a human-readable reason so the caller can
        log *why* a mailbox was quarantined rather than just that it was.

        Fails OPEN on unknown data — a metric that is None never blocks. That is
        the deliberate choice: an InboxKit plan without InfraGuard, or a
        telemetry outage, must not silently halt all outbound. The cost of
        continuing to send on unknown health is bounded (the per-mailbox daily
        cap); the cost of halting every campaign because a metrics endpoint
        moved is not.
        """
        if self.bounce_rate is not None and self.bounce_rate >= BOUNCE_RATE_QUARANTINE:
            return (
                f"bounce rate {self.bounce_rate:.1%} at or above "
                f"{BOUNCE_RATE_QUARANTINE:.0%}"
            )
        if (
            self.complaint_rate is not None
            and self.complaint_rate >= COMPLAINT_RATE_QUARANTINE
        ):
            return (
                f"complaint rate {self.complaint_rate:.2%} at or above "
                f"{COMPLAINT_RATE_QUARANTINE:.1%}"
            )
        if self.infraguard_clean is False:
            return "InfraGuard reports a blacklist or DNS problem"
        if (
            self.placement_pct is not None
            and self.placement_pct < PLACEMENT_PCT_QUARANTINE
        ):
            return (
                f"inbox placement {self.placement_pct:.0f}% below "
                f"{PLACEMENT_PCT_QUARANTINE:.0f}%"
            )
        return None

    def is_send_blocked(self) -> bool:
        return self.send_block_reason() is not None


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------

class MailInfraProvider(ABC):
    """Mailbox infrastructure provider.

    All async methods are safe to call from the FastAPI/Celery event loop.
    Implementations must be idempotent on retries (the send agent may invoke
    `get_credentials` more than once for the same mailbox across re-send
    attempts) and must never log credential plaintext.
    """

    name: str   # "inboxkit" | "stalwart"

    # --- Domain lifecycle -------------------------------------------------

    @abstractmethod
    async def search_domains(self, keyword: str, tlds: Optional[list[str]] = None,
                             limit: int = 20) -> list[dict]:
        """Search available domains for purchase."""
        ...

    @abstractmethod
    async def buy_domain(self, domain_name: str, registration_years: int = 1,
                         **opts) -> DomainRecord:
        """Purchase / register a domain. Returns the provider's record."""
        ...

    @abstractmethod
    async def get_domain(self, uid: str) -> Optional[DomainRecord]:
        """Fetch authoritative state for one domain."""
        ...

    # --- Mailbox lifecycle ------------------------------------------------

    @abstractmethod
    async def buy_mailbox(self, domain_uid: str, username: str,
                          platform: str = "google",
                          first_name: str = "", last_name: str = "") -> MailboxRecord:
        """Provision a new mailbox on an already-added domain."""
        ...

    @abstractmethod
    async def get_mailbox(self, uid: str) -> Optional[MailboxRecord]:
        """Fetch authoritative state for one mailbox (re-fetch pattern)."""
        ...

    @abstractmethod
    async def get_credentials(self, uid: str) -> MailboxCredentials:
        """Pull SMTP/IMAP credentials via the AUTHENTICATED REST call.

        This is the only source of truth for credentials. Webhook payloads
        that happen to carry plaintext creds are treated as a hint only.
        """
        ...

    @abstractmethod
    async def list_mailboxes(self, domain_uid: Optional[str] = None,
                             status: Optional[str] = None) -> list[MailboxRecord]:
        """List mailboxes, optionally filtered."""
        ...

    @abstractmethod
    async def cancel_mailbox(self, uid: str) -> bool:
        """Retire / schedule a mailbox for cancellation."""
        ...

    # --- Warmup -----------------------------------------------------------

    @abstractmethod
    async def start_warmup(self, mailbox_uids: list[str]) -> bool:
        """Activate warmup for the given mailboxes."""
        ...

    @abstractmethod
    async def pause_warmup(self, mailbox_uids: list[str]) -> bool:
        """Pause warmup without cancelling."""
        ...

    # --- Health -----------------------------------------------------------

    @abstractmethod
    async def health(self, uid: str) -> HealthSnapshot:
        """Latest deliverability / reputation snapshot for a mailbox or domain."""
        ...


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_inboxkit_provider: Optional[MailInfraProvider] = None
_stalwart_provider: Optional[MailInfraProvider] = None


def get_inboxkit_provider() -> MailInfraProvider:
    """Return the cached InboxKit provider, or raise if not configured."""
    global _inboxkit_provider
    if _inboxkit_provider is None:
        from app.services.inboxkit.provider import InboxKitProvider
        _inboxkit_provider = InboxKitProvider()
    return _inboxkit_provider


def get_stalwart_provider() -> MailInfraProvider:
    """Return the cached Stalwart provider (the legacy self-hosted stack)."""
    global _stalwart_provider
    if _stalwart_provider is None:
        from app.services.stalwart_provider import StalwartProvider
        _stalwart_provider = StalwartProvider()
    return _stalwart_provider


def get_provider(infra_provider: str) -> MailInfraProvider:
    """Resolve a provider by its logical name.

    `infra_provider` is the value stored on Domain.infra_provider. Falls back
    to Stalwart for unknown / null values so legacy domains keep working.
    """
    if infra_provider == "inboxkit":
        if not settings.inboxkit_api_key:
            raise RuntimeError(
                "INBOXKIT_API_KEY is not set; cannot use the InboxKit provider"
            )
        return get_inboxkit_provider()
    return get_stalwart_provider()


def inboxkit_configured() -> bool:
    """True iff InboxKit is usable in this process (non-empty key + workspace)."""
    return bool(settings.inboxkit_api_key and settings.inboxkit_workspace_id)
