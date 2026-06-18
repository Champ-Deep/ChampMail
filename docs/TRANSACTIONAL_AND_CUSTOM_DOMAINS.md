# ChampMail → Transactional Email + Custom-Domain Hosting (multi-tenant)
**Date:** 2026-06-12 · **Status:** RESEARCH + PLAN (no code yet)
**Goal:** other companies use the Champ suite with **their own domain** on ChampMail —
sending transactional (signup/OTP/receipts/payment) + marketing email under that domain.

> Companion to `SUITE_EXTENSION_ROADMAP.md`. The deliverability + suppression +
> identity-spine + event-bus work already done is the foundation this builds on.

---

## A. Transactional email (separate path from the cold-outreach we built)

### A1. Why a SEPARATE path
Transactional = 1:1, user-triggered (verify, OTP, password reset, receipts/invoices,
shipping, appointment check-ins, account notices, any "abstract" triggered 1:1).
The industry rule (Postmark): **transactional and bulk MUST NOT share IPs** — Postmark
runs them on completely separate infrastructure so bulk can never degrade time-sensitive
transactional inbox placement. Transactional is optimized for **Time-to-Inbox** (low
latency); bulk for reliability. ⇒ ChampMail sends transactional from a **distinct
subdomain (`mail.`/`notifications.`) + distinct IP pool** from the marketing path.
No legal unsubscribe requirement for pure transactional (but keep List-Unsubscribe for
borderline upsell receipts).

### A2. Architecture to add (model on Postmark Message Streams + Postal)
- **Message Streams** abstraction: stream types `transactional | broadcast | inbound`,
  immutable after create. `POST/GET/PATCH /v1/message-streams`; every send names its stream.
- **Transactional send path:** `POST /v1/email` — **synchronous, low-latency** (return a
  message id immediately), high-priority Celery queue + dedicated IP pool on the Go engine.
  Marketing stays on the existing queued path.
- **Per-tenant API keys** (scoped: send-only / report-only, per domain). Subaccount model.
- **Idempotency keys** — BUILD IT (Postmark does NOT have them; MailPace is the OSS ref):
  client sends `Idempotency-Key` header (bare, not `X-`), store a hash in **Redis** with a
  dedup window, return the original message id on repeat. ChampMail already runs Redis.
- **Webhooks** delivery/bounce/open/click/complaint — **return 200 immediately, process in
  Celery** (providers retry → dupes). Model events on Postal: `MessageSent / MessageDelayed /
  MessageDeliveryFailed / MessageBounced / MessageHeld / MessageLoaded / MessageLinkClicked`
  + **`DomainDNSError`** (fires on SPF/DKIM/MX/return-path failure — surface in onboarding UI).
- **Per-tenant suppression** (we already have the suppression backbone — extend it per-tenant
  for transactional bounce/complaint addresses).
- **Message DB + IP pools** (Postal patterns): store every message with retention; IP pools
  route transactional vs bulk on separate IPs/subdomains.

### A3. OSS to learn from
**Postal** (closest blueprint — message DB, IP pools, webhook event model). **Stalwart**
(already our MTA; native DKIM/SPF/DMARC/ARC + **auto DKIM key rotation**). **Maddy** (Go,
matches our mail-engine language). Keep Stalwart/Postfix as MTA; model the API/message-DB/
IP-pool/webhook layer on Postal.

### A4. Payment / financial emails
MJML templates + variables/loops (line items). Seed receipt/invoice templates
(`mjmlio/email-templates`). Flow: **Stripe/Razorpay webhook** (`invoice.paid`,
`payment_failed`, `subscription.*`) → verify signature (`stripe-signature` + raw body +
signing secret) → render MJML with event data → send via the transactional API on the
tenant's authenticated domain. Stripe's own receipts can't be branded — so this is the
value-add: branded, on-domain payment emails.

---

## B. Custom-domain + DNS automation (the core ask)

