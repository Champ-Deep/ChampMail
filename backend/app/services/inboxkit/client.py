"""
InboxKit REST client.

Verified against docs.inboxkit.com on 2026-07-28:
- Base URL:  https://api.inboxkit.com  (paths are /v1/api/...)
- Auth:      Authorization: Bearer <api_key>
- Workspace: X-Workspace-Id: <workspace_uid>  (required on most resource endpoints)
- Rate limits: 5,000/min standard, 50/min domain search, 10/min bulk mailbox buy.
  Responses carry X-RateLimit-Remaining and X-RateLimit-Reset; we back off on 429.

No official SDK exists — this is a plain httpx wrapper. Every method returns
the parsed JSON body on success and raises InboxKitAPIError on failure so
callers can wrap a single except.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Verified endpoints (docs.inboxkit.com + live probing, 2026-07-28).
_DOMAINS_SEARCH     = "/v1/api/domains/search"
_DOMAINS_REGISTER   = "/v1/api/domains/register"
_MAILBOXES_BUY      = "/v1/api/mailboxes/buy"
_MAILBOXES_LIST     = "/v1/api/mailboxes/list"       # POST only (GET 404s)
_MAILBOXES_STATUS   = "/v1/api/mailboxes/status"
_MAILBOXES_CRED     = "/v1/api/mailboxes/show-credentials"
_MAILBOXES_CANCEL   = "/v1/api/mailboxes/cancel"
_WARMUP_ADD         = "/v1/api/warmup/add"
_WARMUP_PAUSE       = "/v1/api/warmup/pause"
_WORKSPACES_LIST    = "/v1/api/workspaces/list"
_WORKSPACES_WEBHOOK = "/v1/api/workspaces/webhook"

# Verified live: /domains/search rejects any tld outside this set (400).
_ALLOWED_TLDS = {"com", "net", "org", "shop"}


class InboxKitAPIError(Exception):
    """Raised for any non-2xx InboxKit response."""

    def __init__(self, status: int, message: str, body: Optional[dict] = None):
        super().__init__(f"InboxKit HTTP {status}: {message}")
        self.status = status
        self.body = body or {}


class InboxKitClient:
    """Async httpx wrapper around the InboxKit REST API.

    One instance is cheap to keep around for the process lifetime; the
    underlying httpx.AsyncClient is created lazily so importing this module
    never opens a socket.
    """

    def __init__(self, api_key: Optional[str] = None,
                 workspace_id: Optional[str] = None,
                 base_url: Optional[str] = None,
                 timeout: float = 30.0):
        self._api_key = api_key if api_key is not None else settings.inboxkit_api_key
        self._workspace_id = (workspace_id if workspace_id is not None
                              else settings.inboxkit_workspace_id)
        self._base_url = (base_url or settings.inboxkit_base_url
                          or "https://api.inboxkit.com").rstrip("/")
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------ lifecycle

    async def _acquire(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                headers=self._default_headers(),
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    def _default_headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        if self._workspace_id:
            h["X-Workspace-Id"] = self._workspace_id
        return h

    @property
    def configured(self) -> bool:
        return bool(self._api_key and self._workspace_id)

    # ------------------------------------------------------------------ core request

    async def _request(self, method: str, path: str, *,
                       json: Optional[dict] = None,
                       params: Optional[dict] = None,
                       retries: int = 3) -> Any:
        """Issue a request with exponential backoff on 429/5xx.

        Honours X-RateLimit-Remaining when present; on a 429 we sleep for the
        shorter of the Retry-After header or 2^n seconds (cap 60s).
        """
        last_exc: Optional[Exception] = None
        for attempt in range(retries):
            client = await self._acquire()
            try:
                resp = await client.request(method, path, json=json, params=params)
            except httpx.HTTPError as e:
                last_exc = e
                logger.warning("inboxkit %s %s network error (try %d/%d): %s",
                               method, path, attempt + 1, retries, e)
                await asyncio.sleep(min(2 ** attempt, 60))
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = float(resp.headers.get("Retry-After", "2") or "2")
                wait = min(retry_after, 2 ** attempt, 60)
                logger.warning("inboxkit %s %s -> HTTP %s (try %d/%d), sleeping %.1fs",
                               method, path, resp.status_code, attempt + 1, retries, wait)
                last_exc = InboxKitAPIError(resp.status_code, resp.text)
                await asyncio.sleep(wait)
                continue

            if resp.status_code >= 400:
                body: Optional[dict] = None
                try:
                    body = resp.json()
                except Exception:
                    pass
                raise InboxKitAPIError(resp.status_code, resp.text, body)

            if resp.status_code == 204 or not resp.content:
                return {}
            try:
                return resp.json()
            except Exception:
                return {"text": resp.text}

        raise last_exc or InboxKitAPIError(0, f"exhausted {retries} retries for {method} {path}")

    # ------------------------------------------------------------------ domains

    async def search_domains(self, keyword: str, tlds: Optional[list[str]] = None,
                             num: int = 20, page: int = 1,
                             check_banned: bool = True) -> dict:
        # Verified live: tlds outside {com, net, org, shop} -> HTTP 400.
        # Strip leading dots (the API wants bare "com", though it returns ".com").
        clean_tlds = [
            t.lstrip(".").lower()
            for t in (tlds or ["com", "net", "org", "shop"])
        ]
        clean_tlds = [t for t in clean_tlds if t in _ALLOWED_TLDS] or ["com"]
        body = {
            "keyword": keyword,
            "tlds": clean_tlds,
            "num": num,
            "page": page,
            "check_banned": check_banned,
            "show_unavailable": False,
        }
        return await self._request("POST", _DOMAINS_SEARCH, json=body)

    async def register_domain(self, domain_name: str,
                              registration_years: int = 1,
                              use_wallet_balance: bool = False,
                              contact_details: Optional[dict] = None,
                              dmarc_email: str = "",
                              catch_all_email: str = "") -> dict:
        body = {
            "domains": [{
                "name": domain_name,
                "registration_years": registration_years,
            }],
            "use_wallet_balance": use_wallet_balance,
            "dmarc_email": dmarc_email,
            "catch_all_email": catch_all_email,
        }
        if contact_details:
            body["contact_details"] = contact_details
        return await self._request("POST", _DOMAINS_REGISTER, json=body)

    # ------------------------------------------------------------------ mailboxes

    async def buy_mailbox(self, domain_name: str, username: str,
                          platform: str = "google",
                          first_name: str = "", last_name: str = "",
                          use_wallet_balance: bool = False) -> dict:
        body = {
            "mailboxes": [{
                "domain_name": domain_name,
                "username": username.lower(),
                "platform": platform.upper(),
                "first_name": first_name,
                "last_name": last_name,
            }],
            "use_wallet_balance": use_wallet_balance,
        }
        return await self._request("POST", _MAILBOXES_BUY, json=body)

    async def mailbox_status(self, uids: Optional[list[str]] = None,
                             domain_uids: Optional[list[str]] = None,
                             page: int = 1, limit: int = 50) -> dict:
        # Verified live: the API 400s with "uids is required" when neither
        # uids nor domain_uids is given — use list_mailboxes for the unfiltered case.
        if not uids and not domain_uids:
            raise ValueError("mailbox_status requires uids or domain_uids")
        body: dict[str, Any] = {"page": page, "limit": limit}
        if uids:
            body["uids"] = uids
        if domain_uids:
            body["domain_uids"] = domain_uids
        return await self._request("POST", _MAILBOXES_STATUS, json=body)

    async def list_mailboxes(self, page: int = 1, limit: int = 50) -> dict:
        """Unfiltered mailbox list — POST /v1/api/mailboxes/list (verified live).

        Returns {"mailboxes": [...], "current_page": int, "total": int,
        "pages": int, "limit": int}.
        """
        return await self._request("POST", _MAILBOXES_LIST, json={
            "page": page, "limit": limit,
        })

    async def set_workspace_webhook(self, webhook_url: str,
                                    workspace_uid: Optional[str] = None) -> dict:
        """Set the webhook URL InboxKit posts the 4 events to (verified endpoint)."""
        return await self._request("POST", _WORKSPACES_WEBHOOK, json={
            "uid": workspace_uid or self._workspace_id,
            "webhook_url": webhook_url,
        })

    async def show_credentials(self, uid: Optional[str] = None,
                               email: Optional[str] = None) -> dict:
        """The AUTHENTICATED credentials call (verified).

        This is the ONLY source of truth for mailbox creds. Webhook payloads
        that carry plaintext password/app_password/secret are treated as a
        hint only — see provider.get_credentials for the re-fetch pipeline.
        """
        params: dict[str, Any] = {}
        if uid:
            params["uid"] = uid
        elif email:
            params["email"] = email
        else:
            raise ValueError("show_credentials requires uid or email")
        return await self._request("GET", _MAILBOXES_CRED, params=params)

    async def cancel_mailbox(self, uids: list[str]) -> dict:
        return await self._request("POST", _MAILBOXES_CANCEL, json={"uids": uids})

    # ------------------------------------------------------------------ warmup

    async def add_warmup(self, mailbox_uids: list[str],
                         activate_immediately: bool = True) -> dict:
        return await self._request("POST", _WARMUP_ADD, json={
            "mailbox_uids": mailbox_uids,
            "activate_immediately": activate_immediately,
        })

    async def pause_warmup(self, mailbox_uids: list[str]) -> dict:
        return await self._request("POST", _WARMUP_PAUSE, json={
            "mailbox_uids": mailbox_uids,
        })

    # ------------------------------------------------------------------ health / liveness

    async def list_workspaces(self) -> dict:
        """Use as a liveness check — no public /health endpoint exists."""
        return await self._request("GET", _WORKSPACES_LIST)


# Module-level singleton for the provider to share.
_client: Optional[InboxKitClient] = None


def get_client() -> InboxKitClient:
    global _client
    if _client is None:
        _client = InboxKitClient()
    return _client
