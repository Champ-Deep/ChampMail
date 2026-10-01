# ChampMail: OAuth Mailbox Sign-In, InboxKit Procurement, and the JEV Reply Agent

Status: research and design. Nothing in this document is built on `v2-consolidation`.
Date: 2026-10-01
Base: `v2-consolidation` (see `CONSOLIDATION-REPORT.md` for how that base was chosen)

---

## 0. Read this first: two findings that change the plan

### 0.1 JEV is not a mailbox-understanding agent

Deep's brief for step (c) was "an agent that uses JEV to understand and segment
the user's mailbox." JEV, as it actually exists, does not do that.

JEV (from `Projects/Jev Camoufox Agent/`, notes dated 2026-09-27) is a **browser
automation agent**. Its actual design:

| Property | Value |
|---|---|
| What it does | Indexes a web page's controls, then picks an *operation* and a *target* from that index |
| Browser | Camoufox (patched Firefox) over Playwright, fingerprint-spoofed |
| Decision endpoint | `openrouter.ai/api/alpha/decisions`, model `typesafe/jev-1.13` |
| Field/text model | `stealth/space-bunny-alpha` via OpenRouter |
| Upstream | fork of `browser-use/jev-ultrafast` (MIT) |
| Safety property | The model never emits a selector or executable code. Node ids are minted by our own DOM reader and re-resolved plus hit-tested immediately before input |
| Verified state | 24/24 offline transport checks, 3 live canaries, 1 full text-entry flow |
| Self-declared limits | Single-task runs, not a benchmark. Slower than Chrome. Shadow DOM, iframes, canvas, file uploads and nested scroll containers are all outside the reader. "Not yet wired to anything. This is a library and a runner, not an automation." |

So JEV operates a **web UI**. It does not read a mailbox, does not classify
threads, and does not segment anything. Routing mailbox content through it
would mean: render the mailbox as HTML, hand it to a browser agent, and have
the agent click through a UI to read what a JSON API could return directly.
That is strictly worse on cost, latency, determinism and correctness.

**Recommendation.** Split the requirement in two and use the right tool for each:

| Need | Right tool |
|---|---|
| Read and segment mailbox content | Gmail API / Microsoft Graph over OAuth, straight into an LLM pipeline |
| Drive a consent screen or settings page that resists the API | JEV, as a last-resort browser fallback |

JEV stays in scope, but as a narrow fallback, not as the segmentation engine.
This is the single most important correction in this document, and it needs
Deep's confirmation before Phase 3 starts (see section 10).

### 0.2 OAuth for "your own mailbox" triggers restricted scopes

Google classifies `https://mail.google.com/` and `gmail.modify` as **restricted**
scopes. Restricted scopes require Google OAuth verification, a public app, a
privacy policy, and in most cases a security assessment. Sensitive scopes
(`gmail.send`, `gmail.metadata`) need verification too, though it is lighter.

This has a schedule implication: OAuth verification is not a sprint task, it is
a multi-week process that gates a public launch. See section 5.3 for the
mitigation, which is also just better security.

---

## 1. What already exists in the repo

Everything below was read in `v2-consolidation`. This plan builds on the real
code, not a greenfield sketch.

### 1.1 Reusable