### B1. cPanel vs WHM (the multi-tenant fit)
- **cPanel** = per-account (one customer's sites/email/DNS). **WHM** = server/reseller admin
  that *creates* cPanel accounts, packages, nameservers. **Reseller model = our multi-tenancy:
  each Champ-suite customer = one cPanel account under ChampMail's WHM**, isolated, with a
  **white-label branded UI** (logo/colors) → "other company runs the suite under its own brand".

### B2. The automation APIs
Three: **WHM API 1** (server-wide: `createacct`, zones), **UAPI** (account-level, preferred),
**cPanel API 2** (legacy, but still where per-record DNS lives). Key calls:
- `createacct` (username, domain, plan) — provision a tenant cPanel account.
- **`mass_edit_dns_zone`** (WHM API 1) — bulk add/edit/remove records w/ serial handling
  (modern); `parse_dns_zone`/`dumpzone` read back.
- **`ZoneEdit::add_zone_record`** (cPanel API 2) — per-record workhorse (no UAPI equivalent):
  - TXT (SPF/DKIM/DMARC): `domain,name,type=TXT,txtdata,ttl`
  - CNAME (delegation/verify): `domain,name,type=CNAME,cname`
  - A: `domain,name,type=A,address`
  - `edit_zone_record`, `remove_zone_record`, `fetchzone`.
- **Auth = WHM API tokens** (not root pw): header `Authorization: WHM root:APITOKEN`, hit
  `https://host:2087/json-api/<func>?api.version=1`. Tokens scoped + rotatable.
- **AutoSSL / Let's Encrypt** TLS: install provider via `install_lets_encrypt_autossl_provider`;
  `start_autossl_check_for_one_user`; or `acme.sh` cPanel deploy hook via UAPI.

### B3. github.com/cpanel reality
Official org is thin (mostly Perl/system tools), **no official Python/Go SDK**. Repos:
`CpanelInc/publicapi-php` (official PHP, barely maintained), `CpanelInc/xmlapi-php` (legacy),
`cpanel/p5-cPanel-APIClient` (Perl). Community: `zanysoft/cpanel-api`, `mgufrone/cpanel-php`,
`johnie/cpanel-zone-file`, `cloudflare/Cloudflare-CPanel`. **Since ChampMail is FastAPI
(Python), call the WHM JSON-API directly over httpx with a token** — the header format is
simple; no SDK needed.

### B4. Custom-domain onboarding — the TWO models
A customer wants `mail.theircompany.com` to send via ChampMail.

- **Model 1 — customer self-serves DNS at their registrar; we just verify (DEFAULT, SaaS).**
  The SendGrid/Resend/Postmark pattern. Customer adds a **DKIM CNAME (delegation flavor →
  lets us rotate DKIM later without them touching DNS)** + SPF TXT + return-path MX + optional
  DMARC. We generate the records, poll DNS, drive a **Resend-style state machine**:
  `created → records_generated → pending → verifying → verified → active`
  (+ `partially_verified`, `failed` after 72h, `temporary_failure`). On verified → enable
  sending + AutoSSL. Strongly prefer sending from a **subdomain** (reputation isolation).
- **Model 2 — ChampMail HOSTS the customer's DNS via cPanel/WHM (premium / white-label).**
  Customer delegates the (sub)domain NS to our nameservers; we write all records via
  `add_zone_record`/`mass_edit_dns_zone` + AutoSSL. Zero customer DNS work. Uses the WHM
  reseller account model.

**Recommendation:** **Model 1 = default** (low friction, no hosting liability, any registrar).
**Model 2 = premium "fully-managed / white-label" tier** on WHM.

### B5. Don't lock to cPanel — DNS provider abstraction
Abstract DNS behind a provider interface with adapters: **self-serve-verify** (default),
**cPanel/WHM**, **Cloudflare API**, **PowerDNS** (be-the-nameserver / NS-delegation),
**OctoDNS** (DNS-as-code in git for ChampMail's OWN infra zones). cPanel is one pluggable
provider, not the foundation. For pure email custom domains, Model 1 + Cloudflare/PowerDNS
for our own zones; cPanel only when we also host the tenant.

### B6. White-label / reseller
WHM reseller + per-account cPanel + custom-domain flow = each suite customer runs under its
own brand + domain, isolated, optionally with its own mailboxes — the literal "other company
uses our suite with their own domain" requirement.

---

## Plan & roadmap

**Automation surface:** `POST /v1/email` (sync transactional, stream + Idempotency-Key) ·
`/v1/message-streams` · `/v1/suppressions` (per-tenant) · `/v1/webhooks` · template service
(MJML + Stripe/Razorpay webhook→render→send) · **custom-domain service** (DKIM keygen per
tenant-domain + a DNS provider interface {self-serve-verify, cPanel/WHM, Cloudflare, PowerDNS}
+ DNS-poll verification state machine + AutoSSL).

**Onboarding state machine (Resend-modeled):**
`created → records_generated → pending → verifying → verified → active`,
branches `partially_verified | failed(72h) | temporary_failure`; `DomainDNSError` webhook can
demote `active → failed`.

**Roadmap**
- **S (weeks):** transactional send path (sync) + message streams + per-tenant keys + Redis
  idempotency + per-tenant suppression. Model-1 custom domain (DKIM keygen, show records,
  DNS-poll verify, state machine). MJML receipt templates + Stripe webhook → receipt email.
- **M (1–2 mo):** Postal-style message DB + IP pools (transactional/bulk IP+subdomain
  separation) + full async webhook events. DNS provider abstraction (Cloudflare/PowerDNS).
  AutoSSL/acme.sh TLS.
- **L (quarter+):** cPanel/WHM reseller (Model 2) — `createacct` + `mass_edit_dns_zone` +
  AutoSSL via WHM tokens for fully-managed/white-label tenants; OctoDNS-in-git for our zones;
  DKIM auto-rotation (Stalwart); inbound/reply streams.

**Caveats:** Postmark has no idempotency keys (build it, Redis); no official cPanel Python SDK
(call WHM JSON-API directly); no UAPI equivalent for `add_zone_record` (use cPanel API 2 / WHM
`mass_edit_dns_zone`); `include:` SPF lookups count against the 10-lookup limit.

_Sources: Postmark Message Streams; Postal docs/webhooks/IP-pools; MailPace idempotency;
SendGrid Automated Security; Resend domains; cPanel API 2 ZoneEdit; WHM API tokens/createacct;
AutoSSL; github.com/cpanel; OctoDNS/Cloudflare/PowerDNS; MJML+Stripe; Stalwart/Haraka/Maddy._
