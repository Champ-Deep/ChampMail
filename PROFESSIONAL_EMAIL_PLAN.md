# Professional Email Delivery — Implementation Plan

## Goal
Make ChampMail emails indistinguishable from hand-typed emails. Fully compliant with Gmail, Yahoo, and Microsoft Outlook bulk sender requirements (2025-2026).

---

## Compliance Matrix

| Requirement | Gmail | Yahoo | Microsoft Outlook | Our Implementation |
|---|---|---|---|---|
| SPF pass | Required | Required | Required | Already handled via DNS setup wizard |
| DKIM pass (1024-bit+) | Required | Required | Required | Already handled via mail-engine DKIM |
| DMARC (p=none minimum) | Required | Required | Required | Already handled via DNS setup wizard |
| `List-Unsubscribe` header | Required (RFC 8058) | Required (RFC 8058) | Required ("functional") | **Phase 1** — mailto + HTTPS dual header |
| `List-Unsubscribe-Post` header | Required (one-click) | Required (one-click) | Recommended | **Phase 1** — `List-Unsubscribe=One-Click` |
| `Message-ID` header (domain-aligned) | Expected | Expected | Expected | **Phase 1** — `<uuid@sender_domain>` |
| `Date` header (RFC 2822) | Expected | Expected | Expected | **Phase 1** — proper timestamp |
| Valid From/Reply-To | Required | Required | Required | **Phase 4** — configurable from_email |
| Honor unsubscribe within 48h | Required | Required | Required | **Phase 2** — IMAP scan every 5 min |
| Spam rate < 0.3% | Hard enforced | Hard enforced | Enforced | **Phase 5** — cadenced sending |
| Rejection code if non-compliant | Temp/perm reject | Reject | `550 5.7.515` | All phases prevent this |

---

## Phase 1 — Professional Email Headers (Anti-Spam)

**Principle:** Single Responsibility — header construction is a dedicated concern, separate from SMTP transport.

**File:** `backend/app/services/email_service.py`

### Changes:
1. Add `Message-ID` header: `<{uuid}@{sender_domain}>` — domain extracted from from_email
2. Add `Date` header: RFC 2822 format via `email.utils.formatdate()`
3. Add `List-Unsubscribe` header (dual method):
   - `mailto:{from_email}?subject=unsubscribe-{tracking_id}` — uses user's own IMAP-monitored inbox
   - `https://{app_url}/api/v1/track/unsubscribe/{tracking_id}?sig={sig}` — existing tracking service URL
4. Add `List-Unsubscribe-Post: List-Unsubscribe=One-Click` — RFC 8058 one-click POST
5. Ensure `MIME-Version: 1.0` is always present
6. Always include plain-text part alongside HTML (multipart/alternative)

### Method Signature Change:
```python
async def send_email(
    self, ...,
    campaign_id: str = None,
    prospect_id: str = None,
)
```
When campaign_id + prospect_id are provided, tracking URLs are generated and headers are injected.

---

## Phase 2 — IMAP Unsubscribe Detection

**Principle:** Open/Closed — extend existing reply detection without modifying it. New task alongside, not merged into.

**Files:**
- `backend/app/tasks/sequences.py` — new `process_imap_unsubscribes` task
- `backend/app/celery_app.py` — add to beat schedule

### Flow:
1. IMAP SEARCH for subjects matching `unsubscribe-*`
2. Extract `tracking_id` from subject
3. Call existing `tracking_service.handle_unsubscribe(tracking_id)` — already marks prospect as unsubscribed
4. Delete/move processed unsubscribe emails from inbox
5. Runs every 5 minutes via Celery Beat

### Why IMAP:
- No public URL needed (app may not be internet-facing)
- Gmail/Yahoo/Outlook all support `mailto:` List-Unsubscribe
- User's IMAP inbox is already monitored for reply detection
- Unsubscribes honored within 5 minutes (well within 48h requirement)

---

## Phase 3 — Wire Tracking IDs into Send Flow

**Principle:** Dependency Inversion — email_service depends on tracking abstraction, not concrete tracking implementation.

**Files:**
- `backend/app/tasks/sending.py` — pass campaign_id/prospect_id to email_service
- `backend/app/services/email_service.py` — generate tracking URLs when campaign context is present

### Flow:
1. `send_email()` receives `campaign_id` + `prospect_id`
2. Calls `tracking_service.generate_tracking_urls()` to get tracking_id + unsubscribe_url
3. Injects `List-Unsubscribe` and `List-Unsubscribe-Post` headers
4. Injects tracking pixel and click wrappers into HTML body (existing logic)

---

## Phase 4 — Fix From Address Chain

**Principle:** Interface Segregation — EmailAccount model gets a dedicated `from_email` field instead of overloading `email` field.

**Files:**
- `backend/app/models/email_account.py` — add `from_email` column
- `backend/app/schemas/email_account.py` — add to create/update schemas
- `backend/app/services/email_service.py` — use from_email when set
- `frontend/src/pages/SettingsPage.tsx` — add from_email input, remove dead Email Settings tab
- New Alembic migration