| Need | Existing code | Note |
|---|---|---|
| Auth | `app/core/security.py` | JWT HS256, `create_access_token`, `decode_token`, `require_auth`, `TokenData(user_id, email, role, team_id)` |
| Credential encryption | `app/services/email_account_service.py` | Fernet, key from `EMAIL_ENCRYPTION_KEY`. Already encrypts SMTP and IMAP passwords at rest |
| Mailbox model | `app/models/email_account.py` | `smtp_*`, `imap_*`, `from_email`, `from_name`, `is_default`, verification flags |
| Inbound mail | `app/services/email_provider.py` | `IMAPReplyDetector.check_new_messages()`, `IncomingMessage` |
| Reply understanding | `app/services/reply_ingest.py` | Bounce / OOO / reply discrimination, `In-Reply-To` thread matching, free-text opt-out detection. Pure cores, unit-tested offline |
| Reply intent | `app/services/reply_intent.py` | `classify_intent()` |
| LLM plumbing | `app/services/ai/openrouter_service.py` | `OpenRouterClient.chat_completion`, plus `SegmentationService` |
| Segmentation | same file, `SegmentationService.segment_prospects()` | Already produces 3-8 segments with criteria, pain points, messaging angle, priority. **This is most of step (c) already** |
| Conversation context | `app/services/ai/c1_context.py` | `C1ContextBuilder` |
| Send gate | `app/tasks/sending.py` | Two transports, suppression then `send_gate`, VERP |
| Suppression | `app/services/suppression_service.py` | Team-scoped, person-aware, address canonicalization |
| API keys | `app/models/send_log.py` | `APIKey` with `key_hash` |
| Settings | `app/core/config.py` | Pydantic `BaseSettings` |

### 1.2 Gaps

| Gap | Consequence |
|---|---|
| No delegated OAuth. `auth.py` uses `OAuth2PasswordRequestForm`, which is the OAuth2 *password* grant form for first-party sign-in, not a Google/Microsoft authorization-code flow | Phase 2 is genuinely new |
| No provider-token table. `EmailAccount` holds static SMTP/IMAP creds | OAuth tokens need their own schema and lifecycle |
| No Sent-folder reader | Phase 3 voice extraction has no data source |
| No thread store | Phase 4 drafts cannot attach to a thread |
| No mock/synthetic mailbox | Phase 5 has no test surface |
| No LLM eval harness | Voice quality cannot be measured, only eyeballed |

---

## 2. Data model

Three new tables. Each is independently shippable and each has a rollback.

### 2.1 `oauth_connections`

One row per user per provider per account.

```
id                 uuid pk
user_id            uuid fk users        on delete cascade
provider           text                 'google' | 'microsoft'
provider_account_id text                stable id from the provider
email              text                 the mailbox address
scopes             text[]               granted, as returned
access_token_enc   text                 Fernet
refresh_token_enc  text                 Fernet, the crown jewel
token_expires_at   timestamptz
refresh_after      timestamptz          proactive refresh threshold
revoked_at         timestamptz          set on disconnect / provider revoke
last_validated_at  timestamptz
created_at/updated_at
unique (provider, provider_account_id)
```

`access_token_enc` and `refresh_token_enc` reuse the **existing** Fernet helper
in `email_account_service.py`. Do not write a second crypto path.

### 2.2 `mailbox_threads`

```
id                  uuid pk
connection_id       uuid fk oauth_connections
provider_thread_id  text
participants        text[]
subject             text
snippet             text
last_message_at     timestamptz
is_read             bool
labels              text[]
is_draft_source     bool      true if it seeded a voice profile
unique (connection_id, provider_thread_id)
```

### 2.3 `voice_profiles` and `reply_drafts`

```
voice_profiles
  id            uuid pk
  user_id       uuid fk users
  version       int
  traits        jsonb   sign-off, greeting, formality, sentence length,
                       emoji use, punctuation habits, hedges, closings
  exemplars     jsonb   up to 10 redacted (subject, body) pairs
  sample_size   int     how many sent messages backed this
  confidence    float   sample_size below a floor means "low confidence"
  created_at

reply_drafts
  id                uuid pk
  thread_id         uuid fk mailbox_threads
  variant_a         text   draft option A
  variant_b         text   draft option B
  rationale         text   why these two
  decision          text   null | 'a' | 'b' | 'both' | 'reject'
  decided_at        timestamptz
  created_at
```

`variant_a` / `variant_b` map directly onto the accept/deny UX in (e).

---

## 3. Phase A: OAuth mailbox sign-in

