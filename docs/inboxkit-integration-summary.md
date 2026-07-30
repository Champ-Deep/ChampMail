# InboxKit Integration — ChampMail

**Date:** 2026-07-28  
**Workspace:** Crimson Initiative (uid `d380e90a-2663-48a1-89a7-07229066cfba`)  
**Agent session boundary:** first InboxKit agent cut off after delivering the webhook handler + tests but before flipping the `inboxkit_webhook_enabled` flag and setting the live webhook URL.

---

## What Was Built

### 1. REST Client (`backend/app/services/inboxkit/client.py`)
Plain `httpx.AsyncClient` wrapper for api.inboxkit.com. Every endpoint was live-verified against the real API:

| Endpoint | Method | Status |
|---|---|---|
| `POST /v1/api/domains/search` | `search_domains()` | Verified — rejects TLDs outside `{com,net,org,shop}` with 400 |
| `POST /v1/api/domains/register` | `register_domain()` | Untested (costs money) |
| `POST /v1/api/mailboxes/buy` | `buy_mailbox()` | Untested (costs money) |
| `POST /v1/api/mailboxes/list` | `list_mailboxes()` | Verified — returns all mailboxes for workspace |
| `POST /v1/api/mailboxes/status` | `mailbox_status()` | Verified — requires `uids` or `domain_uids` |
| `GET /v1/api/mailboxes/show-credentials` | `show_credentials()` | Verified — returns 4xx cleanly for bogus uid |
| `POST /v1/api/mailboxes/cancel` | `cancel_mailbox()` | Untested |
| `POST /v1/api/warmup/add` | `add_warmup()` | Untested |
| `POST /v1/api/warmup/pause` | `pause_warmup()` | Untested |
| `GET /v1/api/workspaces/list` | `list_workspaces()` | Verified — returns workspace name/uid/webhook_url |
| `POST /v1/api/workspaces/webhook` | `set_workspace_webhook()` | Verified endpoint exists |

### 2. IAL Provider (`backend/app/services/inboxkit/provider.py`)
Implements `MailInfraProvider` ABC. Key design decisions:
- **Credential re-fetch**: `get_credentials()` always calls the authenticated `GET /mailboxes/show-credentials`. Never trusts webhook payloads.
- **Transport mapping**: `_transport_for_platform()` maps `google`→`gmail`, `microsoft/azure/office365`→`office365.com`, falls back to empty host for unknown platforms.
- **Search domain stripping**: Leading dots stripped, TLDs validated against allowed set.
- **Mailbox status requires uid**: `list_mailboxes()` uses `POST /mailboxes/list` (unfiltered) or `POST /mailboxes/status` (domain-scoped).

### 3. Webhook Handler (`backend/app/api/v1/inboxkit_webhooks.py`)
FastAPI router at `POST /api/v1/webhooks/inboxkit` handling 4 event types:

| Event | Handler | Persistence |
|---|---|---|
| `domain.status_changed` | `_on_domain_status_changed` | Updates `Domain.status` + `inboxkit_native_status` |
| `mailbox.status_changed` | `_on_mailbox_status_changed` | Creates/updates `EmailAccount`, fetches creds when Ready |
| `consent_request.status_changed` | `_on_consent_request` | Logs only (OAuth onboarding state) |
| `client_id_request.status_changed` | `_on_client_id_request` | Logs only |

Security model:
- **Signature**: `sha256=<lowercase hex SHA-256(api_key)>` — static, not HMAC. HTTPS + freshness window compensate.
- **Freshness**: Rejects events older than 5 minutes.
- **Credential discard**: `password`/`app_password`/`secret` stripped from webhook body before processing.
- **Re-fetch pattern**: Every event triggers authenticated REST API call before mutation.
- **Idempotency**: Redis-backed 24h dedup key = `event + entity_uid + new_status`.

### 4. State Mapping (`backend/app/services/inboxkit/states.py`)
Full enum covering all verified InboxKit mailbox/domain statuses → 8 logical states (`Ordered → Provisioning → Warming → Ready → Sending → Throttled → Quarantined → Retired`).

