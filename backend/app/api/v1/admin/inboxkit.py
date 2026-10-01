"""Admin endpoints for InboxKit integration management.

All endpoints require admin role. Provides:
- GET /admin/inboxkit/status — workspace + configuration state
- POST /admin/inboxkit/webhook — set the webhook URL InboxKit posts events to
- DELETE /admin/inboxkit/webhook — clear the webhook URL
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.admin_security import require_admin
from app.core.security import TokenData
from app.core.config import settings
from app.services.inboxkit.client import InboxKitClient, InboxKitAPIError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inboxkit", tags=["Admin - InboxKit"])


class WebhookUrlRequest(BaseModel):
    url: str


class InboxKitStatusResponse(BaseModel):
    configured: bool
    workspace_id: Optional[str] = None
    webhook_url: Optional[str] = None
    api_key_configured: bool
    webhook_enabled: bool
    base_url: Optional[str] = None


class WebhookUrlResponse(BaseModel):
    webhook_url: str
    status: str


def _get_client() -> InboxKitClient:
    if not settings.inboxkit_api_key:
        raise HTTPException(status_code=400, detail="INBOXKIT_API_KEY not configured")
    return InboxKitClient()


@router.get("/status", response_model=InboxKitStatusResponse)
async def get_inboxkit_status(admin: TokenData = Depends(require_admin)):
    """Return current InboxKit integration status from config + live workspace."""
    configured = bool(settings.inboxkit_api_key and settings.inboxkit_workspace_id)
    webhook_url: Optional[str] = None
    workspace_id: Optional[str] = None

    if configured:
        try:
            client = _get_client()
            resp = await client.list_workspaces()
            workspaces = resp.get("workspaces") or []
            for ws in workspaces:
                if ws.get("uid") == settings.inboxkit_workspace_id:
                    workspace_id = ws.get("uid")
                    webhook_url = ws.get("webhook_url") or None
                    break
            if not workspace_id and workspaces:
                ws = workspaces[0]
                workspace_id = ws.get("uid")
                webhook_url = ws.get("webhook_url") or None
            await client.close()
        except InboxKitAPIError as e:
            raise HTTPException(status_code=502, detail=f"InboxKit API error: {e}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to reach InboxKit: {e}")

    return InboxKitStatusResponse(
        configured=configured,
        workspace_id=workspace_id or settings.inboxkit_workspace_id or None,
        webhook_url=webhook_url,
        api_key_configured=bool(settings.inboxkit_api_key),
        webhook_enabled=settings.inboxkit_webhook_enabled,
        base_url=settings.inboxkit_base_url,
    )


@router.post("/webhook", response_model=WebhookUrlResponse)
async def set_webhook_url(
    body: WebhookUrlRequest,
    admin: TokenData = Depends(require_admin),
):
    """Set the webhook URL InboxKit posts domain/mailbox events to."""
    if not body.url:
        raise HTTPException(status_code=422, detail="url must not be empty")
    try:
        client = _get_client()
        resp = await client.set_workspace_webhook(webhook_url=body.url)
        await client.close()
        logger.info("admin: inboxkit webhook URL set to %s by admin %s", body.url, admin.email)
        return WebhookUrlResponse(webhook_url=body.url, status="set")
    except InboxKitAPIError as e:
        raise HTTPException(status_code=502, detail=f"InboxKit API error: {e}")


@router.delete("/webhook", response_model=WebhookUrlResponse)
async def clear_webhook_url(admin: TokenData = Depends(require_admin)):
    """Clear the webhook URL — InboxKit stops posting events."""
    try:
        client = _get_client()
        resp = await client.set_workspace_webhook(webhook_url="")
        await client.close()
        logger.info("admin: inboxkit webhook URL cleared by admin %s", admin.email)
        return WebhookUrlResponse(webhook_url="", status="cleared")
    except InboxKitAPIError as e:
        raise HTTPException(status_code=502, detail=f"InboxKit API error: {e}")


# ─── Bring-your-own-domain ────────────────────────────────────────────────────
#
# The operator-facing surface for connecting a domain you already own, then
# buying mailboxes on it. Previously the only supported flow was registering a
# brand-new domain through InboxKit (/domains/register); there was no way to
# attach championsmail.com or any other existing domain.
#
# Flow (see docs/inboxkit-byod-runbook.md for the operator walkthrough):
#   1. POST /admin/inboxkit/domain/connect      (managed) — one call, done
#      or
#      GET  /admin/inboxkit/domain/records      (manual)  — returns records
#      ... operator creates them in their DNS provider ...
#      POST /admin/inboxkit/domain/verify       (manual)  — re-check
#   2. POST /admin/inboxkit/domain/mailboxes    — buy mailboxes on the domain


class ConnectDomainRequest(BaseModel):
    domain: str
    # * Cloudflare token for MANAGED mode. Forwarded to InboxKit and never
    # * persisted — there is deliberately no column for it. Scope it to
    # * Zone → DNS → Edit on this single zone, with an expiry.
    cloudflare_api_token: Optional[str] = None
    cloudflare_account_id: Optional[str] = None
    cloudflare_zone_id: Optional[str] = None


class DnsRecordResponse(BaseModel):
    type: str
    name: str
    value: str
    priority: Optional[int] = None
    ttl: Optional[int] = None
    purpose: Optional[str] = None


class ConnectDomainResponse(BaseModel):
    domain: str
    mode: str
    connected: bool
    domain_uid: Optional[str] = None
    native_status: Optional[str] = None
    records_required: list[DnsRecordResponse] = []
    needs_manual_dns: bool = False
    message: Optional[str] = None


class BuyMailboxesRequest(BaseModel):
    domain: str
    # Usernames only — the domain is appended by InboxKit.
    usernames: list[str]
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    platform: str = "google"          # google | microsoft | azure | smtp
    start_warmup: bool = False        # $3/mailbox/month — opt in explicitly


class BuyMailboxesResponse(BaseModel):
    domain: str
    requested: int
    purchased: int
    warmup_started: bool
    mailboxes: list[dict] = []
    message: Optional[str] = None


def _record_response(record) -> DnsRecordResponse:
    return DnsRecordResponse(**record.as_dict())


def _connect_response(result) -> ConnectDomainResponse:
    return ConnectDomainResponse(
        domain=result.domain,
        mode=result.mode.value,
        connected=result.connected,
        domain_uid=result.domain_uid,
        native_status=result.native_status,
        records_required=[_record_response(r) for r in result.records_required],
        needs_manual_dns=result.needs_manual_dns,
        message=result.message,
    )


@router.post("/domain/connect", response_model=ConnectDomainResponse)
async def connect_existing_domain(
    body: ConnectDomainRequest,
    admin: TokenData = Depends(require_admin),
):
    """Attach a domain you already own to the InboxKit workspace.

    With `cloudflare_api_token`: InboxKit writes the DNS records itself
    (MANAGED). Without it: returns the records for you to create manually, then
    call /domain/verify.
    """
    from app.services.inboxkit.domain_connect import get_domain_connect_client

    client = get_domain_connect_client()
    try:
        if body.cloudflare_api_token:
            result = await client.connect_managed(
                body.domain,
                cloudflare_api_token=body.cloudflare_api_token,
                cloudflare_account_id=body.cloudflare_account_id,
                cloudflare_zone_id=body.cloudflare_zone_id,
            )
            # ! Never log the token, and never echo it back in the response.
            logger.info(
                "admin: inboxkit managed connect for %s by %s -> connected=%s",
                body.domain, admin.email, result.connected,
            )
        else:
            records = await client.required_records(body.domain)
            from app.services.inboxkit.domain_connect import ConnectMode, ConnectResult

            result = ConnectResult(
                domain=body.domain,
                mode=ConnectMode.MANUAL,
                connected=False,
                records_required=records,
                message=(
                    "Create these records in your DNS provider, then POST "
                    "/admin/inboxkit/domain/verify."
                    if records else
                    "No records returned — the DNS endpoint path may need "
                    "pinning (see domain_connect.py docstring)."
                ),
            )
            logger.info(
                "admin: inboxkit manual connect for %s by %s -> %d record(s)",
                body.domain, admin.email, len(records),
            )
        return _connect_response(result)
    except InboxKitAPIError as e:
        raise HTTPException(status_code=502, detail=f"InboxKit API error: {e}")


@router.get("/domain/records", response_model=list[DnsRecordResponse])
async def get_required_dns_records(
    domain: str,
    admin: TokenData = Depends(require_admin),
):
    """The DNS records this domain needs before mailboxes can be provisioned."""
    from app.services.inboxkit.domain_connect import get_domain_connect_client

    try:
        records = await get_domain_connect_client().required_records(domain)
        return [_record_response(r) for r in records]
    except InboxKitAPIError as e:
        raise HTTPException(status_code=502, detail=f"InboxKit API error: {e}")


@router.post("/domain/verify", response_model=ConnectDomainResponse)
async def verify_domain_dns(
    body: ConnectDomainRequest,
    admin: TokenData = Depends(require_admin),
):
    """Re-check DNS after creating records manually. Safe to poll."""
    from app.services.inboxkit.domain_connect import get_domain_connect_client

    try:
        result = await get_domain_connect_client().verify_dns(body.domain)
        logger.info(
            "admin: inboxkit dns verify for %s by %s -> connected=%s",
            body.domain, admin.email, result.connected,
        )
        return _connect_response(result)
    except InboxKitAPIError as e:
        raise HTTPException(status_code=502, detail=f"InboxKit API error: {e}")


@router.get("/domain/connected")
async def list_connected_domains(admin: TokenData = Depends(require_admin)):
    """Domains currently connected to this workspace."""
    from app.services.inboxkit.domain_connect import get_domain_connect_client

    try:
        return {"domains": await get_domain_connect_client().list_connected()}
    except InboxKitAPIError as e:
        raise HTTPException(status_code=502, detail=f"InboxKit API error: {e}")


@router.post("/domain/mailboxes", response_model=BuyMailboxesResponse)
async def buy_mailboxes_on_domain(
    body: BuyMailboxesRequest,
    admin: TokenData = Depends(require_admin),
):
    """Buy mailboxes on a connected domain.

    Warmup is opt-in (`start_warmup`) because it bills $3/mailbox/month. Leave it
    off while sending only to inboxes you own — warmup only matters once you mail
    strangers.
    """
    from app.services.mail_infra import get_provider

    if not body.usernames:
        raise HTTPException(status_code=400, detail="usernames must not be empty")

    provider = get_provider("inboxkit")
    purchased: list[dict] = []
    try:
        for username in body.usernames:
            record = await provider.buy_mailbox(
                body.domain,
                username,
                first_name=body.first_name,
                last_name=body.last_name,
                platform=body.platform,
            )
            purchased.append(
                {
                    "uid": record.uid,
                    "email": record.email,
                    "status": record.status,
                    "native_status": record.native_status,
                }
            )

        warmup_started = False
        if body.start_warmup and purchased:
            warmup_started = await provider.start_warmup(
                [m["uid"] for m in purchased if m.get("uid")]
            )

        logger.info(
            "admin: bought %d/%d mailbox(es) on %s by %s (warmup=%s)",
            len(purchased), len(body.usernames), body.domain, admin.email,
            warmup_started,
        )
        return BuyMailboxesResponse(
            domain=body.domain,
            requested=len(body.usernames),
            purchased=len(purchased),
            warmup_started=warmup_started,
            mailboxes=purchased,
            message=(
                "Mailboxes provisioning. Watch mailbox.status_changed webhooks; "
                "credentials are fetched only once status reaches active."
            ),
        )
    except InboxKitAPIError as e:
        # Partial success is real: some mailboxes may already be provisioning.
        raise HTTPException(
            status_code=502,
            detail=(
                f"InboxKit API error after purchasing {len(purchased)} of "
                f"{len(body.usernames)}: {e}"
            ),
        )
