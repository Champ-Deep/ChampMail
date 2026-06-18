# ChampMail — In-House Outreach Service: Suite Extension Roadmap
**Date:** 2026-06-12
**Context:** ChampMail as the Champ suite's single in-house outbound mail spine —
no third-party ESP. Driven by champiq-sim-pack, copy by five-level-email-
personalizer, templates by ChampDocs / Image-to-HTML, signals by ChampGraph.

Research basis: provider docs + RFCs (Gmail/Yahoo/Microsoft bulk-sender rules,
RFC 8058/3464/8617), OSS references (Postal, Listmonk, Stalwart, rspamd).

---

## 0. Where ChampMail stands

Already has the hard parts: Go `mail-engine`, domain rotation, 8-step warmup,
open/click tracking, DKIM/SPF/DMARC verification, Celery/Redis pipeline, FalkorDB
graph, OpenRouter AI personalization. ~70% to production.

## 1. What this change set added (compliance gate — the #1/#2 priorities)

| Item | Status | Files |
|---|---|---|
| **RFC 8058 one-click List-Unsubscribe** (`List-Unsubscribe` + `List-Unsubscribe-Post: List-Unsubscribe=One-Click`) emitted on every send | ✅ done | `services/mail_engine_client.py`, `tasks/sending.py` |
| **Centralized, team-scoped suppression list** (do-not-contact) + send-path gate | ✅ done | `models/suppression.py`, `services/suppression_service.py`, `tasks/sending.py` |
| **Auto-suppress** on unsubscribe, hard bounce, complaint | ✅ done | `services/tracking_service.py`, `tasks/bounces.py` |

> ⚠️ One remaining must-do for the header to be honored: both List-Unsubscribe
> headers MUST be inside the DKIM `h=` signed set. Confirm/extend the Go
> `mail-engine` DKIM signer to include them (it now receives them in
> `data["headers"]`). Unsigned one-click headers are ignored by Gmail/Yahoo.

## 2. Hard numbers to encode as guardrails (from provider docs)

- Spam complaint rate: keep **< 0.1%**, **never reach 0.3%** (Gmail/Yahoo hard stop).
- Honor unsubscribe **within 2 days** (Yahoo) — build for instant (we suppress synchronously).
- Cold send ceiling: **50–100 emails / mailbox / day**.
- Hard bounce: pause ramp at **2%**, stop at **4%**.
- Seed inbox placement: advance warmup only if **> 85%**.
- Auth: SPF **+** DKIM **+** DMARC (min `p=none`, must pass + align). PTR/FCrDNS + TLS required.

## 3. Prioritized roadmap (compliance → deliverability → reply → intelligence)

**Phase 0 — Compliance gate (mostly done here)**
1. ✅ One-click List-Unsubscribe (finish: include headers in DKIM `h=`). — M
2. ✅ Suppression service + auto-suppress wiring. — M
3. ⬜ Consent/legal-basis records per contact (`legal_basis`, timestamp, source, LIA ref); CAN-SPAM physical address + honest headers. — S

**Phase 1 — Deliverability engineering**
4. ✅ **DSN/bounce parser (RFC 3464)** — `services/dsn_parser.py`: parses `message/delivery-status`, classifies `5.x` hard / `4.x` soft, with a non-standard fallback. Tested (`tests/test_outreach_core.py`). — M
5. ⬜ FBL/ARF ingestion (Yahoo CFL, Microsoft JMRP) → suppress + tenant alerting. — M
6. ⬜ Reputation ingestors: Google Postmaster Tools API + Microsoft SNDS → daily timeseries + dashboard. — M
7. ✅ **Ramp-governor** — `services/ramp_governor.py` (pure, tested) + `tasks/ramp.py` (Celery): closed-loop per-domain throttle tied to live bounce(2/4%)/complaint(0.1/0.3%)/seed(>85%) thresholds; advance/throttle/pause. — M
8. ⬜ MTA-STS + TLS-RPT publish; formalize cold-email subdomain isolation from corporate/transactional. — S/M
9. ⬜ Pre-send copy spam-linter (rspamd) surfaced in UI. — S

**Phase 2 — Reply handling & scale**
10. ✅ **IMAP reply ingestion + thread match-back** — `services/reply_ingest.py` (pure classify+match, tested) + `tasks/replies.py` (imaplib adapter): discriminates bounce vs reply vs OOO (`Return-Path:<>`, `Auto-Submitted`, subject prefixes), matches `In-Reply-To`/`References`, **prospect-level auto-pause** on human reply, free-text opt-out → suppression. — L
11. ⬜ Per-destination Redis token-bucket throttles + DKIM key-rotation automation; Postfix/Stalwart per-transport tuning. — M

**Phase 3 — Intelligence**
12. ⬜ LLM reply-intent classifier (interested/not/OOO/unsub/referral) → FalkorDB conversation graph; free-text opt-out auto-suppress. — M
13. ⬜ Signal-based AI personalization + deliverability-aware copy scoring + by-model A/B on **reply rate**. — L