### 3.1 Flow

Standard authorization code flow, server-side.

```
1. GET  /api/v1/oauth/{provider}/start
      -> 307 to provider consent, with:
           state         = signed, short-lived, single use (Redis, 10 min TTL)
           redirect_uri  = {PUBLIC_BASE_URL}/api/v1/oauth/{provider}/callback
           scopes        = minimal set for this provider (section 3.2)
           access_type   = offline          (google: get a refresh token)
           prompt        = consent          (google: force refresh token first time)

2. User consents at the provider.

3. GET  /api/v1/oauth/{provider}/callback?code=&state=
      - verify state, consume it (single use)
      - exchange code for tokens at the provider's token endpoint
      - fetch the user's profile/address
      - Fernet-encrypt both tokens, insert oauth_connections
      - 307 to the frontend, no tokens in the URL, ever

4. Background/refresh: when now > refresh_after, refresh and re-encrypt.
```

### 3.2 Scopes, minimal per provider

**Google.** Verified against Google's published scope table.

| Scope | Class | Why |
|---|---|---|
| `.../auth/gmail.readonly` | sensitive | read threads for (c) |
| `.../auth/gmail.send` | sensitive | send the accepted draft |
| `.../auth/userinfo.email` | non-sensitive | identify the mailbox |

Avoid `gmail.modify` and `mail.google.com`. They are **restricted**: they force
verification and a security assessment. `readonly` + `send` covers the whole
product here and keeps verification to the lighter sensitive tier. Revisit only
if labelling drafts in-provider becomes a requirement.

**Microsoft Graph.** Required for Outlook and, notably, for the InboxKit
Microsoft 365 mailboxes:

| Scope | Why |
|---|---|
| `offline_access` | get a refresh token |
| `User.Read` | identity |
| `Mail.Read` | read threads |
| `Mail.Send` | send |
| `offline_access` plus, only if needed | `Mail.ReadWrite` for draft creation |

> **Needs confirmation.** Graph permission names and whether `Mail.ReadWrite`
> is required to create a draft (versus sending a body directly) were not
> verified against current Microsoft docs during this pass. Confirm against
> learn.microsoft.com before implementing. Do not take the table above as
> authoritative.

### 3.3 Token storage security

This is the highest-risk part of the whole plan.

1. **Encrypt at rest, always.** Fernet via the existing helper. Never a
   plaintext column, never a log line.
2. **Separate key from data.** `EMAIL_ENCRYPTION_KEY` currently covers SMTP and
   IMAP passwords. Add a dedicated `OAUTH_TOKEN_ENCRYPTION_KEY`. If the
   application tier is ever breached, blast radius stops at one key. Cost is one
   env var.
3. **Rotation.** Support `OAUTH_TOKEN_ENCRYPTION_KEY_PREVIOUS`. On read, try
   current then previous and re-encrypt on success. Rotation must not require
   a maintenance window or a full re-consent.
4. **Never return a token to a client.** Not in a response body, not in a
   redirect, not in a header. The frontend holds only its own ChampMail JWT.
5. **Logs.** Redact `access_token`, `refresh_token`, `code`, `client_secret`.
   The InboxKit webhook handler already strips `password`, `app_password` and
   `secret` from bodies; the same discipline applies here. Log token *ids* and
   expiry, never token *values*.
6. **Redis `state`.** Signed, single use, 10 minute TTL, bound to the session
   and the redirect URI. Prevents CSRF on the callback.
7. **Least privilege at rest.** A refresh token for a user's whole mailbox is
   worth more than the DB rows around it. Encrypt, restrict DB access, and keep
   it out of backups or encrypted backups at minimum.
8. **Revocation.** Disconnect sets `revoked_at` and deletes the row. Handle
   `invalid_grant` by marking revoked and prompting re-consent, never by
   looping refresh attempts.

### 3.4 Re-consent

