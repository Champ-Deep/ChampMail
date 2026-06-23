# ChampMail — Fit in the Champ Suite

ChampMail is the suite's **send-engine**: the one component that actually signs (DKIM)
and dispatches a real message. Everything upstream (ScraperChamp → Harbinger → ChampGraph →
sim-pack → Champ_IQ / ChampOracle) decides *who / what / when*; ChampMail does the *send*
and emits the *what-happened* events. Below: each seam, grounded in code, marked
**WIRED** (code path exists) vs **DESIGNED-NOT-WIRED** (contract/spec exists, no live consumer).

## 1. Where ChampMail sits — the send target of the DAG  — WIRED
- sim-pack exposes ChampMail as a Sim tool + Canvas block:
  - `champiq-sim-pack/tools/champmail.ts:19` `champMailSendTool` → `POST /api/champmail/send`;
    `:48` `champMailPauseTool` → `/api/champmail/enrollments/pause` (pause on reply).
  - `champiq-sim-pack/blocks/champmail.ts:8` `ChampMailBlock` (Canvas node, tools `champmail_send`/`champmail_pause_sequence`).
- The DAG's **email** stage runs through `email/send-service.ts`:
  - `EmailService.sendLive()` (`send-service.ts:117`) gates → personalizes → dispatches via
    `this.live.champmail.send(...)` (`:139`).
  - `email/champmail-client.ts:82` `ChampMailClient.send()` → `POST {baseUrl}/api/v1/send` with
    `list_unsubscribe`, `domain_id`, tracking flags → ChampMail's Go mail-engine (DKIM sign + deliver).
- The 8-stage flow is demonstrated in `champiq-sim-pack/demo.mjs` `runSequence` (~`:138`):
  `enrich → personalize → send → wait → reply → voice/pause`.
**Verdict:** Yes — ChampMail is the engine the DAG dispatches real sends to. The base product
"never sent a real message"; the Go mail-engine + `/api/v1/send` is the load-bearing add.

## 2. Identity seam — person_id spine  — PARTIALLY WIRED (deterministic, not byte-identical across producers)
- ChampMail mints the spine: `backend/app/services/identity_service.py`
  - `derive_person_id()` (`:56`) = `uuid5(_PERSON_NS, "<key>:<val>")` over priority
    `linkedin_urn > lake_id > clerk_id > email` (`_PERSON_KEY_ORDER`, `:25`).
  - `derive_account_id()` (`:80`) = `uuid5(_ACCOUNT_NS, "domain:<dom>")`.
  - Docstring: in prod ids are **minted/resolved by ChampGraph/Graphiti**; local UUIDv5 is the
    fallback when ChampGraph isn't wired.
