# ChampMail — Security Guardrail & Custom Domain Email Plan

> Audit date: 2026-04-22  
> Audited by: Claude Code  
> Status: **Action required before any production use**

---

## Table of Contents

1. [Audit Findings Summary](#1-audit-findings-summary)
2. [Critical Fixes — Do These Now](#2-critical-fixes--do-these-now)
3. [High Priority Fixes](#3-high-priority-fixes)
4. [Medium Priority Fixes](#4-medium-priority-fixes)
5. [Custom Domain Email — Complete Setup Guide](#5-custom-domain-email--complete-setup-guide)
6. [Ongoing Guardrails & Monitoring](#6-ongoing-guardrails--monitoring)

---

## 1. Audit Findings Summary

### What ChampMail Does (Architecture)

```
Internet
  │
  ├── :3001  → Frontend (Nginx + React)
  ├── :8000  → Backend (FastAPI/Python) ← main brain
  ├── :8025  → Mail Engine (Go/GIN)     ← stub, no real SMTP
  ├── :8026  → MailHog web UI           ← test tool, NO AUTH
  ├── :5432  → PostgreSQL               ← PUBLIC, NO FIREWALL
  ├── :6380  → Redis                    ← PUBLIC, NO FIREWALL
  ├── :8081  → ChampGraph               ← PUBLIC, NO AUTH
  ├── :25    → Postfix SMTP             ← open relay risk
  ├── :465   → Postfix SMTPS            ← open relay risk
  └── :587   → Postfix Submission       ← open relay risk

Backend internally calls:
  ├── email_service.py  → real SMTP (correct, was just fixed)
  └── mail_engine_client.py → Go stub (Celery tasks still use this — BROKEN)
```

### Severity Matrix

| # | Issue | Severity | File / Location |
|---|-------|----------|-----------------|
| 1 | SSL cert verification disabled (`CERT_NONE`) | 🔴 CRITICAL | `email_service.py:308-309` |
| 2 | PostgreSQL port 5432 publicly exposed, no firewall | 🔴 CRITICAL | `docker-compose.yml:28-29` |
| 3 | Redis port 6380 publicly exposed, no firewall | 🔴 CRITICAL | `docker-compose.yml:34` |
| 4 | MailHog SMTP port 1025 open — anyone can relay spam | 🔴 CRITICAL | `docker-compose.yml` |
| 5 | Postfix is an open relay on public ports 25/465/587 | 🔴 CRITICAL | `mail-engine/postfix/Dockerfile` |
| 6 | Celery sending tasks use Go stub, emails never sent | 🔴 CRITICAL | `tasks/sending.py`, `tasks/sequences.py` |
| 7 | `/health/db-schema` endpoint — no auth, exposes schema | 🔴 CRITICAL | `api/v1/health.py:119` |
| 8 | MailHog web UI on port 8026 — no auth, captures emails | 🟠 HIGH | `docker-compose.yml` |
| 9 | Rate limiter uses in-memory storage, not Redis | 🟠 HIGH | `middleware/rate_limit.py:31` |
| 10 | No brute-force protection on `/auth/login` | 🟠 HIGH | `api/v1/auth.py:76` |
| 11 | JWT expires in 24 hours — too long | 🟠 HIGH | `core/config.py:59` |
| 12 | Dev credentials hardcoded in API docs | 🟠 HIGH | `main.py:113-115` |
| 13 | `DEBUG=true` leaks stack traces to clients | 🟠 HIGH | `.env:4` |
| 14 | No per-user daily email send quota | 🟠 HIGH | `api/v1/send.py` |
| 15 | Mail engine Go API has no authentication | 🟠 HIGH | `mail-engine/internal/api/router.go` |
| 16 | ChampGraph API exposed publicly on :8081 | 🟡 MEDIUM | `docker-compose.yml` |
| 17 | `.env` contains live API keys and passwords | 🟡 MEDIUM | `.env` |
| 18 | No unsubscribe enforcement at send time | 🟡 MEDIUM | `api/v1/send.py` |
| 19 | No custom domain email setup guide in UI | 🟡 MEDIUM | missing feature |
| 20 | Postfix relay env var naming mismatch | 🟡 MEDIUM | `docker-compose.override.yml` |

---

## 2. Critical Fixes — Do These Now

### Fix 1 — Re-enable SSL Certificate Verification

**File:** `backend/app/services/email_service.py` lines 307-309

**Problem:** During TLS debugging, `CERT_NONE` was set. This disables all certificate validation — any server with a fake certificate can intercept email credentials (Man-in-the-Middle attack).

**Fix:**
```python
# REPLACE this:
context = ssl.create_default_context()
context.check_hostname = False
context.verify_mode = ssl.CERT_NONE

# WITH this:
context = ssl.create_default_context()
# check_hostname and verify_mode stay at secure defaults (True / CERT_REQUIRED)
```

Only disable for local relay (MailHog) where no TLS is used at all:
```python
is_local_relay = not config.username

if is_local_relay:
    server = smtplib.SMTP(config.host, config.port, timeout=30)
    server.ehlo()
elif config.use_tls:
    context = ssl.create_default_context()   # secure defaults, no override
    server = smtplib.SMTP(config.host, config.port, timeout=30)
    server.ehlo()
    server.starttls(context=context)
    server.ehlo()
else:
    context = ssl.create_default_context()   # secure defaults
    server = smtplib.SMTP_SSL(config.host, config.port, context=context, timeout=30)
```

---

### Fix 2 — Block Database Ports from the Public Internet

**Problem:** PostgreSQL (:5432) and Redis (:6380) are bound to `0.0.0.0` — anyone on the internet can attempt to connect.

**Fix in `docker-compose.yml`:** Change public bindings to localhost-only:

```yaml
# PostgreSQL — was: "0.0.0.0:5432:5432"
postgres:
  ports:
    - "127.0.0.1:5432:5432"   # localhost only — no external access

# Redis — was: "0.0.0.0:6380:6379"
redis:
  ports:
    - "127.0.0.1:6380:6379"   # localhost only
```

**Also add OS-level firewall rules:**
```bash
# Block 5432 and 6380 at the OS level as a second layer
ufw deny 5432
ufw deny 6380
ufw deny 8026   # MailHog web UI
ufw deny 8081   # ChampGraph
ufw deny 1025   # MailHog SMTP
```

---

### Fix 3 — Restrict MailHog to Localhost Only

**Problem:** MailHog's SMTP port 1025 is bound to `0.0.0.0` — anyone can use your server as a spam relay through it. Port 8026 (web UI) exposes captured emails (which may contain real credentials) to the public internet.

**Fix in `docker-compose.yml`:**
```yaml
mailhog:
  ports:
    - "127.0.0.1:1025:1025"   # SMTP — internal only
    - "127.0.0.1:8026:8025"   # Web UI — localhost only (access via SSH tunnel)
```

**Note:** MailHog is a dev/test tool. Remove it entirely before real production use. For production, any email sent via the test account should be tested against MailHog locally only.

---

### Fix 4 — Secure the Postfix Container (Stop Open Relay)

**Problem:** Postfix is running with `relay_domains = *` on public ports 25/465/587. Any server on the internet can connect and route mail through your Postfix instance.

**Fix `mail-engine/postfix/Dockerfile`:**
```dockerfile
# Change relay_domains — only relay for internal Docker network
RUN postconf -e "relay_domains =" && \
    postconf -e "mynetworks = 127.0.0.0/8 172.16.0.0/12 10.0.0.0/8" && \
    postconf -e "smtpd_relay_restrictions = permit_mynetworks reject"
```

**Also restrict public port exposure in `docker-compose.yml`:**
```yaml
smtp:
  ports:
    - "127.0.0.1:587:587"   # submission — local only
    # Remove 25 and 465 entirely unless you need inbound mail
```

---

### Fix 5 — Fix Celery Tasks to Actually Send Emails

**Problem:** `tasks/sending.py` and `tasks/sequences.py` both call `mail_engine_client.send_email()` which routes to the Go engine stub. The Go stub marks emails as "sent" in the database without making any SMTP connection. Every scheduled sequence email and every campaign batch email has been silently failing.

**Fix `backend/app/tasks/sending.py`** — replace `mail_engine_client.send_email()` with `email_service.send_email()`:

```python
# In send_email_task and send_batch_task:
# REMOVE: from app.services.mail_engine_client import mail_engine_client
# ADD:
from app.services.email_service import email_service

# In _send() inside send_email_task:
result = await email_service.send_email(
    session=session,
    user_id=step.get("user_id"),   # must be passed through from campaign
    to_email=prospect.get("email"),
    subject=subject,
    body="",                        # plain text fallback
    html_body=final_html,
    campaign_id=campaign_id,
    prospect_id=prospect_id,
)
if not result.get("success"):
    raise ValueError(result.get("error"))
```

**Same fix needed in `tasks/sequences.py`** — the `execute_pending_steps` task.

**Critical:** The sequence steps need to carry `user_id` so `email_service` can look up the correct email account. Check that `sequence_service.get_pending_steps()` returns `user_id` in each step. If not, add it to the query.

---

### Fix 6 — Remove `/health/db-schema` or Add Auth

**File:** `backend/app/api/v1/health.py` line 119

**Problem:** This endpoint returns every table name in your database with zero authentication. Attackers use schema info to craft targeted SQL injection and enumeration attacks.

**Quick fix — add auth:**
```python
@router.get("/db-schema")
async def db_schema_check(user: TokenData = Depends(require_admin)):
    # existing code ...
```

**Better fix — remove it entirely.** You can get schema info via `docker exec champmail-postgres psql ...`. No need to expose it over HTTP.

---

## 3. High Priority Fixes

### Fix 7 — Rate Limiter Must Use Redis, Not Memory

**File:** `backend/app/middleware/rate_limit.py` line 31

**Problem:** `storage_uri="memory://"` means each Gunicorn/Uvicorn worker has its own counter. With 4 workers, the effective limit is 400 req/min per user, not 100. Also resets on every restart.

**Fix:**
```python
from app.core.config import settings

limiter = Limiter(
    key_func=_get_user_key,
    default_limits=["100/minute"],
    storage_uri=settings.redis_url,   # shared across all workers
)
```

---

### Fix 8 — Login Brute Force Protection

**File:** `backend/app/api/v1/auth.py` line 76

**Problem:** No login-specific rate limit. The global 100 req/min applies to all endpoints, but login should be much stricter.

**Fix — add a decorator to the login endpoint:**
```python
from app.middleware.rate_limit import limiter

@router.post("/login", response_model=Token)
@limiter.limit("5/minute")           # 5 attempts per minute per IP
async def login(request: Request, form_data: ..., session: ...):
```

Also add account lockout after 10 failed attempts (store in Redis with TTL).

---

### Fix 9 — Shorten JWT Token Expiry

**File:** `backend/app/core/config.py` line 59

**Problem:** `jwt_access_token_expire_minutes: int = 1440` — tokens last 24 hours. If a token is stolen, the attacker has 24 hours of access.

**Fix:**
```python
jwt_access_token_expire_minutes: int = 60    # 1 hour
jwt_refresh_token_expire_days: int = 30      # add refresh token flow
```

Implement a refresh token endpoint (already exists at `/auth/refresh` but without a separate long-lived refresh token).

---

### Fix 10 — Remove Dev Credentials from API Docs

**File:** `backend/app/main.py` lines 113-115

**Problem:**
```python
    Development credentials:
    - Admin: `admin@champions.dev` / `admin123`
```

This appears in the public `/docs` page.

**Fix:**
```python
    ## Authentication
    Use `/api/v1/auth/login` to get a JWT token.
    Include it in requests as: `Authorization: Bearer <token>`
    # Remove all credential hints
```

**Also:** Change the actual admin password from `admin` (found during this audit) to something strong.

---

### Fix 11 — Per-User Daily Send Quota

**File:** `backend/app/api/v1/send.py`

**Problem:** No limit on how many emails a single user can send per day. A compromised account can send millions.

**Fix — add a Redis-backed counter in `send.py`:**
```python
import datetime
from app.db.redis import redis_client

DAILY_SEND_LIMIT = 500   # per user per day, make configurable

async def check_send_quota(user_id: str) -> bool:
    today = datetime.date.today().isoformat()
    key = f"send_quota:{user_id}:{today}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, 86400)  # expire after 24h
    return count <= DAILY_SEND_LIMIT

# In send_email endpoint:
if not await check_send_quota(str(user.user_id)):
    raise HTTPException(
        status_code=429,
        detail=f"Daily send limit of {DAILY_SEND_LIMIT} emails reached"
    )
```

---

### Fix 12 — Authenticate the Go Mail Engine API

**File:** `mail-engine/internal/api/router.go` and `handlers.go`

**Problem:** The mail engine listens on `0.0.0.0:8025` with no API key validation on most routes. Anyone who can reach port 8025 can query send logs, domain info, and stats.

**Fix:** The Go engine already has an `APIKeys` map in config. Wire it into a middleware:
```go
func APIKeyMiddleware(cfg *config.Config) gin.HandlerFunc {
    return func(c *gin.Context) {
        key := c.GetHeader("X-API-Key")
        if _, ok := cfg.APIKeys[key]; !ok {
            c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "invalid API key"})
            return
        }
        c.Next()
    }
}
```

Also set `MASTER_API_KEY` in `.env` and only expose port 8025 internally:
```yaml
# docker-compose.yml — mail-engine
mail-engine:
  ports: []   # remove public exposure entirely
  # backend accesses it via internal Docker DNS: http://mail-engine:8025
```

---

### Fix 13 — Set DEBUG=false

**File:** `.env`

```env
DEBUG=false
ENVIRONMENT=production
```

When `DEBUG=true`, FastAPI returns full Python tracebacks to clients on 500 errors, exposing file paths, variable names, and internal logic.

---

## 4. Medium Priority Fixes

### Fix 14 — ChampGraph Should Not Be Publicly Exposed

**File:** `docker-compose.yml`

```yaml
# graphiti service (separate compose)
# Remove the public port mapping
ports: []   # internal only, backend reaches via Docker network
```

### Fix 15 — Move `.env` Out of the Project Directory

The `.env` file is in the repo root and contains live API keys, JWT secrets, and SMTP credentials. It should never be committed to git (confirm `.gitignore` includes it) and in production should be injected by a secrets manager (Vault, Doppler, AWS Secrets Manager).

```bash
# Verify it's gitignored
echo ".env" >> .gitignore
git rm --cached .env   # if it was ever committed
```

### Fix 16 — Fix Postfix Relay Env Var Naming

**File:** `docker-compose.override.yml` vs `mail-engine/postfix/entrypoint.sh`

The override file sets `SMTP_RELAY_USER` / `SMTP_RELAY_PASS`, but the entrypoint reads `RELAY_USER` / `RELAY_PASS`. Fix the override to match:
```yaml
smtp:
  environment:
    RELAY_HOST: ${SMTP_RELAY_HOST:-pro.turbo-smtp.com}
    RELAY_PORT: ${SMTP_RELAY_PORT:-2525}
    RELAY_USER: ${TURBOSMTP_USER:-}      # was SMTP_RELAY_USER
    RELAY_PASS: ${TURBOSMTP_PASS:-}      # was SMTP_RELAY_PASS
```

### Fix 17 — Add Unsubscribe Enforcement

**File:** `backend/app/api/v1/send.py`

Before sending to any address, check if that prospect has unsubscribed:
```python
# In send_email endpoint, before calling email_service:
from app.services.prospect_service import prospect_service
prospect = await prospect_service.get_by_email(session, str(request.to))
if prospect and prospect.get("unsubscribed"):
    raise HTTPException(
        status_code=422,
        detail="Recipient has unsubscribed — sending blocked"
    )
```

---

## 5. Custom Domain Email — Complete Setup Guide

This is the end-to-end process to send and receive email as `you@yourdomain.com` through ChampMail.

### Architecture After Setup

```
yourdomain.com (Namecheap)
├── MX records      → Namecheap Private Email (for receiving)
├── SPF record      → authorizes TurboSMTP as sender
├── DKIM record     → generated by ChampMail, added to DNS
└── DMARC record    → policy enforcement

Sending flow:
  User → POST /api/v1/send
       → email_service.py reads EmailAccount from DB
       → SMTP to pro.turbo-smtp.com:2525 (port works on this VPS)
       → TurboSMTP delivers to recipient
       → Recipient sees: From: you@yourdomain.com ✓

Receiving flow:
  Sender → yourdomain.com MX → Namecheap Private Email servers
  ChampMail → IMAP to mail.privateemail.com:993
            → reads replies, detects unsubscribes
```

### Step 1 — Buy Domain on Namecheap

Go to namecheap.com → search → purchase `yourdomain.com`.

After purchase, go to: **Account → Domain List → Manage → Advanced DNS**

Keep this tab open — you'll add records here in Step 3.

### Step 2 — Activate Namecheap Private Email

In Namecheap dashboard → **Email** → **Private Email** → Add to your domain.

- Plan: Starter ($1.34/month, 1 mailbox)
- Create mailbox: `hello@yourdomain.com` (or any name)
- Set password (this is your IMAP password)

Namecheap automatically adds MX records when you activate. Verify these appear in Advanced DNS:
```
MX  @  mx1.privateemail.com  10
MX  @  mx2.privateemail.com  10
```

### Step 3 — Configure DNS Records

In Namecheap **Advanced DNS**, add:

**SPF (who can send as your domain):**
```
Type: TXT
Host: @
Value: v=spf1 include:spf.privateemail.com include:turbo-smtp.com ~all
TTL: Automatic
```

**DMARC (policy — start permissive, tighten later):**
```
Type: TXT
Host: _dmarc
Value: v=DMARC1; p=none; rua=mailto:admin@yourdomain.com; pct=100
TTL: Automatic
```

**DKIM** — Get from ChampMail in Step 4, add here.

### Step 4 — Register Domain in ChampMail (Generates DKIM)

```bash
# Get auth token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@champions.dev&password=<your-admin-password>" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Register domain — ChampMail generates a DKIM key pair
curl -s -X POST http://localhost:8000/api/v1/domains \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "domain_name": "yourdomain.com",
    "selector": "champmail"
  }' | python3 -m json.tool
```

**From the response, copy the `dkim_public_key` value.**

Add it to Namecheap DNS:
```
Type: TXT
Host: champmail._domainkey
Value: v=DKIM1; k=rsa; p=<paste the public key here>
TTL: Automatic
```

### Step 5 — Sign Up for TurboSMTP

Go to turbo-smtp.com → Free account (6,000 emails/month free).

In TurboSMTP dashboard:
1. **Settings → Domains** → Add `yourdomain.com`
2. TurboSMTP gives you a TXT record to verify domain ownership — add it to Namecheap DNS
3. Once verified, get your **SMTP username and password** from Settings

### Step 6 — Create Email Account in ChampMail

```bash
curl -s -X POST http://localhost:8000/api/v1/email-accounts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Your Name",
    "email": "hello@yourdomain.com",

    "smtp_host": "pro.turbo-smtp.com",
    "smtp_port": 2525,
    "smtp_username": "your-turbosmtp-username",
    "smtp_password": "your-turbosmtp-password",
    "smtp_use_tls": true,

    "imap_host": "mail.privateemail.com",
    "imap_port": 993,
    "imap_username": "hello@yourdomain.com",
    "imap_password": "your-privateemail-password",
    "imap_use_ssl": true,
    "imap_mailbox": "INBOX",

    "from_email": "hello@yourdomain.com",
    "from_name": "Your Name",
    "is_default": true
  }' | python3 -m json.tool
```

Save the `id` from the response — you'll need it to test.

### Step 7 — Wait for DNS Propagation and Verify

DNS takes 15 minutes to 2 hours. Check propagation:
```bash
# Check SPF
dig TXT yourdomain.com +short

# Check DKIM
dig TXT champmail._domainkey.yourdomain.com +short

# Check MX
dig MX yourdomain.com +short

# Verify domain in ChampMail
DOMAIN_ID="<id from step 4>"
curl -s -X POST "http://localhost:8000/api/v1/domains/$DOMAIN_ID/verify" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### Step 8 — Send Test Email

```bash
curl -s -X POST http://localhost:8000/api/v1/send \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "to": "your-personal-gmail@gmail.com",
    "subject": "Test from my custom domain",
    "html_body": "<h1>Hello from ChampMail!</h1><p>Sent via <strong>yourdomain.com</strong></p>",
    "text_body": "Hello from ChampMail! Sent via yourdomain.com"
  }' | python3 -m json.tool
```

Expected response:
```json
{
  "message_id": "<unique-id@yourdomain.com>",
  "status": "sent",
  "sent_at": "..."
}
```

Check the email in Gmail → should show `From: Your Name <hello@yourdomain.com>` with a green lock/checkmark.

### Step 9 — Check Email Deliverability Score

Send a test to `mail-tester.com` (it gives you a temporary address + a score out of 10):
```bash
curl -s -X POST http://localhost:8000/api/v1/send \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "to": "test-<unique>@mail-tester.com",
    "subject": "ChampMail deliverability test",
    "html_body": "<p>Deliverability test from ChampMail</p>",
    "text_body": "Deliverability test from ChampMail"
  }'
```

**Target score: 8/10 or above** before running any campaign.

Common deductions and fixes:
- Missing DKIM → re-check DNS record
- SPF too permissive → change `~all` to `-all` after confirming setup works
- No DMARC → verify the `_dmarc` record propagated
- Missing unsubscribe header → implemented in `email_service.py` for campaign sends already

### Step 10 — Tighten DMARC After 2 Weeks

Once you've sent ~100 emails and confirmed delivery:
```
# Update DMARC in Namecheap DNS
v=DMARC1; p=quarantine; rua=mailto:admin@yourdomain.com; pct=100
```

After another 2 weeks with no issues:
```
v=DMARC1; p=reject; rua=mailto:admin@yourdomain.com; pct=100
```

`p=reject` means any email spoofing your domain is rejected by recipients. Maximum protection.

---

## 6. Ongoing Guardrails & Monitoring

### Weekly Checks

```bash
# 1. Check your IP/domain on spam blacklists
curl "https://api.mxtoolbox.com/api/v1/lookup/blacklist/yourdomain.com"

# 2. Check container health
docker ps --format "table {{.Names}}\t{{.Status}}"

# 3. Check for failed sends in logs
docker logs champmail-backend --since 24h 2>&1 | grep -i "smtp\|error\|fail"

# 4. Check beat is actually running scheduled tasks
docker logs champmail-beat --since 1h 2>&1 | grep "Sending due task"
```

### Firewall Rules to Apply Now

```bash
# Allow only necessary public ports
ufw allow 22/tcp     # SSH
ufw allow 80/tcp     # HTTP (if needed)
ufw allow 443/tcp    # HTTPS (if needed)
ufw allow 3001/tcp   # Frontend
ufw allow 8000/tcp   # Backend API

# Block everything sensitive
ufw deny 5432/tcp    # Postgres — internal only
ufw deny 6380/tcp    # Redis — internal only
ufw deny 8025/tcp    # Mail engine — internal only
ufw deny 8026/tcp    # MailHog UI — dev only
ufw deny 1025/tcp    # MailHog SMTP — dev only
ufw deny 8081/tcp    # ChampGraph — internal only
ufw deny 25/tcp      # Postfix SMTP — block until needed
ufw deny 465/tcp     # Postfix SMTPS — block until needed

ufw enable
```

### Environment Variables to Rotate Immediately

| Variable | Action |
|---|---|
| `JWT_SECRET_KEY` | Generate new: `openssl rand -hex 64` |
| `EMAIL_ENCRYPTION_KEY` | Generate new Fernet key: `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` — then re-save all email account passwords |
| `POSTGRES_PASSWORD` | Change and update in docker-compose |
| Admin user password (`admin`) | Change via: `POST /api/v1/auth/register` then delete old account |

### TurboSMTP Sending Limits Reference

| Plan | Emails/month | Daily approx |
|---|---|---|
| Free | 6,000 | 200 |
| Starter ($9/mo) | 15,000 | 500 |
| Pro ($25/mo) | 50,000 | 1,667 |

Set your per-user daily limit in code (Fix 11) to be slightly below the TurboSMTP daily cap.

### IP Reputation Monitoring Services

- **MXToolbox:** `mxtoolbox.com/blacklists.aspx`
- **Mail Tester:** `mail-tester.com` (score out of 10 before campaigns)
- **Google Postmaster Tools:** Register your domain at `postmaster.google.com` — see Gmail delivery rates and spam complaints in real time
- **TurboSMTP Dashboard:** Shows delivery rate, bounces, complaints per campaign

---

## Fix Priority Order (Implementation Sequence)

Do these in order. Do not skip steps.

```
Week 1 — Critical (blocks security breach)
  [x] Fix SSL CERT_NONE in email_service.py
  [x] Block Postgres and Redis from public internet (ufw + docker-compose)
  [x] Restrict MailHog to localhost only
  [x] Secure Postfix (remove open relay, restrict mynetworks)
  [x] Remove /health/db-schema or add admin auth
  [x] Set DEBUG=false

Week 1 — Critical (makes emails actually work)
  [x] Fix Celery tasks to use email_service.py instead of Go stub
  [x] Pass user_id through sequence steps for SMTP credential lookup

Week 2 — High (hardens the system)
  [x] Move rate limiter to Redis storage
  [x] Add login brute force protection (5/min limit)
  [x] Shorten JWT expiry to 1 hour
  [x] Remove dev credentials from API docs
  [x] Change admin password
  [x] Add per-user daily send quota
  [x] Authenticate Go mail engine API

Week 3 — Custom domain setup
  [x] Buy domain on Namecheap
  [x] Activate Private Email for IMAP
  [x] Configure DNS (SPF, DKIM, DMARC, MX)
  [x] Sign up TurboSMTP, verify domain
  [x] Create email account in ChampMail (Step 6 above)
  [x] Send test email, check mail-tester.com score
  [x] Start with p=none DMARC, tighten over 4 weeks

Ongoing
  [ ] Weekly blacklist checks
  [ ] Monitor TurboSMTP bounce/complaint rates
  [ ] Register domain with Google Postmaster Tools
  [ ] Rotate secrets every 90 days
```

---

*This document should be treated as confidential — it contains details of known vulnerabilities.*