| Trigger | Behaviour |
|---|---|
| `invalid_grant` / revoked refresh token | Set `revoked_at`, surface "reconnect your mailbox", stop retrying |
| User revokes at the provider | Detected on next refresh. Same path |
| Scopes change | Require explicit re-consent; do not silently widen |
| `refresh_token` absent (Google sometimes omits it) | Re-prompt with `access_type=offline&prompt=consent` |

**Refresh must be single-flight per connection.** Two workers refreshing the
same revoked token can invalidate a token the first one just obtained, because
Google rotates refresh tokens. Take a Redis lock keyed on `connection_id`.

### 3.5 Phase A exit criteria

- Google connect, refresh, disconnect, and re-consent-on-revoke all work
- Microsoft Graph connect verified against live docs and a test tenant
- Tokens never appear in logs, error responses, or the browser
- Key rotation proven: encrypt with old, read with previous, re-encrypt
- Redirect URI mismatch and CSRF rejected
- Security review passed (section 8)

---

## 4. Phase B: InboxKit domain and mailbox procurement

### 4.1 What InboxKit is

InboxKit is a **third-party paid email infrastructure provider**: it sells
domains and hosted mailboxes (Google Workspace and Microsoft 365 mailboxes on
your own domain, plus Azure-hosted M365).

Public pricing, checked 2026-10-01 from inboxkit.com/pricing:

| Item | Price |
|---|---|
| Google Workspace mailbox | $2.50/mailbox/mo on annual, $3.00 monthly |
| Microsoft 365 mailbox | $2.50/mailbox/mo on annual |
| Azure domain | ~$30/domain |
| Domains | from ~$7 for the first year |
| Payment | prepaid wallet |

**Flagging as an external dependency with unknown cost.** Cost scales linearly
with mailbox count. At $2.50/mailbox/mo, 100 mailboxes is ~$250/mo and 1,000 is
~$2,500/mo. That is a P&L decision for Deep, not an engineering one. Nothing in
ChampMail should auto-purchase.

### 4.2 Already built

PR #5 landed a substantial InboxKit integration. **Use it, do not rewrite it.**

| File | Role |
|---|---|
| `app/services/inboxkit/client.py` | REST wrapper, rate-limit aware, backs off on 429 |
| `app/services/inboxkit/provider.py` | `MailInfraProvider` implementation |
| `app/services/inboxkit/domain_connect.py` | DNS connect flow |
| `app/services/inboxkit/states.py` | InboxKit status to 8 logical states |
| `app/services/inboxkit/deliverability.py` | Warmup and deliverability |
| `app/api/v1/admin/inboxkit.py` | Admin routes |
| `app/api/v1/inboxkit_webhooks.py` | Webhook ingress |
| `app/services/mail_infra.py` | Provider registry |
| `app/services/mailbox_rotation.py` | Rotation under daily cap |
| `docs/inboxkit-byod-runbook.md` | Runbook |

The endpoints below were **live-verified by the agent who wrote PR #5** (per
`docs/inboxkit-integration-summary.md`), which is unusually good provenance.
Verified: domain search, mailbox list, mailbox status, show-credentials,
workspace list, set webhook. Untested because they cost money: register
domain, buy mailbox, cancel mailbox, warmup add/pause.

Auth: `Authorization: Bearer <api key>` plus `X-Workspace-Id: <workspace uid>`.

> **Needs confirmation.** Endpoint paths, the workspace id format, webhook
> signature scheme, and current pricing should be re-verified against InboxKit's
> own documentation before Phase B ships. The list above is taken from our own
> code and prior run notes, not from InboxKit's docs during this pass. The one
> thing independently confirmed here is the pricing page.

### 4.3 What Phase B adds

1. **Budget guard.** A per-team spend ceiling, checked in the purchase path.
   Refuse to buy past it. This does not exist and must.
2. **Purchase confirmation.** Always an explicit user action with the price
   shown. No background auto-buying.