- ScraperChamp Facts ride a `person_id` too: `champscrape/champscrape/enrichment/permutator.py:89`
  writes `entities={"person_id": make_person_id(...)}`; `enrichment/base.py:20` `make_person_id`
  is a **`name:company` slug string** ("Stable-ish person key for the ChampMail person_id spine
  (best-effort)") — NOT a UUIDv5.
- **Seam reality:** both sides intend one spine, and ChampMail's `email.sent` envelope carries
  `person_id`/`account_id` so events *can* join the person graph. But the two producers compute
  different shapes (UUIDv5 vs slug). They only truly converge if **ChampGraph/Graphiti** is the
  authoritative resolver (as both docstrings say) — that resolver is **DESIGNED, not wired here**.

## 3. Event seam — `champ.email.v1` on Redis Streams  — PRODUCER WIRED, CONSUMERS NOT
- Producer: `backend/app/services/events.py` — `SCHEMA="champ.email.v1"`, `STREAM="champ:events:email"`,
  `build_event()` (pure envelope keyed by `person_id/account_id/campaign_id/team_id`), `emit()` does
  best-effort `XADD`.
- Emit sites (all inside ChampMail): `tasks/sending.py:82` `email.sent` (carries `person_id`,
  `account_id` from the prospect record); `tasks/bounces.py:42` `email.bounced`/`complained`.
  Webhook ingress (`api/v1/webhooks.py:137+`) handles OPENED/CLICKED/REPLIED/BOUNCED/UNSUBSCRIBED
  internally (auto-pause + suppression) but those are ChampMail-internal reactions.
- **Consumers of the stream:** none outside ChampMail. Grep across sim-pack / Champ_IQ /
  Harbinger finds `champ:events:email` only in **docs/HTML/manifests**, never a live `XREADGROUP`.
  - sim-pack's `wait`/`reply` branch in `demo.mjs` is driven by a **local `gotReply` flag**, NOT by
    reading `email.opened`/`email.replied` off the bus. No voice-escalation / pause is bus-triggered.
  - ChampGraph does **not** ingest engagement edges from this stream (no consumer code present).
**Verdict:** the outbound nervous system is built and emitting; **nobody is plugged into it yet.**
This is the single biggest open seam (gap).

## 4. Suppression seam — team-scoped do-not-contact  — TWO GATES, AUTHORITATIVE ONE INSIDE CHAMPMAIL
- ChampMail (authoritative, persistent, team-scoped):
  `backend/app/services/suppression_service.py` — `is_suppressed()` (`:27`) checked in the send
  path at `tasks/sending.py:48` **before dispatch**; `add()` called from `tasks/replies.py:108`,
  `tasks/bounces.py:33`, `tracking_service.py:732` ("opt-out anywhere suppresses everywhere for that team").
- sim-pack (local mirror, NOT a query to ChampMail): `email/send-service.ts:84` `EmailService.gate()`
  checks an in-memory `suppressed: Set<string>` + per-prospect `consent.email` + warmup cap.
  The Canvas block also declares a compliance `capability: 'consent.email'` (`blocks/champmail.ts`),
  and `demo.mjs` guardrail blocks adding a champmail node without an email-consent capability (`:100`).
**Verdict:** the real, team-scoped suppression gate lives **inside ChampMail** and always runs.
sim-pack pre-gates on its own local set/consent but does **not** call ChampMail's suppression API
before the email stage — so sim-pack's pre-flight is advisory; ChampMail is the backstop.

## 5. ChampOracle → ChampMail path  — REACHES Champ_IQ, NOT ChampMail DIRECTLY
- `ChampOracle-main/backend/app/services/champoracle_bridge.py`:
  `export_high_performing_agents()` (`:169`) → `create_icp_from_simulation()` (`:353`) →
  `sync_lookalike_centroid()`; POSTs to **Champ_IQ**: `{champiq_base_url}/api/v1/icp` (`:582`) and
  `/api/v1/lookalike/centroid` (`:601`), `champiq_base_url` default `http://localhost:5002`.
- So the winning ICP/centroid lands in **Champ_IQ**, not ChampMail. Champ_IQ in turn carries
  ChampMail as a Canvas node (`Champ_IQ-main/champiq-canvas/manifests/champmail.manifest.json`,
  action `send_single_email`) + a settings/credentials surface (`EmailEngineSection.tsx`), but that
  manifest is a **declarative capability descriptor**, not a live HTTP binding, and no Champ_IQ
  runtime code calls `/api/v1/send` (only `.md` specs reference it).
**Verdict:** ChampOracle pre-flights → exports to Champ_IQ (**WIRED**). Champ_IQ → sim-pack → ChampMail
real send is **DESIGNED** (manifest + ChampMail_Inline_Spec.md) but the live ChampOracle→…→ChampMail
chain is not joined end-to-end in code.

## 6. The closed loop — summary
```
ScraperChamp ──Facts(person_id slug)──► ChampGraph ──► sim-pack DAG
ChampOracle ──ICP/centroid──► Champ_IQ                    │ email stage
                                  │ (Canvas node, spec)   ▼
                                  └──────────────► ChampMail  (gate→DKIM-sign→send)
                                                      │
                                            champ.email.v1 (Redis Streams)
                                                      │  (emitting, no external consumer)
                                                      ✗── back to sim-pack wait/voice / ChampGraph edges
```
- **WIRED:** sim-pack DAG → `ChampMailClient` → `/api/v1/send` (real DKIM send);
  ChampMail send-path suppression gate + warmup; ChampMail emits `champ.email.v1`
  (sent/bounced) keyed by identity ids; ChampMail-internal reply→auto-pause + bounce→suppress;
  ChampOracle → Champ_IQ ICP/centroid export.
- **DESIGNED-NOT-WIRED (the gaps):**
  1. No consumer of `champ:events:email` — sim-pack `wait`/`writeback` doesn't read
     opened/replied to branch to voice/pause; ChampGraph ingests no engagement edges.
  2. Identity spine: ScraperChamp emits a slug `person_id`, ChampMail a UUIDv5 — they only
     reconcile through a ChampGraph/Graphiti resolver that isn't wired in these repos.
  3. Champ_IQ → ChampMail send is a Canvas manifest + spec, not a live call; ChampOracle's
     export stops at Champ_IQ.

**One line:** ChampMail is the suite's real (and only) send-engine — fully wired *inbound*
(sim-pack dispatches to it) and *self-contained* (it gates, signs, sends, and reacts to its own
bounces/replies), but its *outbound* event bus and the cross-app identity reconciliation are
emitted-but-unconsumed — the loop is open on the way back.
