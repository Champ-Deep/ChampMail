# ChampMail — Self-Hosted Email Engine: Complete Production Plan

> **Goal:** Build a fully self-hosted email engine on our VPS with custom domains that achieves 92-97% inbox placement on Gmail, Outlook, and Yahoo — without relying on any third-party relay like TurboSMTP.

---

## Table of Contents

1. [Current State — What's Broken](#current-state)
2. [Tier 1 — DNS & Authentication](#tier-1)
3. [Tier 2 — Server & MTA Hardening](#tier-2)
4. [Tier 3 — IP Strategy & Warmup](#tier-3)
5. [Tier 4 — Email Content Requirements](#tier-4)
6. [Tier 5 — Sending Behavior & Rate Control](#tier-5)
7. [Tier 6 — Monitoring & Reputation Management](#tier-6)
8. [Domain Strategy — How Many & Where](#domain-strategy)
9. [Cloudflare DNS — Exact Setup Per Domain](#cloudflare-setup)
10. [OpenDKIM — Why It's Non-Negotiable](#opendkim)
11. [Final Architecture — Complete Picture](#final-architecture)
12. [Implementation Phases](#implementation-phases)
13. [Before vs After](#before-vs-after)
14. [Cost Breakdown](#cost-breakdown)

---

## What Exists vs What This Plan Assumes {#reality-check}

Before building anything new, the codebase had these gaps between plan and reality:

| Module | Plan Assumed | Reality (Fixed in Phase 0) |
|--------|-------------|---------------------------|
| Warmup enforcement | Will be built | Built but 0 enforcement callers → **Fixed** |
| Blacklist checking | Will be built | Built but never called → **Fixed** |
| Mail path | Postfix direct | Direct to TurboSMTP, bypassed Postfix → **Fixed** |
| SSL/TLS | Let's Encrypt | Cert verification DISABLED in code → **Fixed** |
| Graduation day | Day 60 | Hardcoded at day 30 → **Fixed** |
| Midnight reset | Will be built | sent_today never reset → **Fixed** |
| Mail-engine client | In use | Full HTTP client written, never called → **Deleted** |
| Email provider ABC | In use | Abstract base class, never integrated → **Deleted** |

---

## Current State — What's Broken {#current-state}

### Critical Issues Right Now

| Issue | Impact |
|-------|--------|
| Using TurboSMTP smarthost relay | Not truly self-hosted, dependent on third party |
| Self-signed TLS certificate hardcoded for champmail.com | Gmail/Outlook see fake cert — trust penalty |
| `relay_domains = *` in Postfix | Open relay — spammers will find and abuse it, instant blacklisting |
| No DKIM signing (no OpenDKIM) | Emails unsigned — 25-30% of inbox placement lost |
| No PTR/reverse DNS coordination | Server can't prove its identity — high spam scores |
| No bounce reception on port 25 | Flying blind on delivery failures |
| Warmup limits ignored in DomainRotator | Domains over-sending during warmup, destroying reputation |
| No blacklist monitoring | Could be blacklisted right now and not know it |
| No daily sent_today counter reset | Rotator eventually sees all domains at capacity |
| Warmup schedule only 8 days | Industry standard is 60 days |

### Current Email Flow (Broken)
```
Your App → Postfix → TurboSMTP (third party) → Gmail
```

### Target Email Flow (Self-Hosted)
```
Your App → Postfix → OpenDKIM (signs email) → Gmail directly
```

---

## Tier 1 — DNS & Authentication {#tier-1}

### What It Is
DNS authentication is your email's identity system. It proves to Gmail and Outlook that you are who you say you are. Without it, every email you send is treated as potentially forged.

### 1.1 PTR / Reverse DNS (rDNS) — Most Critical

Every sending IP must have a PTR record that resolves back to your mail hostname.

```
PTR:     <VPS_IP>  →  mail.yourdomain.com
Forward: mail.yourdomain.com  →  <VPS_IP>
```

- Set this in your VPS control panel (Hetzner, Vultr, DigitalOcean all support it)
- The hostname in Postfix `myhostname` must exactly match the PTR record
- This is the #1 reason VPS IPs get rejected — fix this first

### 1.2 SPF Record (per domain)

```
Type:  TXT
Name:  @
Value: v=spf1 ip4:<VPS_IP> -all
```

- Use hard fail (`-all`) not soft fail (`~all`)
- One SPF record per domain — no more than 10 DNS lookups
- If using multiple IPs: `v=spf1 ip4:x.x.x.x ip4:y.y.y.y -all`

### 1.3 DKIM — Cryptographic Signature

```
Type:  TXT
Name:  champmail._domainkey
Value: v=DKIM1; k=rsa; p=<2048-bit public key>
```

- 2048-bit RSA keys minimum (4096-bit preferred for new setups)
- One unique keypair per domain — never reuse keys across domains
- Key rotation every 6 months — keep old selector live 72 hours post-rotation
- Requires OpenDKIM running as a Postfix milter on your server (see Tier 2)

### 1.4 DMARC — The Policy That Ties Everything Together

```
Type:  TXT
Name:  _dmarc
Value: v=DMARC1; p=none; rua=mailto:dmarc@yourdomain.com; pct=100
```

**Phased rollout:**
- Weeks 1-4: `p=none` — monitor only, don't take action
- Weeks 5-8: `p=quarantine` — send failing emails to spam
- Month 3+:  `p=reject` — block failing emails completely

### 1.5 MX Record

```
Type:     MX
Name:     @
Priority: 10
Value:    mail.yourdomain.com
```

Required for bounce reception — Gmail needs somewhere to send failure notifications.

### 1.6 BIMI (Optional — Month 3+)

```
Type:  TXT
Name:  default._bimi
Value: v=BIMI1; l=https://yourdomain.com/logo.svg; a=
```

Shows your logo in Gmail next to the sender name. Requires DMARC `p=reject` to be stable first.

---

## Tier 2 — Server & MTA Hardening {#tier-2}

### 2.1 Postfix — Critical Configuration Changes

**Replace the current broken config with:**

```ini
# Identity — must exactly match PTR record
myhostname = mail.yourdomain.com
mydomain = yourdomain.com
myorigin = $mydomain

# Close the open relay (CRITICAL)
relay_domains =
mynetworks = 127.0.0.0/8 [::ffff:127.0.0.0]/104 [::1]/128 172.16.0.0/12

# TLS outbound (to recipient mail servers)
smtp_tls_security_level = may
smtp_tls_loglevel = 1
smtp_tls_CAfile = /etc/ssl/certs/ca-certificates.crt
smtp_tls_protocols = !SSLv2, !SSLv3, !TLSv1, !TLSv1.1

# TLS inbound (submission from app)
smtpd_tls_cert_file = /etc/letsencrypt/live/mail.yourdomain.com/fullchain.pem
smtpd_tls_key_file  = /etc/letsencrypt/live/mail.yourdomain.com/privkey.pem
smtpd_tls_security_level = may
smtpd_tls_protocols = !SSLv2, !SSLv3, !TLSv1, !TLSv1.1
smtpd_tls_auth_only = yes

# OpenDKIM milter
milter_default_action = accept
milter_protocol = 6
smtpd_milters = inet:localhost:8891
non_smtpd_milters = inet:localhost:8891

# Queue behavior
maximal_queue_lifetime = 5d
bounce_queue_lifetime = 2d
default_destination_concurrency_limit = 5
smtp_destination_rate_delay = 1s

# Strip internal IPs from headers
header_checks = regexp:/etc/postfix/header_checks

# Professional banner — reveal nothing
smtpd_banner = $myhostname ESMTP
```

**header_checks file — strip internal metadata:**
```
/^Received:.*\(.*\[(?:10\.|172\.|192\.168\.)/ IGNORE
/^X-Originating-IP:/ IGNORE
/^X-Mailer:/ IGNORE
```

### 2.2 Let's Encrypt TLS — Replace Self-Signed Cert

```bash
certbot certonly --standalone -d mail.yourdomain.com
```

- Free, globally trusted certificate
- Auto-renews every 90 days
- Mount into Postfix container replacing the fake self-signed cert
- Hook: `systemctl reload postfix` after renewal

### 2.3 OpenDKIM — New Container

OpenDKIM runs as a milter (middleware) between your app and Postfix. Its only job: sign every outgoing email with your domain's private key.

**Flow:**
```
Your App → Postfix → OpenDKIM (signs) → Postfix → Gmail
```

**Config for multiple domains (KeyTable + SigningTable):**

```
# KeyTable
champmail._domainkey.domain1.com   domain1.com:champmail:/keys/domain1.private
champmail._domainkey.domain2.com   domain2.com:champmail:/keys/domain2.private

# SigningTable
*@domain1.com   champmail._domainkey.domain1.com
*@domain2.com   champmail._domainkey.domain2.com
```

**When a new domain is added in ChampMail:**
1. Generate RSA keypair → store in DB
2. Write new line to KeyTable + SigningTable
3. Send HUP signal to OpenDKIM to reload
4. Add public key to Cloudflare DNS

### 2.4 Native Bounce Reception

Replace webhook-only bounce handling with native SMTP bounce reception:

- Postfix accepts inbound SMTP on port 25 for your sending domains
- Use VERP (Variable Envelope Return Path): `MAIL FROM: bounce+{prospect_id}@mail.yourdomain.com`
- Postfix pipes DSN messages to bounce_handler.py
- Parser extracts prospect ID, fires Celery `process-bounces` task
- End-to-end bounce pipeline with no third-party dependency

---

## Tier 3 — IP Strategy & Warmup {#tier-3}

### 3.1 Dedicated IP Selection

Before using any VPS IP for email, check it against blacklists:

**Blacklists to check:**
- Spamhaus ZEN (covers SBL + XBL + PBL)
- Barracuda BRBL
- SpamCop
- SORBS
- UCEProtect L1

**Check at:** mxtoolbox.com/blacklists.aspx

**VPS providers with clean IP pools:**
- Hetzner (Germany) — recommended
- OVH — good option
- Vultr — generally clean
- Avoid: AWS, GCP, Azure (IP ranges often pre-blocked by Outlook)

### 3.2 IP Warmup Schedule

A new IP must be introduced gradually. Gmail tracks sending volume per IP and treats sudden high volume as spam.

| Day | Max/Day | Max/Hour | Rule |
|-----|---------|----------|------|
| 1-3 | 15 | 5 | Prove you exist |
| 4-7 | 50 | 10 | Building early pattern |
| 8-14 | 150 | 20 | First week of history |
| 15-21 | 500 | 50 | Reputation scoring active |
| 22-30 | 1,000 | 100 | Month 1 complete |
| 31-45 | 3,000 | 300 | Solid sender |
| 46-60 | 8,000 | 800 | High trust established |
| 61+ | 15,000 | 1,500 | Graduated — full capacity |

**Warmup rules:**
- Only send to verified, high-quality contacts during warmup
- Maintain seed inbox network (Gmail, Outlook, Yahoo accounts you control)
- Interact with seed emails: open, click, move from spam to inbox
- Warmup graduation: day 60 (`warmup_day >= 60`)

### 3.3 Domain Warmup (Separate from IP Warmup)

Domains have their own reputation score independent of the IP.

- New domain → follow same 60-day ramp schedule
- Use subdomains for sending: `mail.yourdomain.com`, not `yourdomain.com`
- Multiple domains warm in parallel — start all new domains simultaneously

**What's currently broken in ChampMail:**
- `DomainRotator` ignores warmup limits entirely — uses static `daily_send_limit`
- `warmup_day` counter stored in DB but never used to gate sends
- `sent_today` never resets at midnight
- Warmup graduation at day 30 (should be day 60)

**What needs to be fixed:**
- `warmup_schedule.py` — authoritative schedule module
- `DomainRotator` — gates effective limit from warmup schedule
- Celery beat task at midnight — resets `sent_today`, advances `warmup_day`
- Graduation logic — disable warmup at day 60, unlock full `daily_send_limit`

---

## Tier 4 — Email Content Requirements {#tier-4}

### 4.1 Required Headers (Every Campaign Email)

```
From: Display Name <sender@yourdomain.com>
To: recipient@theirdomain.com
Subject: ...
Date: Mon, 12 May 2026 10:30:00 +0000
Message-ID: <uuid@mail.yourdomain.com>
MIME-Version: 1.0
List-Unsubscribe: <mailto:unsub@yourdomain.com?subject=unsubscribe-{id}>, <https://track.yourdomain.com/unsubscribe/{token}>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```

**`List-Unsubscribe-Post` is mandatory** — Google's February 2024 bulk sender policy requires one-click unsubscribe for 5,000+ emails/day to Gmail.

### 4.2 Multipart MIME — Always Required

Every email must be `multipart/alternative` with both versions:

```
multipart/alternative
├── text/plain  (always — never empty, real content)
└── text/html   (with tracking injected)
```

An HTML-only email with no plain text is a major spam signal.

### 4.3 Content Rules

| Rule | Requirement |
|------|-------------|
| URL shorteners | Never use (bit.ly, t.co, etc.) — use your own tracking domain |
| Tracking domain | Separate subdomain (`track.yourdomain.com`) — not main domain |
| HTML/text ratio | Minimum 60% readable text, max 40% images/links |
| Spam words | Avoid: FREE, GUARANTEED, CLICK HERE, ACT NOW, LIMITED TIME |
| From/Reply-To | Must be on same domain — mismatches flagged as phishing |
| Subject line | Must reflect actual content — no deceptive subjects |
| Email size | Under 102KB HTML — Gmail clips larger emails (breaks tracking) |
| Links | Must use HTTPS — HTTP links in email = spam signal |
| Message-ID | `<uuid@mail.yourdomain.com>` — domain must match sender |

### 4.4 Tracking Infrastructure

**Tracking pixel:** 1x1 transparent image — fires when email is opened
**Click wrappers:** Links replaced with tracking redirect, then to real URL

**Critical setup:**
- Tracking on `track.yourdomain.com` — separate subdomain
- HTTPS only — valid TLS cert on tracking domain
- Tracking domain must never have been used for spam
- Apple Mail Privacy Protection pre-fetches images — open rates are inflated, use click rates as primary engagement signal

---

## Tier 5 — Sending Behavior & Rate Control {#tier-5}

### 5.1 Human-Pattern Sending — Eliminate Robot Behavior

**Current problem:** `cadence_seconds = 3600` sends with perfectly mechanical timing. Gmail detects this.

**Fix — add ±30% jitter to every send interval:**
```
Base cadence: 3600 seconds
Jitter range: ±1,080 seconds (30%)
Actual delay: anywhere from 2,520s to 4,680s
```

**Additional behavior rules:**
- B2B sends: Monday-Friday only, never weekends
- Time window: 8am-5pm recipient's local timezone
- Tuesday, Wednesday, Thursday are optimal days
- Never send in bulk at 2-4am UTC (overnight queue processing)

### 5.2 Per-Destination Domain Throttling

| Provider | Daily Limit (new IP) | Max Connections |
|----------|---------------------|-----------------|
| Gmail | 3,000/day initially | 5 simultaneous |
| Outlook | Aggressive throttling | 30 simultaneous |
| Yahoo | ~100/hour (new IP) | Varies |

Postfix `default_destination_concurrency_limit = 5` handles connection limits.
Application layer must enforce volume limits per destination provider.

### 5.3 Bounce Rate Enforcement — Automatic Safety Gates

**These thresholds must trigger automatic action:**

| Metric | Threshold | Automatic Action |
|--------|-----------|-----------------|
| Hard bounce rate | > 2% | Pause domain, alert admin |
| Soft bounce rate | > 5% | Reduce send rate 50% |
| Spam complaint rate | > 0.08% | Reduce send rate 50% |
| Spam complaint rate | > 0.3% | Pause domain permanently |
| Blacklist hit | Any | Pause domain, alert admin |

### 5.4 Email Validation Before Every Send

**Check in this order before sending:**
1. Format check — is it a valid email format?
2. MX record check — does the domain have a mail server?
3. Role address filter — skip info@, admin@, noreply@, postmaster@, abuse@
4. Suppression list check — was this person on any domain blacklisted before?

---

## Tier 6 — Monitoring & Reputation Management {#tier-6}

### 6.1 Google Postmaster Tools

Register every sending domain at: `postmaster.google.com`

**Monitor daily:**
- Domain Reputation: must stay Green (High)
- IP Reputation: must stay Green (High)
- Spam Rate: must stay below 0.08%
- Authentication: must be near 100%
- Delivery Errors: any spike needs immediate diagnosis

**Action thresholds:**
- Domain drops to Medium → diagnose within 24 hours
- Domain drops to Low → pause all sending, diagnose immediately
- Spam rate hits 0.1% → pause campaign, review content

### 6.2 Microsoft SNDS & JMRP

**Register at:** `sendersupport.olc.protection.outlook.com`

- SNDS: Real-time IP status (Green/Yellow/Red), spam trap hits
- JMRP: Receive individual spam complaint emails from Outlook users
- Every JMRP complaint → immediately add to suppression list

### 6.3 Blacklist Monitoring (Every 6 Hours via Celery)

**Zones to check:**
- `zen.spamhaus.org` — most important
- `b.barracudacentral.org`
- `bl.spamcop.net`
- `dnsbl.sorbs.net`
- `dnsbl-1.uceprotect.net`
- `ix.dnsbl.manitu.net`

**If blacklisted:**
1. Auto-pause all sending from that IP/domain
2. Send admin alert with which blacklist
3. Fix underlying issue
4. Submit delisting request
5. Resume only after confirmed delisted

### 6.4 DMARC Report Processing

Every domain's `rua=` address receives XML aggregate reports from Gmail, Outlook, etc.

**What reports reveal:**
- SPF failure rate per day
- DKIM failure rate per day
- Spoofing attempts (someone forging your domain)
- Unauthorized senders (third-party tools using your domain)

**Tool:** Use `parsedmarc` Python library to parse XML into readable data. Store parsed results in PostgreSQL. Alert on failure rate spikes.

### 6.5 Seed Network — Inbox Placement Testing

**Maintain test accounts at:**
- Gmail (gmail.com)
- Outlook (outlook.com)
- Yahoo (yahoo.com)
- Apple iCloud (icloud.com)
- ProtonMail (protonmail.com)

**Before every campaign launch:**
1. Send to all seed accounts
2. Check: inbox vs spam vs promotions vs missing entirely
3. If any provider shows spam → diagnose before sending to real prospects
4. Check all links work, tracking fires, unsubscribe works
5. Check mobile rendering

---

## Domain Strategy — How Many & Where {#domain-strategy}

### How Many Domains You Need

A fully warmed domain (60 days) can safely send 150-200 cold emails per day.

| Daily Email Goal | Domains Needed |
|-----------------|---------------|
| 500/day | 3-4 domains |
| 1,000/day | 6-7 domains |
| 2,500/day | 15-17 domains |
| 5,000/day | 30-35 domains |
| 10,000/day | 60-70 domains |

**Recommended starting point:** 5-10 domains = 750-2,000 emails/day

### Domain Naming Strategy

Never send cold outreach from your main business domain. Use branded variations:

**Good examples (for ChampMail):**
- `getchampionsmail.com`
- `champmail.io`
- `trychampmail.com`
- `champmailhq.com`
- `championsoutreach.com`
- `hellochampmail.com`

### Always Use Subdomains for Sending

- Buy: `getchampionsmail.com`
- Send from: `mail.getchampionsmail.com`

If the sending subdomain gets in trouble, the root domain is unaffected.

### Domain Extensions by Trust Level

| Extension | Trust | Recommendation |
|-----------|-------|----------------|
| .com | Highest | Primary choice |
| .io | High | Good for tech |
| .co | Medium-High | Acceptable |
| .net | Medium | Fallback only |
| .info / .biz | Low | Avoid |
| .xyz / .top | Very Low | Never use |

### Where to Buy

- **Namecheap** — cheapest bulk buying, API already integrated in ChampMail
- **Cloudflare Registrar** — at-cost pricing (~$8.57/year), DNS already integrated
- **Avoid:** GoDaddy (expensive, known to suspend email domains)

### Domain Lifecycle

- Domains are consumables — not permanent assets
- Rotate every 12-18 months
- Always keep a pipeline of 5 domains warming (60-day process)
- At $10/year per domain, rotation costs $0.56/month per domain

### The Starter Pack — Buy These Today

Buying them today starts their age clock. Older domains get more trust.

1. `getchampionsmail.com`
2. `champmail.io`
3. `trychampmail.com`
4. `championsoutreach.com`
5. `hellochampmail.com`

Start warmup on all 5 immediately. By day 60 all are ready: 750-1,000 emails/day minimum.

---

## Cloudflare DNS — Exact Setup Per Domain {#cloudflare-setup}

### The 6 Records Every Sending Domain Needs

For each domain (example: `getchampionsmail.com`):

```
TYPE    NAME                           VALUE                               PROXY
────────────────────────────────────────────────────────────────────────────────
A       @                              <VPS_IP>                            ON
A       mail                           <VPS_IP>                            OFF ← must be grey
MX      @                    (pri 10)  mail.getchampionsmail.com            —
TXT     @                              v=spf1 ip4:<VPS_IP> -all            —
TXT     champmail._domainkey           v=DKIM1; k=rsa; p=<public key>     —
TXT     _dmarc                         v=DMARC1; p=none; rua=mailto:...   —
```

### Critical Rules

- **Mail A record MUST have proxy OFF (grey cloud)** — orange cloud breaks email authentication
- **Only one SPF TXT record per domain** — two SPF records = SPF breaks completely
- **DKIM value must be one continuous string** — no line breaks in the key
- **MX record is required** — without it bounces have nowhere to go

### Propagation Verification

After creating records, verify with:
```bash
dig TXT champmail._domainkey.getchampionsmail.com
dig TXT getchampionsmail.com
dig MX getchampionsmail.com
```

Or check at: `dnschecker.org`

### PTR Record (Reverse DNS)

Set in your VPS control panel (not Cloudflare):
```
<VPS_IP>  →  mail.championsmail.com   (pick your primary domain)
```

One PTR per IP. Use your main/primary domain. All other domains still work — PTR only affects the SMTP handshake greeting.

### Per-Domain Setup Checklist

```
□ A record: mail.yourdomain.com → VPS IP (proxy OFF)
□ A record: @ → VPS IP (proxy ON — for web)
□ MX record: @ → mail.yourdomain.com (priority 10)
□ TXT record: @ → v=spf1 ip4:<VPS IP> -all
□ TXT record: champmail._domainkey → v=DKIM1; k=rsa; p=<public key>
□ TXT record: _dmarc → v=DMARC1; p=none; rua=mailto:dmarc@yourdomain.com
□ Verify propagation
□ Register at Google Postmaster Tools
□ Register IP at Microsoft SNDS
□ Enable warmup in ChampMail for this domain
```

---

## OpenDKIM — Why It's Non-Negotiable {#opendkim}

### The Three Guarantees OpenDKIM Provides

**Identity** — Proves the email genuinely came from your authorized server, not someone forging your domain.

**Integrity** — Proves nobody tampered with the email content between your server and Gmail. The signature covers subject, body, and key headers.

**Forwarding** — Unlike SPF (which breaks when emails are forwarded through different servers), DKIM signatures are embedded in the email itself and survive every forward and relay.

### Without vs With OpenDKIM

**Without OpenDKIM:**
- SPF: ✅ Pass
- DKIM: ❌ No signature — FAIL/NONE
- DMARC: ⚠️ Passes via SPF only (weak — breaks on forwarding)
- Cannot safely use DMARC p=reject
- Inbox placement: ~65-75%

**With OpenDKIM:**
- SPF: ✅ Pass
- DKIM: ✅ Signed and verified
- DMARC: ✅ Both aligned (strong)
- Can use DMARC p=reject after 8 weeks
- Inbox placement: ~92-97%

### The Gap in Numbers

On 1,000 emails/day:
- Without DKIM: ~700 reach inbox
- With DKIM: ~950 reach inbox
- **250 extra emails reaching real people every single day**

### How the Signing Works

```
Email exits app
      ↓
Postfix receives it
      ↓
Postfix calls OpenDKIM on port 8891
      ↓
OpenDKIM looks up From domain in SigningTable
      ↓
Loads correct private key from KeyTable
      ↓
Calculates HMAC-SHA256 signature over headers + body
      ↓
Adds DKIM-Signature header to email
      ↓
Returns signed email to Postfix
      ↓
Postfix delivers to Gmail
      ↓
Gmail fetches public key from Cloudflare DNS
      ↓
Gmail verifies signature mathematically
      ↓
✅ DKIM PASS
```

### Dynamic Multi-Domain Configuration

ChampMail supports many domains. OpenDKIM handles this via two files:

**KeyTable** (`/etc/opendkim/KeyTable`):
```
champmail._domainkey.domain1.com   domain1.com:champmail:/keys/domain1.private
champmail._domainkey.domain2.com   domain2.com:champmail:/keys/domain2.private
```

**SigningTable** (`/etc/opendkim/SigningTable`):
```
*@domain1.com    champmail._domainkey.domain1.com
*@domain2.com    champmail._domainkey.domain2.com
```

**When a new domain is added in ChampMail, the app must:**
1. Generate RSA keypair → store in DB (already done in `provision_new_domain`)
2. Write new entry to KeyTable file
3. Write new entry to SigningTable file
4. Send HUP signal to OpenDKIM: `kill -HUP $(cat /run/opendkim/opendkim.pid)`
5. Add public key to Cloudflare DNS (already done via `cloudflare_client`)

---

## Final Architecture — Complete Picture {#final-architecture}

### The Complete VPS Architecture

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                          YOUR VPS (Single Dedicated IP)                         ║
║                                                                                  ║
║  ┌─────────────────────────────────────────────────────────────────────────┐    ║
║  │                         INCOMING LAYER                                  │    ║
║  │   Port 25  ──── Bounces/DSNs from Gmail, Outlook arriving back          │    ║
║  │   Port 587 ──── Authenticated submission from your app                  │    ║
║  │   Port 443 ──── HTTPS for tracking (open pixels, click links)           │    ║
║  │   Port 80  ──── Certbot TLS certificate renewal (Let's Encrypt)         │    ║
║  └─────────────────────────────────────────────────────────────────────────┘    ║
║                                    │                                             ║
║                                    ▼                                             ║
║  ┌──────────────────────────── MAIL LAYER ─────────────────────────────────┐    ║
║  │                                                                          │    ║
║  │   ┌─────────────┐     signs every      ┌──────────────────────────────┐ │    ║
║  │   │  OpenDKIM   │ ◄── outgoing email ── │         POSTFIX              │ │    ║
║  │   │  (milter)   │ ── signed email  ───► │      (Mail Transfer Agent)   │ │    ║
║  │   │  port 8891  │                       │                              │ │    ║
║  │   │             │   one key per domain  │  • Direct delivery (no relay)│ │    ║
║  │   │ KeyTable    │                       │  • Let's Encrypt TLS cert    │ │    ║
║  │   │ domain1.com │                       │  • header_checks active      │ │    ║
║  │   │ domain2.com │                       │  • closed relay              │ │    ║
║  │   │    ...      │                       │  • rate limiting per dest    │ │    ║
║  │   └─────────────┘                       └──────────────┬───────────────┘ │    ║
║  │                                                        │                  │    ║
║  │   ┌────────────────────┐              outbound emails  │  inbound DSNs    │    ║
║  │   │     Certbot        │              to Gmail/Outlook │  (bounces)       │    ║
║  │   │  Let's Encrypt     │              Yahoo etc.       │                  │    ║
║  │   │  auto-renewal      │                               ▼                  │    ║
║  │   └────────────────────┘               ┌───────────────────────────────┐ │    ║
║  │                                        │    Bounce Processor           │ │    ║
║  │                                        │  • parses RFC 3464 DSNs       │ │    ║
║  │                                        │  • extracts prospect ID (VERP)│ │    ║
║  │                                        │  • fires Celery bounce task   │ │    ║
║  │                                        └───────────────────────────────┘ │    ║
║  └──────────────────────────────────────────────────────────────────────────┘    ║
║                                          │                                        ║
║                                          ▼                                        ║
║  ┌──────────────────────────── APPLICATION LAYER ───────────────────────────┐   ║
║  │                                                                            │   ║
║  │  ┌─────────────────────────────────────────────────────────────────────┐  │   ║
║  │  │                   FastAPI Backend  (port 8000)                       │  │   ║
║  │  │  /api/v1/campaigns  /api/v1/domains    /api/v1/analytics             │  │   ║
║  │  │  /api/v1/sequences  /api/v1/prospects  /api/v1/email-accounts        │  │   ║
║  │  │  /track/open/{id}   /track/click/{id}  /unsubscribe/{id}             │  │   ║
║  │  └─────────────────────────────────────────────────────────────────────┘  │   ║
║  │                                    │                                        │   ║
║  │              ┌─────────────────────┼──────────────────────┐                │   ║
║  │              ▼                     ▼                       ▼                │   ║
║  │  ┌───────────────────┐  ┌──────────────────┐  ┌────────────────────────┐  │   ║
║  │  │   Celery Worker   │  │   Celery Beat    │  │    Mail Engine (Go)    │  │   ║
║  │  │                   │  │                  │  │    port 8025           │  │   ║
║  │  │ • send_email      │  │ Every 5 min:     │  │                        │  │   ║
║  │  │ • send_batch      │  │ • sequences      │  │  • SMTP client         │  │   ║
║  │  │ • AI pipeline     │  │ • imap check     │  │  • Batch sending       │  │   ║
║  │  │ • warmup sends    │  │                  │  │  • DKIM key generation │  │   ║
║  │  │ • bounce process  │  │ Every 10 min:    │  └────────────────────────┘  │   ║
║  │  │ • DMARC parse     │  │ • bounce queue   │                               │   ║
║  │  │ • blacklist check │  │                  │                               │   ║
║  │  │ • domain health   │  │ Every 6 hours:   │                               │   ║
║  │  └───────────────────┘  │ • domain health  │                               │   ║
║  │                          │ • blacklist check│                               │   ║
║  │                          │                  │                               │   ║
║  │                          │ Daily 9am UTC:   │                               │   ║
║  │                          │ • warmup sends   │                               │   ║
║  │                          │                  │                               │   ║
║  │                          │ Daily midnight:  │                               │   ║
║  │                          │ • reset sent_today│                              │   ║
║  │                          │ • advance warmup │                               │   ║
║  │                          │   day counters   │                               │   ║
║  │                          │                  │                               │   ║
║  │                          │ Daily 11:55pm:   │                               │   ║
║  │                          │ • daily stats    │                               │   ║
║  │                          └──────────────────┘                               │   ║
║  └────────────────────────────────────────────────────────────────────────────┘   ║
║                                         │                                          ║
║                                         ▼                                          ║
║  ┌───────────────────────────── DATA LAYER ────────────────────────────────────┐  ║
║  │                                                                              │  ║
║  │   ┌─────────────────────────┐          ┌────────────────────────────────┐   │  ║
║  │   │     PostgreSQL 16       │          │          Redis 7               │   │  ║
║  │   │                         │          │                                │   │  ║
║  │   │  • users / teams        │          │  • pipeline:{id}:status        │   │  ║
║  │   │  • domains              │          │  • campaign:{id}:schedule      │   │  ║
║  │   │    - warmup_day         │          │  • research:prospect:{id}      │   │  ║
║  │   │    - warmup_enabled     │          │  • domain:blacklist:{id}       │   │  ║
║  │   │    - sent_today         │          │  • rate_limit:{user_id}        │   │  ║
║  │   │    - health_score       │          │                                │   │  ║
║  │   │    - bounce_rate        │          │  Celery broker (DB 0)          │   │  ║
║  │   │    - complaint_rate     │          │  Celery results (DB 1)         │   │  ║
║  │   │    - blacklisted        │          └────────────────────────────────┘   │  ║
║  │   │    - blacklist_hits     │                                                │  ║
║  │   │    - dkim_private_key   │                                                │  ║
║  │   │    - dkim_public_key    │                                                │  ║
║  │   │  • campaigns            │                                                │  ║
║  │   │  • prospects            │                                                │  ║
║  │   │  • suppression_list     │                                                │  ║
║  │   │  • send_logs            │                                                │  ║
║  │   │  • daily_stats          │                                                │  ║
║  │   └─────────────────────────┘                                                │  ║
║  └──────────────────────────────────────────────────────────────────────────────┘  ║
║                                                                                    ║
║  ┌───────────────────────────── MONITORING LAYER ──────────────────────────────┐  ║
║  │                                                                              │  ║
║  │   ┌──────────────────┐   ┌──────────────────┐   ┌────────────────────────┐  │  ║
║  │   │  Flower          │   │  DMARC Processor │   │   Blacklist Monitor    │  │  ║
║  │   │  port 5555       │   │  (parsedmarc)    │   │   (DNS-based)          │  │  ║
║  │   │  Celery metrics  │   │  XML → DB        │   │   Every 6 hours        │  │  ║
║  │   │  queue depths    │   │  Alert on spikes │   │   Auto-pause if listed │  │  ║
║  │   └──────────────────┘   └──────────────────┘   └────────────────────────┘  │  ║
║  └──────────────────────────────────────────────────────────────────────────────┘  ║
╚══════════════════════════════════════════════════════════════════════════════════╝
```

### External Connections

```
YOUR VPS
    │
    ├──► Cloudflare DNS API
    │    Creates: A, MX, SPF, DKIM, DMARC records per domain
    │    Automated on domain provisioning
    │
    ├──► Namecheap API
    │    Purchases domains on demand
    │    Already integrated in ChampMail
    │
    ├──► Google Postmaster Tools
    │    Monitors: domain rep, IP rep, spam rate, auth rates
    │    Check daily
    │
    ├──► Microsoft SNDS & JMRP
    │    Monitors: IP status, complaint rate, trap hits
    │    Receives individual spam complaint emails
    │
    ├──► Spamhaus / Barracuda / SpamCop / SORBS
    │    DNS-based blacklist checks every 6 hours
    │    Auto-pause domain if listed
    │
    ├──► Gmail / Outlook / Yahoo
    │    Direct SMTP delivery — no relay
    │    Receive bounce DSNs back on port 25
    │
    └──► ChampGraph
         Prospect research & AI data
         Already integrated
```

### The Complete Journey of One Email

```
1. CAMPAIGN SCHEDULER (Celery Beat)
   └── Is it business hours in prospect's timezone? (Tue-Thu 10am-2pm ideal)
   └── Has this domain hit its warmup daily limit?
   └── Is the domain blacklisted or paused?
   └── Is bounce_rate < 2% and complaint_rate < 0.08%?
   └── Apply jitter: cadence ± 30% randomization
   └── Queue: send_email_task with ETA

2. CELERY WORKER picks up the task
   └── Validate email format
   └── Check MX record exists for recipient domain
   └── Check not a role address (info@, admin@, noreply@)
   └── Check not on suppression list
   └── Select domain (warmup-gated DomainRotator)
   └── Generate HMAC-signed tracking URLs
   └── Build multipart/alternative email (text/plain + text/html)
   └── Inject tracking pixel into HTML
   └── Wrap all links with click tracking
   └── Add required headers:
       ├── Message-ID: <uuid@mail.yourdomain.com>
       ├── List-Unsubscribe: <mailto:...>, <https://...>
       └── List-Unsubscribe-Post: List-Unsubscribe=One-Click

3. EMAIL SUBMITTED to Postfix (port 587)
   └── Postfix calls OpenDKIM milter (port 8891)

4. OPENDKIM signs the email
   └── Looks up From domain in SigningTable
   └── Loads corresponding private key
   └── Calculates signature over headers + body
   └── Adds DKIM-Signature header

5. POSTFIX delivers the email
   └── Strips internal IP headers (header_checks)
   └── Looks up MX record for recipient domain
   └── Opens TLS-encrypted SMTP connection
   └── EHLO: identifies as mail.yourdomain.com
   └── Delivers directly to Gmail/Outlook/Yahoo

6. RECEIVING SERVER checks
   └── PTR: does mail.yourdomain.com match the connecting IP? ✅
   └── SPF: is this IP in yourdomain.com SPF record? ✅
   └── DKIM: fetches public key from Cloudflare, verifies signature ✅
   └── DMARC: both SPF and DKIM aligned ✅
   └── Content: multipart, List-Unsubscribe present ✅
   └── Reputation: domain High, IP clean ✅
   └── RESULT: Delivered to INBOX

7. PROSPECT OPENS the email
   └── Tracking pixel fires → backend records open event
   └── Campaign stats updated in PostgreSQL

8. PROSPECT CLICKS a link
   └── Goes to track.yourdomain.com/click/{id}
   └── Backend records click, redirects to real URL

9. IF EMAIL BOUNCES
   └── Gmail sends DSN to bounce+{prospect_id}@mail.yourdomain.com
   └── Postfix pipe delivers DSN to bounce_handler.py
   └── Parser extracts prospect ID from VERP tag
   └── Celery: add to suppression list, update bounce_rate
   └── If domain bounce_rate > 2%: auto-pause domain, alert admin

10. EVERY 6 HOURS (Celery Beat)
    └── Blacklist check all sending IPs and domains
    └── DNS verification: SPF, DKIM, DMARC still valid?
    └── Recalculate health_score per domain
    └── If blacklisted: pause domain, send admin alert

11. DAILY AT MIDNIGHT (Celery Beat)
    └── Reset sent_today = 0 for all domains
    └── Advance warmup_day + 1 for all warming domains
    └── Graduate domains at warmup_day >= 60 (disable warmup)
```

### Docker Container Stack

```
┌──────────────────────────────────────────────────────────────┐
│  Container           Port      Purpose                        │
├──────────────────────────────────────────────────────────────┤
│  postgres            5432      All persistent data            │
│  redis               6380      Celery broker + cache          │
│  postfix             25/587    Mail Transfer Agent            │
│  opendkim            8891      DKIM signing milter  [NEW]     │
│  certbot             —         TLS cert auto-renewal [NEW]    │
│  bounce-processor    —         Inbound DSN handler  [NEW]     │
│  mail-engine         8025      Go SMTP client + batch         │
│  backend             8000      FastAPI + all API routes       │
│  worker              —         Celery task execution          │
│  beat                —         Celery scheduled tasks         │
│  flower              5555      Celery monitoring              │
│  frontend            3000      React + Nginx                  │
│  mailhog             8026      Dev SMTP (local only)          │
└──────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases {#implementation-phases}

### Phase 0 — Architecture Seams (Week 0) ✅ COMPLETE
**Goal:** Fix broken foundations before adding new tiers on top

```
✅ Deleted mail_engine_client.py (dead code — never called)
✅ Deleted email_provider.py (abandoned abstraction)
✅ Fixed SSL cert verification (disabled only for local relays)
✅ Wired warmup enforcement into DomainRotator
✅ Wired ip_blacklist.py into check_all_domain_health task
✅ Applied health_penalty to domain.health_score
✅ Fixed graduation day from 30 → 60
✅ Added midnight_reset Celery task (resets sent_today, advances warmup_day)
✅ Added complaint_rate, blacklisted, blacklist_hits, paused to Domain model
✅ Unified mail path: Python → Postfix → Internet (removed TurboSMTP)
✅ Added email_validator.py (format, MX, role address, suppression list)
✅ Added suppression_service.py + suppression_list table
✅ Added VERP bounce envelope to all outbound emails
✅ Rewrote tasks/sending.py to use local Postfix directly
✅ Rewrote tasks/bounces.py for native VERP bounce processing
✅ Added bounce_handler.py Postfix pipe script
✅ Added tasks/dmarc.py DMARC report parser
✅ Added seed_tester.py pre-campaign inbox placement checker
✅ Added ±30% jitter to campaign send cadence
✅ Added 14 new config variables (VPS_PUBLIC_IP, MAIL_HOSTNAME, etc.)
```

### Phase 1 — Foundation (Week 1-2)
**Goal:** Legitimate mail server that passes basic infrastructure checks

```
□ Set PTR record on VPS IP (VPS control panel)
□ Rewrite Postfix Dockerfile:
  □ Remove TurboSMTP smarthost relay
  □ Set relay_domains = (close open relay)
  □ Fix myhostname to match PTR
  □ Fix smtpd_tls_auth_only = yes
  □ Add header_checks to strip internal IPs
  □ Add smtp_tls_protocols to reject old TLS
□ Install Certbot container
□ Get Let's Encrypt cert for mail.yourdomain.com
□ Mount real cert into Postfix (replace self-signed)
□ Buy 5 sending domains (Namecheap)
□ Point DNS to Cloudflare for all domains
□ Create 5 DNS records per domain (A, MX, SPF, DMARC, root A)
□ Register all domains at Google Postmaster Tools
□ Register VPS IP at Microsoft SNDS
□ Enable warmup in ChampMail for all domains
```

### Phase 2 — Authentication (Week 2-3)
**Goal:** Full SPF + DKIM + DMARC — cryptographically verified sender

```
□ Build OpenDKIM Docker container
□ Wire OpenDKIM into Postfix (milter config)
□ Implement dynamic KeyTable/SigningTable management in ChampMail
□ Generate DKIM keypairs for all domains
□ Add DKIM TXT records to Cloudflare for all domains
□ Verify DKIM signing works (check email headers)
□ Implement bounce reception (port 25 + pipe handler)
□ Test full authentication: SPF + DKIM + DMARC all passing
```

### Phase 3 — Intelligence (Week 3-8)
**Goal:** Self-monitoring, self-healing email engine

```
□ Fix DomainRotator to enforce warmup limits
□ Implement warmup_schedule.py module
□ Add midnight Celery task (reset sent_today, advance warmup_day)
□ Implement ip_blacklist.py DNS checker
□ Add blacklist checking to domain health task
□ Add complaint_rate, blacklisted columns to Domain model
□ Add bounce/complaint threshold auto-pause logic
□ Implement DMARC report parser (parsedmarc)
□ Add ±30% jitter to campaign cadence
□ Build seed inbox network (5+ accounts across providers)
□ Escalate DMARC to p=quarantine (week 5-6)
□ Escalate DMARC to p=reject (month 3)
□ Buy 5 more domains (keep pipeline full)
```

---

## Before vs After {#before-vs-after}

| Component | Before | After |
|-----------|--------|-------|
| Email routing | TurboSMTP smarthost relay | Direct delivery from VPS |
| TLS certificate | Self-signed fake cert | Let's Encrypt — globally trusted |
| DKIM signing | None — emails unsigned | OpenDKIM — every email cryptographically signed |
| Relay security | Open relay (`relay_domains=*`) | Closed — your containers only |
| Bounce handling | Webhook from TurboSMTP | Native SMTP inbound, VERP parsing |
| Warmup enforcement | Not enforced in DomainRotator | Enforced at every send decision |
| Warmup schedule | 8 days, max 1,000/day | 60 days, max 15,000/day |
| Daily counter reset | Never resets | Midnight Celery task |
| Blacklist monitoring | None | Every 6 hours, auto-pause if listed |
| DMARC reports | Not processed | Parsed, stored, alerted |
| Sending pattern | Mechanical exact intervals | Human-pattern with ±30% jitter |
| Domain health gate | None | Bounce + complaint rate auto-pause |
| Header cleanup | Internal Docker IPs exposed | Stripped via header_checks |
| DMARC policy | p=none (monitoring only) | p=reject (full enforcement) |
| Inbox placement | ~40-60% | ~92-97% |

---

## Cost Breakdown {#cost-breakdown}

### Annual Infrastructure Cost

| Item | Qty | Cost/Year |
|------|-----|-----------|
| .com sending domains (active) | 10 | ~$100 |
| .com sending domains (warming pipeline) | 5 | ~$50 |
| VPS — Hetzner (4 core, 8GB RAM) | 1 | ~$150 |
| Cloudflare DNS (free plan) | — | $0 |
| Let's Encrypt TLS certificates | — | $0 |
| Google Postmaster Tools | — | $0 |
| Microsoft SNDS & JMRP | — | $0 |
| Spamhaus / blacklist DNS checks | — | $0 |
| GlockApps (inbox placement + DMARC) | 1 | ~$108–$708 |
| **Total** | | **~$408–$1,008/year** |

### Compared to Third-Party Services

| Service | Cost/Year | Emails/Month | Self-Hosted Equivalent |
|---------|-----------|-------------|----------------------|
| Instantly.ai | $1,164 | 5,000 | 150,000+ |
| Lemlist | $1,188 | 5,000 | 150,000+ |
| Apollo.io | $1,788 | varies | 150,000+ |
| **Self-hosted** | **$300** | **unlimited** | — |

**You own the infrastructure. No per-email fees. No monthly caps. No vendor dependency.**

---

## Quick Reference — Key Numbers

| Metric | Safe Zone | Warning | Action Required |
|--------|-----------|---------|----------------|
| Spam complaint rate | < 0.08% | 0.08-0.3% | > 0.3% → pause domain |
| Hard bounce rate | < 2% | 2-5% | > 5% → pause domain |
| Domain reputation | High | Medium | Low → diagnose immediately |
| DKIM pass rate | > 99% | 95-99% | < 95% → check OpenDKIM |
| SPF pass rate | > 99% | 95-99% | < 95% → check SPF record |
| Emails/domain/day (warmed) | 150-200 | 200-400 | > 400 → high risk |
| Warmup graduation day | 60 | — | — |
| DMARC escalation week | p=none wk1-4, p=quarantine wk5-8, p=reject month 3+ | — | — |

---

*Last updated: May 2026*
*Branch: CLI-ChampMail*