3. **Credential handling.** Mailbox credentials are pulled at send time via the
   authenticated `show-credentials` call and never cached in plaintext. This is
   already how `tasks/sending.py` behaves; preserve it.
4. **State reconciliation.** `consent_request.status_changed` and
   `client_id_request.status_changed` are currently logged and ignored. Decide
   whether they need to drive state before launch.
5. **Decide the OAuth interaction.** InboxKit Microsoft 365 mailboxes can
   plausibly be authorized by Microsoft OAuth instead of SMTP-with-password.
   That would be strictly better. **Open question, not designed here**: it needs
   InboxKit's OAuth client model, which is unverified.

### 4.4 Phase B exit criteria

- Spend ceiling enforced and tested
- A real end-to-end purchase in a sandbox workspace, then a real domain, budgeted
- Webhook replay is idempotent (Redis dedup key, 24h, already implemented)
- Signature and freshness rejection tested (5 min window)
- No mailbox credential in logs or DB plaintext

---

## 5. Phase C: the JEV agent, correctly scoped

Restated per section 0.1: **an LLM pipeline over provider APIs, with JEV as a
fallback for browser-only consent or settings screens.**

### 5.1 Mailbox ingestion

| Provider | Read path |
|---|---|
| Google | Gmail API `users.messages.list` / `.get` with `format=metadata`, paginate history |
| Microsoft | Graph `/me/messages`, `$select` for headers only |

Read **headers and bodies of the Sent folder** plus recent inbox. Store into
`mailbox_threads`. Rate-limit aware, incremental by thread id and last-seen
timestamp, so re-runs are cheap.

**PII.** This is a user's entire mailbox. Scope the read tightly: Sent plus
recent inbox, not all folders, not all history, by default. Make depth
configurable. Never send raw mailbox content to a model provider without an
explicit, informed opt-in.

### 5.2 Segmentation (c)

`SegmentationService` already exists and returns segments with criteria, pain
points, messaging angle and priority. The work is feeding it real mailbox
signals rather than prospect research rows:

- sender domain, cadence of contact, reply rate per correspondent
- thread depth, typical response latency
- topic clustering over thread subjects

Input shape changes, output contract stays. That keeps the change small.

### 5.3 Where JEV actually fits

Narrow and explicit:

1. **OAuth consent fallback**, only when a provider flow fails in a headless or
   hardened environment and the user drives it interactively.
2. **Provider settings** that have no API (labelling, forwarding rules).

Constraints, carried over from the JEV notes and non-negotiable:

- Never on a send path. A send must not depend on a browser agent.
- Human-in-the-loop. JEV is a fallback, not an unattended actor.
- Inherits JEV's own limits: no shadow DOM, iframes, canvas, file uploads.
- No verification or benchmark exists for JEV at scale. Three repeats of one
  task proves repeatability, not reliability.

### 5.4 Phase C exit criteria

- Ingestion respects provider rate limits and resumes incrementally
- Segmentation produces stable output on a fixed mailbox fixture
- PII scope is enforced and asserted in tests
- JEV fallback is feature-flagged, off by default, and never on a send path

---

## 6. Phase D: voice extraction and reply drafting

### 6.1 Voice extraction

Input: the user's Sent folder.

1. Sample up to ~200 sent messages, preferring recent ones and messages with a
   real body over one-liners.
2. **Redact before any model call.** Strip signatures, phone numbers, addresses,
   other recipients, tracking parameters, and quoted history. Send the model
   redacted text only.
3. Extract traits into the `voice_profiles.traits` shape: greeting, sign-off,
   formality, average sentence length, emoji use, punctuation habits, hedges,
   favourite closings.
4. Keep up to 10 redacted exemplars.
5. Confidence from `sample_size`. Below a floor (say 20 messages), label the
   profile low-confidence and have the UI say so rather than pretending.

**Privacy:** exemplars must never leave the deployment without explicit
consent, and never be used to train anything.