## 4. Suite integration (how ChampMail fits the Champ stack)

```
ChampIQ Canvas (champiq-sim-pack) — orchestration (Sim DAG)
   │  blocks/champmail.ts · tools/champmail.ts (POST /api/champmail/send)
   ▼
ChampGraph briefing (KG: why-now, signals)  ──► personalization context
   ▼
five-level-email-personalizer (POST /v1/personalize) ──► best variant (reply-likelihood)
   ▼
ChampMail  ──► suppression gate ─► DKIM-signed send (List-Unsubscribe) ─► tracking
   ▲                                                      │
   └────────── reply/bounce/complaint ◄───────────────────┘  (→ suppression + KG episode)

Template sources: ChampDocs marketing-HTML renderer · Image-to-HTML newsletters
Link tracking/attribution: ChampUTM
```

The integration is wired on the sim-pack side in `email/champmail-client.ts`
(real ChampMail REST dispatch) + `email/personalizer-client.ts` (5-level copy),
consumed by `email/send-service.ts::EmailService.sendLive()`. ChampMail's REST
API (`POST /api/v1/send`, `/api/v1/campaigns`, suppression) is the contract.

## 5. OSS references to mine (don't rebuild)
Postal (IP pools, webhook event schema, suppression), Listmonk (bounce pipeline,
throttle config), Stalwart (MTA/IMAP, native MTA-STS/TLS-RPT/ARC), rspamd
(`bounce.lua`, content scoring). See the cited research report for URLs.

## 6. Suite-integration track (orthogonal to deliverability, run in parallel)

Deliverability makes ChampMail a *trustworthy sender*; suite-integration makes it
the suite's *outbound nervous system*. The two decisions to lock first:

1. **Identity spine.** Today both ChampMail's Postgres `Prospect` and its FalkorDB
   node key on `email` — no shared id, breaks on job-changes/dedup. Add
   `person_id` + `account_id` + `external_ids JSONB` (`{lake_id, clerk_id,
   linkedin_urn, champutm_visitor_id, email_sha256}`) to `prospects` and the graph
   nodes. Mint ids in ChampGraph/Graphiti (it already does temporal entity
   resolution); every app references them. **Smallest change, largest unlock.** — S
2. **Unified event bus + schema.** The only event surface today is the n8n-shaped
   `email_webhooks.py`. Introduce a versioned event contract
   (`email.sent|delivered|opened|clicked|bounced|complained|replied|unsubscribed`,
   each `{person_id, account_id, campaign_id, send_log_id, ts}`) on Redis Streams
   (already deployed) + signed HTTP webhooks. Gates every integration below. — M

Per-repo integrations (data-in / events-out), ranked by suite leverage:
- **LakeB2B/LakeStream/LakeCurrent** → prospect enrichment in; ChampMail bounce/
  complaint/reply outcomes back as a data-quality feedback loop. — S
- **ChampUTM** → become the link-shorten/redirect authority (replace ChampMail's
  duplicate redirect); its **file-share read-receipts (dwell/page-depth) are a
  stronger engagement signal than opens**. — S/M
- **ChampGraph/Graphiti** → personalization briefings in; ChampMail engagement
  episodes out. Demote local FalkorDB to a read projection (there's a
  `TODO: integrate Graphiti` in `db/falkordb.py`). — M
- **ChampDocs/Image-to-HTML** → branded templates + **pre-send HTML/attachment
  validation gate** in the send path next to suppression. — S
- **ChampVoice/champvideo** → multichannel cadence: `clicked-no-reply → voice`,
  `file_viewed deeply → video`; one consent gate across channels. — L
- **ChampHarbinger** → `signal.detected` → auto-enroll into a signal-specific
  sequence (highest-converting motion). — S
- **champiq-sim-pack / ChampIQ** → a **campaign-as-workflow API** (declare/enroll/
  state, idempotent) so Sim drives ChampMail as a DAG node (REST send already
  wired). — M
- **five-level-personalizer** → copy in; ChampMail reports realized reply rates to
  close the A/B loop. — M

**Cross-channel consent (highest-value shared fix):** promote ChampMail's
`Suppression` (email+team-scoped) to a suite **Consent service** keyed by
`person_id` with per-channel grants (email/phone/linkedin/sms), each with
`legal_basis`/`source`/`timestamp` — a "stop calling me" reply then suppresses
*voice*, not just email. Regulatory necessity (CAN-SPAM/DPDP/TCPA differ per
channel).

**Shared services to extract:** auth/identity (standardize on Clerk/OIDC; ChampUTM
already uses Clerk), knowledge graph (= ChampGraph), event bus (new, Redis
Streams), LLM gateway (= OpenRouter, already de-facto in ChampMail's config),
analytics warehouse keyed by `person_id`.