### From Address Resolution Order (after fix):
1. Per-call override `from_email` parameter (highest priority)
2. `EmailAccount.from_email` (user-configured display address)
3. `EmailAccount.email` (account's primary email)
4. **Error** — never fall back to `noreply@localhost` or `ChampMail`

### Frontend Changes:
- Email Accounts tab: add "Send From Email" field
- Remove non-functional "Email Settings" tab (dead stub with no handlers)
- Remove redundant "SMTP / IMAP" tab (consolidated into Email Accounts)

---

## Phase 5 — Cadenced Bulk Sending

**Principle:** Single Responsibility — scheduling is separate from sending. Liskov Substitution — cadenced send replaces batch send transparently.

**Files:**
- `backend/app/models/campaign.py` — add `cadence_seconds` column (default 3600)
- `backend/app/tasks/campaign_tasks.py` — fix `schedule_campaign_sends_task` to actually enqueue sends
- `backend/app/tasks/sending.py` — individual sends with ETAs
- `backend/app/tasks/sequences.py` — respect cadence in `execute_pending_steps`
- New Alembic migration

### How It Works:
1. `schedule_campaign_sends_task` computes optimal send times (existing SendScheduler — well-built)
2. **NEW:** After computing schedule, enqueues `send_email_task.apply_async(eta=send_at)` per email
3. `Campaign.cadence_seconds` (default 3600 = 1 hour) sets minimum gap between sends
4. `Campaign.daily_limit` is enforced: count sent today, skip if at limit
5. Velocity limits: max 30/hour, min 30-second gap (existing SendScheduler constants)

### Sending Pattern (what mail servers see):
```
10:00 AM  →  john@acmecorp.com       (Tue, recipient's timezone)
11:00 AM  →  sarah@bigtech.io
12:02 PM  →  mike@startup.co
 1:00 PM  →  lisa@enterprise.com
...next optimal window...
10:15 AM  →  david@fintech.com       (Wed)
```

### Sequence Fix:
- `execute_pending_steps` currently fires all steps in a tight loop
- Fix: process only steps whose `next_step_at <= now()`, one per prospect per run
- Celery Beat already runs this every 5 minutes — natural cadence

---

## Phase 6 — CLI-to-Database Sync

**Principle:** Single Source of Truth — one config path, not two competing systems.

**Files:**
- `backend/cli/commands/chat.py` — SAVE_SMTP creates EmailAccount in database via API
- `backend/cli/commands/setup.py` — setup wizard syncs to database

### Current Problem:
- CLI saves to `~/.champmail/config.json` only
- Backend reads from database only
- User configures SMTP via CLI, sends campaign, gets "No email settings configured"

### Fix:
- CLI `SAVE_SMTP` action calls EmailAccount API to create/update account in database
- Config.json becomes a local cache, not the source of truth
- On CLI startup, check if config.json has credentials not in database → prompt to sync

---

## Files Touched (Summary)

| File | Phase | Change |
|---|---|---|
| `backend/app/services/email_service.py` | 1, 3, 4 | Headers, tracking, from-chain |
| `backend/app/models/email_account.py` | 4 | Add `from_email` column |
| `backend/app/schemas/email_account.py` | 4 | Add to schemas |
| `backend/app/tasks/sending.py` | 3, 5 | Wire tracking, cadenced sends |
| `backend/app/tasks/sequences.py` | 2, 5 | IMAP unsubscribe, fix cadence |
| `backend/app/tasks/campaign_tasks.py` | 5 | Enqueue sends with ETAs |
| `backend/app/models/campaign.py` | 5 | Add `cadence_seconds` column |
| `backend/app/celery_app.py` | 2 | Add unsubscribe check to beat |
| `backend/cli/commands/chat.py` | 6 | Sync to database |
| `backend/cli/commands/setup.py` | 6 | Sync to database |
| `frontend/src/pages/SettingsPage.tsx` | 4 | from_email field, remove dead tabs |
| New Alembic migration | 4, 5 | `from_email` + `cadence_seconds` columns |

---

## What the Recipient Sees (End Result)

### Inbox:
```
From:    Hemang Shah <hemang@yourcompany.com>
To:      John Smith <john@acmecorp.com>
Subject: Quick question about Acme's Q3 hiring plans
```

### Gmail/Outlook UI:
```
Hemang Shah <hemang@yourcompany.com>     [Unsubscribe]
```

### Raw Headers (what servers verify):
```
Message-ID: <a3f7b2c1-9d4e-4f8a-b123-456789abcdef@yourcompany.com>
Date: Wed, 16 Apr 2026 10:23:45 +0000
From: Hemang Shah <hemang@yourcompany.com>
Reply-To: hemang@yourcompany.com
List-Unsubscribe: <mailto:hemang@yourcompany.com?subject=unsubscribe-trk_abc123>, <https://app.yourcompany.com/api/v1/track/unsubscribe/trk_abc123?sig=xyz>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
MIME-Version: 1.0
Content-Type: multipart/alternative
```

### What is NEVER visible:
- `test@accountsonline.biz`
- `noreply@localhost`
- `ChampMail` branding
- `smtp.ethereal.email`
- Any tool/platform branding

---

## References
- [Microsoft: Outlook's New Requirements for High-Volume Senders](https://techcommunity.microsoft.com/blog/microsoftdefenderforoffice365blog/strengthening-email-ecosystem-outlook%E2%80%99s-new-requirements-for-high%E2%80%90volume-senders/4399730)
- [Gmail and Yahoo Bulk Sender Requirements (Updated 2026)](https://emailwarmup.com/blog/gmail-and-yahoo-bulk-sender-requirements/)
- [2026 Bulk Email Sender Requirements Checklist](https://redsift.com/guides/bulk-email-sender-requirements)
- [RFC 8058 — One-Click Unsubscribe](https://www.captaindns.com/en/blog/gmail-one-click-unsubscribe-rfc8058)