### 6.2 Drafting

For a given inbound thread, produce **exactly two** variants plus a one-line
rationale, stored in `reply_drafts`.

| Requirement | How |
|---|---|
| In the user's voice | Voice profile in the system prompt; exemplars as few-shot |
| Contextually correct | Real thread history, not just the last message |
| Not generic | Explicitness and length matched to the counterpart's last message |
| Deterministic enough to test | Temperature low, fixed seed if the provider supports it |
| Honest about confidence | If voice confidence is low, say so in the rationale |

**Always draft. Never auto-send.** Auto-send is out of scope for this plan.

### 6.3 Evaluation

Voice quality cannot be eyeballed at scale. Minimum bar:

- A fixture set of ~20 real threads with human-written "in voice" replies
- Metric: embedding similarity to the human reference, plus a blind A/B on
  10 samples where a human says which is closer to the user's voice
- A regression gate so a prompt change that degrades voice fails CI

### 6.4 Phase D exit criteria

- Voice profile from a 200-message fixture looks right to Deep
- Two variants plus rationale on every fixture thread
- Blind A/B beats the no-voice baseline
- Redaction proven: no phone number or other recipient reaches the model

---

## 7. Phase E: mock threads and the accept/deny UX

### 7.1 Why mocks

Deep called this out explicitly, and it is the right call: it lets you demo and
test the draft-and-accept loop without touching live mail, and without an LLM
call per demo.

### 7.2 Generating realistic mock threads

Source: **redacted real correspondence from the user's own mailbox**. Mock
addresses (`prospect-0142@example.test`) replace real ones. `example.test` is
reserved by RFC 6761 precisely so nothing can resolve it.

```python
# backend/app/services/mock_threads.py  (proposed)

def generate_mock_thread(real_thread, *, n_variants=3) -> list[MockThread]:
    """Derive realistic inbound threads from prior correspondence.

    real_thread is already redacted. Returned threads use reserved-TLD
    addresses and carry no live Message-ID, so nothing can be replied to by
    accident.
    """
```

Properties required of a mock thread:

- Reserved-TLD addresses (`example.test`, `example.invalid`), never real ones
- No real `Message-ID`, no real `In-Reply-To`
- Realistic structure: multi-turn, varied length, includes at least one that
  needs a decline ("not interested", "wrong person")
- Reproducible from a seed, so a demo is repeatable

### 7.3 Contamination controls

This is a credential-handling risk and the controls are not optional:

- Mock threads live in a **separate table** or carry a hard `is_mock` flag that
  is checked in the send path
- **The send path refuses anything synthetic.** A mock thread that can reach SMTP
  can email a real address by accident
- Mock threads are never written into `mailbox_threads`
- No live provider credentials are used to render a mock

### 7.4 The accept/deny UX (e)

```
+---------------------------------------------------------------+
| Thread: "Re: pricing for the Q3 pilot"          [MOCK]       |
| 3 messages  ·  last from dana@partner.example.test  ·  2h    |
+---------------------------------------------------------------+
| From: dana@partner.example.test                                 |
| "Thanks for the sample. Can you do 20 seats at 15k and          |
|  send over the revised MSA? We'd need it by Friday."           |
+---------------------------------------------------------------+
|  A  Sounds right, Dana. Sending over the revised MSA today.    |
|     I'll attach it. One flag: our 15k tier is annual, so I'll   |
|     start the clock today.                                      |
|                                                               |
|  B  Happy to do 20 seats at 15k. Sending the MSA over now.     |
|     Note the 15k tier is annual rather than monthly.           |
|                                                               |
|     Why these two: both answer the price and commit to a       |
|     date; A matches your habit of leading with a caveat,       |
|     B is the plainer version you use with external counsel.   |
|     Confidence: high (48 sent messages in profile).            |
+---------------------------------------------------------------+
|   [ Send A ]   [ Send B ]   [ Edit ]   [ Reject ]   [ Skip ]  |
+---------------------------------------------------------------+
```