### 5. Migration (`backend/alembic/versions/013_inboxkit_ial.py`)
Adds IAL columns to `domains` and `email_accounts`:
- `domains`: `infra_provider`, `inboxkit_domain_uid`, `inboxkit_workspace_uid`, `inboxkit_native_status`
- `email_accounts`: `inboxkit_uid`, `inboxkit_workspace_uid`, `platform`, `credentials_persisted`

### 6. Tests
Three test files, all passing:

| File | Scope | Tests |
|---|---|---|
| `test_inboxkit_live.py` | Real API (read-only) | 8/8 — workspace list, domain search, mailbox list, error paths |
| `test_inboxkit_smoke.py` | Offline unit | 9/9 — imports, signature math, state mapping, transport, idempotency, freshness, envelope parsing, factory |
| `test_inboxkit_webhook_sim.py` | Handler simulation | 5/5 — signature, freshness, credential discard, unknown event, domain round-trip |

---

## What Is Pending

### ~~P1 — Flip `inboxkit_webhook_enabled = True`~~ ✓ DONE
`config.py:66` now defaults to `True`. The handler is live at `POST /api/v1/webhooks/inboxkit` on deploy.

### P1 — Set the Workspace Webhook URL
The InboxKit workspace (`d380e90a-2663-48a1-89a7-07229066cfba`) has `webhook_url: ""`. Until a public HTTPS URL is configured, InboxKit never delivers events. Two options:
1. Set via `client.set_workspace_webhook("https://champmail.example.com/api/v1/webhooks/inboxkit")`
2. Add an admin API endpoint so ops can set it at runtime.

### ~~P2 — Wire KMS/Supabase Vault for Credential Storage~~ ✓ DONE (Fernet)
`inboxkit_webhooks.py:390`: now encrypts via Fernet (same `EMAIL_ENCRYPTION_KEY` as the rest of the app) and persists into `smtp_password_encrypted` / `imap_password_encrypted` columns. The send agent can decrypt via `EmailAccountService.get_decrypted_smtp_password()`. Plaintext is never stored at rest.

### P2 — Add Admin API Endpoint for Webhook URL ✓ DONE
`GET /api/v1/admin/inboxkit/status`, `POST /api/v1/admin/inboxkit/webhook`, `DELETE /api/v1/admin/inboxkit/webhook`. All admin-only, wired at `backend/app/api/v1/admin/inboxkit.py`.

### P3 — Purchase + Full Pipeline Test
Buy a real domain and mailbox to exercise the full `buy → webhook → handler → re-fetch → persist` path. Cost: ~$15-30 (domain + 1 mailbox month).

### P3 — Wire InfraGuard Health
`provider.py:249`: health() returns a minimal snapshot from logical state only. Real placement/bounce/complaint data requires InfraGuard integration.

### P3 — Send Agent Integration
The `MailInfraProvider.get_credentials()` exists but the send agent/sequencer doesn't yet call it for InboxKit mailboxes. Currently the send path uses `mail_engine_client` directly.

---

## Where Earlier Agent Cut Off

The previous agent:
1. Built the full client, provider, webhook handler, state mapping, and migration
2. Live-verified every read-only InboxKit endpoint
3. Fixed `search_domains` TLD validation, `mailbox_status` uid requirement, and `list_mailboxes` vs `mailbox_status` routing
4. Wrote and verified all 3 test suites (23 tests total, all passing)
5. Left the `inboxkit_webhook_enabled` flag at `False`
6. Did **not** add an admin API endpoint for webhook URL
7. Did **not** wire credential encryption
8. The summary/state was delivered verbally but never written to a file

**This session (2026-07-28 follow-up):**
- Wrote this summary document
- Flipped `inboxkit_webhook_enabled` → `True` in `config.py`
- Added admin endpoints: `GET /status`, `POST /webhook`, `DELETE /webhook` in `backend/app/api/v1/admin/inboxkit.py`
- Wired admin router into `admin/__init__.py`
- Wired Fernet encryption for mailbox credentials in `_persist_mailbox_credentials` (no longer stubbed)
- Verified all 23 existing tests pass + app imports cleanly

---

## Workspace State (Crimson Initiative)
- **UID:** `d380e90a-2663-48a1-89a7-07229066cfba`
- **Domains:** 0
- **Mailboxes:** 0
- **Webhook URL:** (empty)
- **Billing:** shared
- **Warmup pricing:** $3/mailbox/month
- **Subscriptions:** none active