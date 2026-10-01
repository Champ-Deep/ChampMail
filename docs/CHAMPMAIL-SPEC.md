# ChampMail — full system specification (as built)

Where ChampMail stands after the system-design alignment + InboxLint integration. This is the
"as-built" spec: every subsystem, the send pipeline with all gates, the data model, the
reputation contract, and current status per phase.

---

## 1. What ChampMail is

A **standalone, multi-tenant, cPanel-class email engine** — in-house SMTP + IMAP, owning the full
sending lifecycle (hosting, rotation, warmup, reputation, suppression, monitoring) instead of renting
an ESP (SendGrid/Postmark). Two send models: **BYOD** (client's own domain) and a **managed
pre-warmed pool**.

**Why it exists (the Vision moats):**
- **Moat 1 — owned reseller data / identity spine.** Prospects carry `person_id`/`account_id`, so they
  join the rest of the Champ suite (ChampGraph/Oracle), not email-keyed islands.
- **Moat 2 — deliverability.** The asset is the inbox reputation of owned sending domains/IPs. Every
  gate below exists to protect it. **InboxLint is the pre-send guard on this moat.**

---

## 2. Architecture — two planes

```
┌──────── CONTROL PLANE (DigitalOcean) — FastAPI + Celery/Redis + Postgres ────────┐
│  identity spine · suppression (person+global) · ramp-governor (per-IP)           │
│  event bus (champ.email.v1 / Redis) · provisioning API · Cloudflare DNS automation│
│  ┌─ SEND PIPELINE (Celery task `send_email_task`) ──────────────────────────┐    │
│  │ suppression gate → tracking/unsub inject → INBOXLINT gate → mail_engine   │    │
│  └──────────────────────────────────────────────────────────────────────────┘    │
└───────────┬──────────────────────────────────────────────┬──────────────────────┘
            │ mail_engine_client (HTTP)                      │ DNS API / DMARC RUA
            ▼                                                ▼
┌──── DATA PLANE (Hetzner/OVH, :25 + clean PTR) — Go `mail-engine/` ────┐  ┌─ Cloudflare ─┐
│ builder.go  : RFC5322 build — QP body, RFC-2047 subj, CRLF-strip      │  │ Registrar    │
│ dkim.go     : rsa-sha256 relaxed/relaxed, 2048 floor, List-Unsub in h=│  │ Auth DNS API │
│ deliver.go  : submission relay / spool (4xx vs 5xx retry → dead-letter)│  │ DMARC reports│
│ (phase 4) go-smtp :25 inbound MX · go-imap mailbox store · MTA-STS/DANE│  └──────────────┘
└────────────────────────────────────────────────────────────────────────┘
```

**Boundaries:** Cloudflare touches **only DNS**. All SMTP/IMAP/IP-reputation lives on the MTA hosts.
Reputation keyed **per sending IP**. Free suffixes never appear in `From`/`DKIM d=`/body links.

---

## 3. The send pipeline (control plane — `tasks/sending.py`)

Order is load-bearing — each gate protects the next:

1. **Resolve prospect** (`prospect_service`) → email, name, `team_id`, `person_id`.
2. **Suppression gate** (`suppression_service.is_suppressed`) — blocks if the address OR person is
   suppressed for this team **or globally**. Hard stop.
3. **Domain selection / rotation** (`domain_rotation.select_domain`) — picks a warmed sending domain.
4. **Tracking injection** — open pixel, click-wrapped links (aligned `click.<domain>` CNAME),
   unsubscribe URL; builds the RFC-8058 `List-Unsubscribe` header.
5. **InboxLint gate** (`services/inboxlint.lint`) — spam-trigger + CAN-SPAM/GDPR + deliverability
   lint. `block` → **do not send** (returns `{status: blocked, reason: inboxlint, issues}`);
   `warn/pass` → proceed. **Fail-open** (a linter error never blocks a legit send).
6. **Dispatch** (`mail_engine_client.send_email`) → the Go MTA builds + DKIM-signs + relays.
7. **Status + event** — `update_send_status`; emit `EmailEventType.SENT` to the suite bus.

Batch path (`send_batch_task`) mirrors steps 3–6 per prospect.

---

## 4. Subsystems

### Control plane (Python — `backend/app/`)
| Service | Role |
|---|---|
| `inboxlint.py` | **pre-send compliance + deliverability linter** (stdlib, no dep). `pass/warn/block`. |
| `suppression_service.py` | do-not-contact gate. `team OR NULL` global + person-aware (`email OR person_id`) + canonicalization (+tag/gmail-dots). |
| `ramp_governor.py` | closed-loop warmup: ADVANCE/HOLD/THROTTLE/PAUSE on bounce/complaint/seed; THROTTLE steps `warmup_day` down; per-IP seam. |
| `identity_service.py` | person/account spine — joins prospects to the suite. |
| `events.py` | `champ.email.v1` event bus (Redis Streams). |
| `domain_rotation.py` / `domain_service.py` | sending-domain pool + verify-before-send. |
| `cloudflare_client.py` | DNS automation (DKIM/SPF/DMARC/MX/click CNAME). |
| `tracking_service.py` | pixel + click wrap + signed unsubscribe URLs. |
| `reply_ingest.py` / `reply_intent.py` | inbound reply handling (feeds ReplyIQ-style intent). |
| `dsn_parser.py` / `tasks/bounces.py` | bounce (DSN) parsing → suppression. |

### Data plane (Go — `mail-engine/internal/`)
| File | Role |
|---|---|
| `mailer/builder.go` | RFC-5322 build: **QP-encoded bodies**, **RFC-2047** subject/display-names, **CRLF-stripped** headers, multipart alternative. |
| `mailer/dkim.go` | self-contained rsa-sha256 DKIM, relaxed/relaxed, **2048-bit floor**, `List-Unsubscribe` in `h=`. |
| `mailer/deliver.go` | relay/spool with 4xx-vs-5xx retry/backoff → dead-letter. |
| `api/` `handlers/` | HTTP surface the control plane calls (`mail_engine_client`). |
| `db/` `config/` | Postgres + Redis + env config (2048 floor is a const). |
| _(phase 4)_ `smtpd/` `imapd/` | inbound MX (`go-smtp`, RCPT-550 no-backscatter) + IMAP store. |

---

## 5. Data model (key tables)

- **`suppressions`** — `team_id` (NULL = global), `email` (canonical), `person_id`, `email_sha256`,
  `reason`, `source`. Unique `(team_id, email)` + **partial unique `email WHERE team_id IS NULL`**.
- **`domains`** — `domain_name`, DKIM selector/keys, `daily_send_limit`, `warmup_day`,
  `warmup_enabled`, `bounce_rate`, `seed_placement`, **`sending_ip`**, verification flags.
- **`prospects`** — identity spine: `person_id`, `account_id`, `external_ids`.
- **`send_logs`**, **`campaigns`**, **`sequences`**, **`email_accounts`** — sending records + cadence.

Schema via Alembic (`alembic/versions/`, head = `010_suppression_perip`).

---

## 6. The reputation contract (why each gate exists)

The moat is inbox reputation; these four together = "never burn a domain/IP":

1. **InboxLint** — content is compliant + non-spammy *before* it's sent.
2. **Suppression** — never email an opted-out/bounced address or person (Gmail/Yahoo cap complaint
   rates; one complaint spike torches a domain).
3. **DKIM (2048 + List-Unsub in `h=`)** — auth passes and the one-click unsubscribe is *signed*
   (receivers ignore unsigned unsub).
4. **Ramp-governor (per-IP)** — volume rises only while bounce/complaint/seed stay healthy; backs off
   automatically when they slip.

---

## 7. Current status (per `plan.md` phases)

| Phase | Item | Status |
|---|---|---|
| 1 | QP / RFC-2047 / CRLF-strip / 2048 floor | ✅ done + tested (`go test ./internal/mailer`) |
| 2 | suppression `team OR NULL` + person-aware + migration 010 | ✅ done |
| 3 | ramp THROTTLE-decrement + per-IP seam | ✅ done |
| — | InboxLint pre-send gate | ✅ integrated (fail-open) |
| 0 | one real sending domain + Hetzner MTA host | ⏳ infra (needs :25 host) |
| 1-gate | mail-tester 10/10 / Gmail Show-original PASS | ⏳ run on the host |
| 4 | inbound MX + IMAP (go-smtp/go-imap) | 📋 specced (`SYSTEM-DESIGN-ALIGNMENT.md`) |
| 5 | pool + BYOD | 📋 specced |

---

## 8. How to run / test

```bash
# Go MTA unit tests (DKIM verify + QP/RFC-2047/injection/key-floor)
cd mail-engine && go test ./internal/mailer/

# Pure-logic self-checks (no DB)
cd backend && python3 app/services/ramp_governor.py        # ramp THROTTLE-decrement
python3 -c "import sys; sys.argv=['x']; exec(open('app/services/suppression_service.py').read())"  # canon (needs sqlalchemy)

# Full stack (compose)
docker-compose up        # control plane + Go mail-engine + postgres + redis
# then POST a send via the API; InboxLint blocks a spammy payload before dispatch.

# Phase-1 live gate (on the :25 host): send to mail-tester.com → must be 10/10,
# Gmail "Show original" SPF/DKIM/DMARC = PASS, List-Unsubscribe present + signed.
```

InboxLint smoke: a payload with `FREE!!! CLICK HERE 100% GUARANTEED` and no unsubscribe returns
`level=block` and is never dispatched.