Decisions recorded in `reply_drafts.decision`. Reject and Skip are different
intents and both must be recorded: reject means wrong, skip means not now. That
distinction is the training signal for the future.

Required behaviour:

- Nothing sends without an explicit tap. No auto-send, no countdown
- Low voice confidence is visible before the user reads the drafts
- Edit shows the edited text as the new draft
- Reject captures an optional reason

---

## 8. Security review: what to escalate

Flagged prominently because this feature handles credentials and personal mail.

| # | Risk | Severity | Mitigation | Gate |
|---|---|---|---|---|
| S1 | Refresh token exfiltration from the DB | **Critical** | Dedicated encryption key, least-privilege DB, no plaintext ever | Phase A exit |
| S2 | Token leakage into logs or error responses | **Critical** | Redaction at the logging layer, not per call site | Phase A exit |
| S3 | OAuth CSRF via a leaked or reused `state` | High | Signed single-use state, 10 min TTL, session-bound | Phase A |
| S4 | Token refresh race invalidating a good token | High | Redis single-flight lock per connection | Phase A |
| S5 | Over-broad scopes (restricted-scope verification burden, breach blast radius) | High | `readonly` + `send` only; escalate scope changes | Phase A design |
| S6 | Mock thread reaching a real recipient | **Critical** | Send path hard-refuses synthetic threads | Phase E exit |
| S7 | Full-mailbox PII sent to a model provider | High | Tight scope, redaction, explicit opt-in | Phase C exit |
| S8 | InboxKit purchase without a human decision | High | Budget ceiling plus explicit confirmation | Phase B exit |
| S9 | Voice exemplars containing third-party personal data | High | Redact signatures, quoted history, other recipients | Phase D exit |
| S10 | Prompt injection from inbound email content | High | Inbound text is data, never instruction. Fixed system prompt, no tools reachable from email content | Phase D exit |
| S11 | Unbounded InboxKit spend | Medium | Budget ceiling | Phase B |
| S12 | Voice profile for the wrong user (cross-tenant leak) | **Critical** | Every voice and draft query filtered by `user_id` at the query, not in Python | Phase D exit |

**S10 deserves a note.** Inbound email is attacker-controlled text that will be
placed inside a prompt. It must never be able to instruct the model. The system
prompt is fixed; thread content goes in a clearly delimited data block; the
drafting model gets no tool access.

**S12 is the one to test hardest.** Tenant isolation is easiest to get wrong in
exactly this shape: a `get_profile(user_id)` call that trusts a `user_id` from
the request body, or a `reply_drafts` lookup keyed on thread id alone. Write the
negative tests first.

---

## 9. Phasing and dependencies

```
Phase A  OAuth sign-in                ──┐
                                        ├──> Phase C  Mailbox read + segmentation
Phase B  InboxKit procurement ─────────┘                  │
                                        │                  v
                                        └──> Phase D  Voice + drafting
                                                                   │
                                                                   v
                                                  Phase E  Mock threads + UX
```

| Phase | Depends on | Independently shippable? | Gate |
|---|---|---|---|
| A. OAuth sign-in | none | yes, behind a flag | Security review S1-S5 |
| B. InboxKit procurement | none | yes, admin-only | Budget test, real sandbox purchase |
| C. Mailbox read + segmentation | A | yes, read-only | PII scope tests, rate-limit test |
| D. Voice + drafting | A, C | yes, drafts only, never sends | Blind A/B beats baseline |
| E. Mock threads + accept/deny UX | D | yes, behind a flag | Send path refuses synthetic |

A and B are parallel and share nothing. That is deliberate: A is the long pole
because of OAuth verification, so start it first and let B proceed alongside.

Every phase is behind a feature flag and dark by default. Nothing in this plan
changes the behaviour of an existing send.

