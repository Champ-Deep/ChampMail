"""
InboxKitProvider — MailInfraProvider implementation for api.inboxkit.com.

This is the load-bearing provider for the ChampMail Build Spec (doc 2, §1).
Every method delegates to InboxKitClient and reshapes the response into the
IAL value types. Credentials are NEVER accepted from webhook payloads —
get_credentials always calls the authenticated
GET /v1/api/mailboxes/show-credentials endpoint (see webhooks.py for the
hint-vs-fact pattern).

All network errors propagate as InboxKitAPIError; the caller (send agent,
warmup task, or webhook handler) decides whether to retry or fail the
mailbox.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.services.inboxkit.client import InboxKitClient, InboxKitAPIError, get_client
from app.services.inboxkit.states import to_logical_state, LogicalState
from app.services.mail_infra import (
    MailInfraProvider,
    MailboxCredentials,
    MailboxRecord,
    DomainRecord,
    HealthSnapshot,
)

logger = logging.getLogger(__name__)


class InboxKitProvider(MailInfraProvider):
    """MailInfraProvider backed by InboxKit."""

    name = "inboxkit"

    def __init__(self, client: Optional[InboxKitClient] = None):
        self._client = client or get_client()

    # ------------------------------------------------------------------ domains

    async def search_domains(self, keyword: str, tlds: Optional[list[str]] = None,
                             limit: int = 20) -> list[dict]:
        resp = await self._client.search_domains(keyword=keyword, tlds=tlds, num=limit)
        # InboxKit returns either {"domains": [...]} or a bare list; normalise.
        if isinstance(resp, dict):
            return resp.get("domains") or resp.get("data") or []
        return resp or []

    async def buy_domain(self, domain_name: str, registration_years: int = 1,
                         **opts) -> DomainRecord:
        resp = await self._client.register_domain(
            domain_name=domain_name,
            registration_years=registration_years,
            use_wallet_balance=opts.get("use_wallet_balance", False),
            contact_details=opts.get("contact_details"),
            dmarc_email=opts.get("dmarc_email", ""),
            catch_all_email=opts.get("catch_all_email", ""),
        )
        # register returns either a Stripe checkout (url + domain_uids) or a
        # wallet confirmation. In both cases domain_uids is the handle list.
        uids = resp.get("domain_uids") or []
        uid = uids[0] if uids else ""
        return DomainRecord(
            uid=uid,
            name=domain_name,
            status=LogicalState.ORDERED.value,
            native_status="registration_in_progress",
            workspace_uid=self._client._workspace_id,
        )

    async def get_domain(self, uid: str) -> Optional[DomainRecord]:
        # InboxKit has get-domain-details; we use the status batch endpoint
        # with domain_uids to fetch authoritative state without needing the
        # dedicated path (keeps the client surface small).
        try:
            resp = await self._client.mailbox_status(domain_uids=[uid])
        except InboxKitAPIError as e:
            logger.warning("inboxkit get_domain %s failed: %s", uid, e)
            return None
        domains = resp.get("domains") or []
        if not domains:
            return None
        d = domains[0]
        native = d.get("status", "")
        return DomainRecord(
            uid=d.get("uid", uid),
            name=d.get("name", ""),
            status=to_logical_state(native, is_domain=True).value,
            native_status=native,
            renewal_date=d.get("renewal_date"),
            workspace_uid=d.get("workspace_id") or self._client._workspace_id,
        )

    # ------------------------------------------------------------------ mailboxes

    async def buy_mailbox(self, domain_uid: str, username: str,
                          platform: str = "google",
                          first_name: str = "", last_name: str = "") -> MailboxRecord:
        # /mailboxes/buy takes domain_name, not uid; the caller (provider
        # factory in the API layer) resolves uid->name before calling. We
        # accept domain_uid for IAL parity and pass it through as domain_name
        # when it already looks like a domain.
        domain_name = domain_uid if "." in domain_uid else domain_uid
        resp = await self._client.buy_mailbox(
            domain_name=domain_name,
            username=username,
            platform=platform,
            first_name=first_name,
            last_name=last_name,
        )
        mailboxes = resp.get("mailboxes") or []
        m = mailboxes[0] if mailboxes else {}
        native = m.get("status", "pending")
        return MailboxRecord(
            uid=m.get("uid", ""),
            email=m.get("email", f"{username}@{domain_name}"),
            status=to_logical_state(native).value,
            native_status=native,
            platform=m.get("platform", platform),
            first_name=first_name,
            last_name=last_name,
            domain_name=domain_name,
            workspace_uid=self._client._workspace_id,
        )

    async def get_mailbox(self, uid: str) -> Optional[MailboxRecord]:
        try:
            resp = await self._client.mailbox_status(uids=[uid])
        except InboxKitAPIError as e:
            logger.warning("inboxkit get_mailbox %s failed: %s", uid, e)
            return None
        mailboxes = resp.get("mailboxes") or []
        if not mailboxes:
            return None
        m = mailboxes[0]
        native = m.get("status", "")
        return MailboxRecord(
            uid=m.get("uid", uid),
            email=m.get("email", ""),
            status=to_logical_state(native).value,
            native_status=native,
            platform=m.get("platform"),
            first_name=m.get("first_name"),
            last_name=m.get("last_name"),
            domain_uid=m.get("domain_id"),
            domain_name=m.get("domain_name"),
            workspace_uid=m.get("workspace_id") or self._client._workspace_id,
        )

    async def get_credentials(self, uid: str) -> MailboxCredentials:
        """The authenticated credentials call. Re-fetch, never trust webhooks.

        InboxKit returns {password, secret, app_password} for a Google /
        Microsoft / Azure mailbox. SMTP/IMAP host/port are not in the
        response — Google Workspace uses smtp.gmail.com:587 / imap.gmail.com:993,
        Microsoft 365 uses smtp.office365.com:587 / outlook.office365.com:993,
        Azure tenant mailboxes use the tenant's MX target. We pick by platform
        from the mailbox record; callers may override.
        """
        resp = await self._client.show_credentials(uid=uid)
        password = resp.get("password", "")
        app_password = resp.get("app_password")
        secret = resp.get("secret")

        # Fetch the mailbox to learn platform + email.
        mb = await self.get_mailbox(uid)
        platform = (mb.platform if mb else "google") or "google"
        email_addr = (mb.email if mb else "") or resp.get("email", "")

        smtp_host, smtp_port, imap_host, imap_port = _transport_for_platform(platform)

        # For Google/Microsoft the usable SMTP password is app_password, not
        # the account password (which is admin-console only). Fall back
        # gracefully for SMTP-platform mailboxes that only have `password`.
        smtp_password = app_password or password or secret or ""

        return MailboxCredentials(
            email=email_addr,
            username=email_addr or smtp_password,
            password=smtp_password,
            app_password=app_password,
            secret=secret,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            imap_host=imap_host,
            imap_port=imap_port,
            platform=platform,
        )

    async def list_mailboxes(self, domain_uid: Optional[str] = None,
                             status: Optional[str] = None) -> list[MailboxRecord]:
        # Verified live: the unfiltered list uses POST /mailboxes/list; a
        # domain-scoped list uses /mailboxes/status with domain_uids.
        if domain_uid:
            resp = await self._client.mailbox_status(domain_uids=[domain_uid])
        else:
            resp = await self._client.list_mailboxes()
        mailboxes = resp.get("mailboxes") or []
        out: list[MailboxRecord] = []
        for m in mailboxes:
            native = m.get("status", "")
            logical = to_logical_state(native).value
            if status and logical != status:
                continue
            out.append(MailboxRecord(
                uid=m.get("uid", ""),
                email=m.get("email", ""),
                status=logical,
                native_status=native,
                platform=m.get("platform"),
                first_name=m.get("first_name"),
                last_name=m.get("last_name"),
                domain_uid=m.get("domain_id"),
                domain_name=m.get("domain_name"),
                workspace_uid=m.get("workspace_id") or self._client._workspace_id,
            ))
        return out

    async def cancel_mailbox(self, uid: str) -> bool:
        try:
            await self._client.cancel_mailbox([uid])
            return True
        except InboxKitAPIError as e:
            logger.error("inboxkit cancel_mailbox %s failed: %s", uid, e)
            return False

    # ------------------------------------------------------------------ warmup

    async def start_warmup(self, mailbox_uids: list[str]) -> bool:
        try:
            await self._client.add_warmup(mailbox_uids)
            return True
        except InboxKitAPIError as e:
            logger.error("inboxkit start_warmup %s failed: %s", mailbox_uids, e)
            return False

    async def pause_warmup(self, mailbox_uids: list[str]) -> bool:
        try:
            await self._client.pause_warmup(mailbox_uids)
            return True
        except InboxKitAPIError as e:
            logger.error("inboxkit pause_warmup %s failed: %s", mailbox_uids, e)
            return False

    # ------------------------------------------------------------------ health

    async def health(self, uid: str) -> HealthSnapshot:
        """Real health snapshot from InboxKit's deliverability telemetry.

        This previously fabricated its answer:

            infraguard_clean = logical.value in ("ready", "warming", "sending")

        i.e. it inferred "healthy" from "finished provisioning", which carries
        no deliverability information whatsoever — a fully blacklisted mailbox
        reported clean. It now reads Email Insights (bounce/complaint), Inbox
        Placement and InfraGuard (blacklist/DNS).

        Fields that cannot be read stay None rather than being invented. None
        means "unknown" and must never be treated as a failure: see
        `is_send_blocked()` for the distinction. Telemetry being unavailable is
        not a reason to stop sending, but it IS a reason not to claim health.
        """
        from .deliverability import get_deliverability_client

        mb = await self.get_mailbox(uid)
        if mb is None:
            return HealthSnapshot()

        telemetry = get_deliverability_client()
        snapshot = HealthSnapshot(
            last_checked=__import__("datetime").datetime.utcnow(),
        )

        # Each read is independently guarded: one unavailable product (e.g. no
        # InfraGuard subscription) must not blank out the fields that ARE
        # readable.
        try:
            snapshot.bounce_rate = await telemetry.bounce_rate(uid)
        except Exception:
            logger.exception("inboxkit health: bounce_rate failed for %s", uid)
        try:
            snapshot.complaint_rate = await telemetry.complaint_rate(uid)
        except Exception:
            logger.exception("inboxkit health: complaint_rate failed for %s", uid)
        try:
            snapshot.placement_pct = await telemetry.placement_pct(uid)
        except Exception:
            logger.exception("inboxkit health: placement_pct failed for %s", uid)

        if mb.domain_name:
            try:
                snapshot.infraguard_clean = await telemetry.infraguard_clean(
                    mb.domain_name
                )
            except Exception:
                logger.exception(
                    "inboxkit health: infraguard_clean failed for %s", mb.domain_name
                )

        return snapshot


def _transport_for_platform(platform: str) -> tuple[str, int, str, int]:
    """Return (smtp_host, smtp_port, imap_host, imap_port) for a platform.

    Verified against InboxKit's documented mailbox platforms (google,
    microsoft, azure, smtp). Azure tenant mailboxes use the tenant's MX
    target, which we cannot know without a DNS lookup — for those we return
    the Microsoft 365 defaults and let the send agent override from the
    domain's DNS records.
    """
    p = (platform or "").lower()
    if p == "google":
        return ("smtp.gmail.com", 587, "imap.gmail.com", 993)
    if p in ("microsoft", "azure", "microsoft_365", "office365"):
        return ("smtp.office365.com", 587, "outlook.office365.com", 993)
    # Plain SMTP-platform (InboxKit's catch-all) — caller must override.
    return ("", 587, "", 993)