---

## 10. Open questions for Deep

Ordered by how much they block.

1. **Is the JEV split right?** (section 0.1) JEV is a browser agent, not a
   mailbox-understanding agent. Plan uses provider APIs for content and keeps
   JEV as a consent/settings fallback. Confirm or tell me the browser-driven
   path is genuinely required.
2. **Which providers first?** Google only, or Google plus Microsoft? Microsoft
   doubles the work but is also the InboxKit M365 path.
3. **Is OAuth verification acceptable?** Restricted scopes avoid it but limit
   labelling. Sensitive-only scopes still need verification, on Google's
   schedule, not ours.
4. **InboxKit budget ceiling.** Per team, per month? What is the number? At
   $2.50/mailbox/mo, 100 mailboxes is ~$250/mo.
5. **Is sending from a user's own connected mailbox in scope at all**, or is
   OAuth read-only for the reply agent, with sending still via owned/InboxKit
   domains? This materially changes the safety profile and the scopes.
6. **Mock thread realism floor.** Is "derived from real correspondence with
   reserved-TLD addresses" good enough, or do you want fully synthetic
   generation?
7. **Does a reply draft ever auto-send?** Plan says never. Confirm.
8. **Who owns the Google OAuth app and the privacy policy?** Verification needs
   a named owner and a public privacy policy URL.
9. **ChampHarbinger direction** (section 11): confirm the waterfall contract
   still holds on their side.
10. **LICENSE.** A proprietary placeholder was added. Confirm or replace.

---

## 11. ChampHarbinger reconciliation

ChampHarbinger is owned by another team and is actively developed. **Do not
refactor it and do not assume its internals.** ChampMail must only interoperate.

The entire current surface is one file, `app/services/harbinger_client.py`:

| Assumption ChampMail makes | Status |
|---|---|
| `POST {HARBINGER_URL}/api/v1/enrich/waterfall` | implemented |
| `Authorization: Bearer $HARBINGER_API_KEY` | implemented |
| Key is a per-workspace BYOK key validated against their `userApiKeys` table | **their side, unverified by us** |
| Returns an `EnrichmentResult` with `contactId`, `status`, `resolvedTier`, `fields`, confidence scores | **their shape, unverified** |
| Unreachable or unset means return `None` and continue | implemented, fire-and-forget |
| Runs before `personalize_emails()` in the campaign pipeline | implemented |

Settings: `harbinger_url`, `harbinger_api_key`.

**What this plan adds, and must keep minimal:** exactly one new assumption. The
JEV reply agent needs to know a correspondent is real before drafting to them.
That reuses `verify_contact()` unchanged. **No new endpoint, no new field, no
new dependency.**

Action: re-check the waterfall response shape against their current code before
Phase D. Their branches `feat/inboxkit-flow-fixes`, `feat/voice-channel` and
`feat/send-integrity` suggest active change in exactly the areas we depend on.

If `feat/voice-channel` turns out to overlap this work, that is a conversation
with their team, not a merge.

---

## Appendix: what was verified versus assumed

**Verified by reading this repo:** every file path, class, function, and schema
field cited in section 1; the two transports in `tasks/sending.py`; the single
alembic head; the Fernet credential path; InboxKit pricing from
inboxkit.com/pricing (2026-10-01); Google's scope classifications from
developers.google.com.

**Verified from the JEV project notes** (`Projects/Jev Camoufox Agent/`, dated
2026-09-27): everything in the section 0.1 table, including the self-declared
limits and the "not yet wired to anything" status.

**Taken from PR #5's own notes, not re-verified here:** the InboxKit endpoint
list and live-verification status.

**NOT verified, must confirm before building:** Microsoft Graph permission
names; InboxKit endpoint paths and the OAuth client model; Google's current
verification requirements and timeline; InboxKit pricing at contract rates.

**No LLM output was used as a source for any factual claim in this document.**