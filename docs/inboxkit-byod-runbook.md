# InboxKit bring-your-own-domain — operator runbook

*Written 2026-07-30. Connect a domain you already own to InboxKit, buy mailboxes
on it, and prove a ChampMail send end to end.*

Intended reader: whoever owns the InboxKit account and DNS. No code changes are
needed to follow this — everything is an authenticated admin API call.

---

## 0. Read this first

**Do not use your primary business domain.** Cold outreach burns sender
reputation as a matter of course; that is what warmup and rotation exist to
manage. If `championsmail.com` picks up complaints or a blacklist entry, your
real business mail — client threads, invoices, password resets — goes down with
it, and recovery is measured in months.

Sending domains are disposable by design. Use a lookalike that 301-redirects to
the real site: `getchampionsmail.com`, `championsmail.co`, `trychampionsmail.com`.

Connect the domain you are willing to lose.

**One unverified dependency.** The InboxKit endpoint *paths* for this feature are
not live-verified — the public docs name the operations but not their URLs. Step
1 below resolves them. If it reports NOT FOUND, everything after it will fail
with a clear message rather than silently doing nothing.

---

## 1. Pin the endpoint paths (once, ~1 minute)

```bash
cd ChampMail/backend
INBOXKIT_API_KEY=<key> INBOXKIT_WORKSPACE_ID=<workspace> \
  ./.venv/bin/python -m app.services.inboxkit.domain_connect --probe
```

Expected output:

```
Resolved paths (paste into the _*_PATHS tuples):
  cf_list                      /v1/api/cloudflare-domains/list
  dns_records                  /v1/api/dns/records
  cf_connect (inferred)        /v1/api/cloudflare-domains/connect
  cf_disconnect (inferred)     /v1/api/cloudflare-domains/disconnect
```

Paste each winner into the matching `_*_PATHS` tuple in
`app/services/inboxkit/domain_connect.py`, reduced to a single entry with a
`# verified live <date>` comment — the convention the rest of `client.py` uses.

Do the same for health telemetry:

```bash
INBOXKIT_API_KEY=<key> \
  ./.venv/bin/python -m app.services.inboxkit.deliverability --probe
```

**If a path reports NOT FOUND**, it usually means the plan does not include that
product (InfraGuard is a paid add-on; Inbox Placement rides on it). That is fine
— health fields degrade to "unknown", which fails open and never blocks sending.

---

## 2. Connect the domain

Two modes. Pick based on whether you are willing to move DNS to Cloudflare.

### Mode A — MANAGED (recommended, fully hands-off)

InboxKit writes MX, SPF, DKIM and verification records itself.

Prepare a Cloudflare API token **scoped to the minimum**:

| Setting | Value |
|---|---|
| Permissions | Zone → DNS → **Edit** |
| Zone Resources | Include → Specific zone → *your sending domain only* |
| TTL | Set an expiry (e.g. 7 days) |

Never use a global API key or an "All zones" token. This token can rewrite DNS.

```bash
curl -X POST https://<champmail>/api/v1/admin/inboxkit/domain/connect \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{
        "domain": "getchampionsmail.com",
        "cloudflare_api_token": "<scoped token>",
        "cloudflare_zone_id": "<zone id>"
      }'
```

Response:

```json
{ "domain": "getchampionsmail.com", "mode": "managed", "connected": true,
  "domain_uid": "dom_...", "native_status": "dns_setup_pending",
  "needs_manual_dns": false }
```

**Revoke the Cloudflare token once `native_status` reaches `active`.** ChampMail
never stores it — there is deliberately no column for it — so revoking costs you
nothing, and leaving a live DNS-write token around is the larger risk.

### Mode B — MANUAL (any DNS provider)

Omit the token and you get the records to create yourself:

```bash
curl -X POST https://<champmail>/api/v1/admin/inboxkit/domain/connect \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"domain": "getchampionsmail.com"}'
```

Create every returned record in Route53 / Namecheap / GoDaddy / wherever, then:

```bash
curl -X POST https://<champmail>/api/v1/admin/inboxkit/domain/verify \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"domain": "getchampionsmail.com"}'
```

Poll this — it is a read plus a validation pass, so it is safe to repeat. DNS
propagation is typically minutes but the TTL on any pre-existing record governs.

Confirm independently before moving on:

```bash
dig +short MX  getchampionsmail.com
dig +short TXT getchampionsmail.com          # SPF
dig +short TXT selector1._domainkey.getchampionsmail.com   # DKIM
```

---

## 3. Register the webhook BEFORE buying anything

This ordering matters. InboxKit reports provisioning progress over webhooks
(`domain.status_changed`, `mailbox.status_changed`). If the endpoint is not
reachable when you buy, you miss the entire lifecycle and have to reconcile by
polling.

```bash
curl -X POST https://<champmail>/api/v1/admin/inboxkit/webhook \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://<champmail>/api/v1/webhooks/inboxkit"}'
```

The URL must be publicly reachable — localhost will not work. Deploy first, or
tunnel.

Signature note: InboxKit signs with a **static SHA-256 of the team API key**, not
an HMAC over the body. So `INBOXKIT_API_KEY` is what verification needs; there is
no separate webhook secret to generate.

---

## 4. Buy mailboxes

Start with **three on one domain** — the correct 3-5-per-domain ratio, and enough
to prove rotation actually rotates. One mailbox cannot demonstrate that.

```bash
curl -X POST https://<champmail>/api/v1/admin/inboxkit/domain/mailboxes \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{
        "domain": "getchampionsmail.com",
        "usernames": ["deep", "sales", "hello"],
        "first_name": "Deep",
        "platform": "google",
        "start_warmup": false
      }'
```

`start_warmup: false` is deliberate — warmup bills **$3/mailbox/month** and only
matters once you mail strangers. While you are sending to your own inboxes it
buys nothing. Turn it on at step 7.

Watch provisioning:

```bash
curl -H "Authorization: Bearer $ADMIN_JWT" \
  https://<champmail>/api/v1/admin/inboxkit/domain/connected
```

Mailboxes move `pending → processing → configuring_* → active`. ChampMail fetches
credentials only once a mailbox reaches `active`, and always by re-calling
`/mailboxes/show-credentials` — never from the webhook payload.

---

## 5. Verify ChampMail picked them up

```sql
-- Credentials landed and the mailbox is linked to its domain
SELECT email, inboxkit_uid, credentials_persisted, domain_id,
       daily_send_limit, sent_today, sent_today_date, last_send_at
FROM email_accounts
WHERE inboxkit_uid IS NOT NULL;
```

You need **`credentials_persisted = true` and a non-null `domain_id`** on all
three rows. If `domain_id` is null, the webhook did not resolve the domain — check
that step 3 happened before step 4.

`daily_send_limit` should read 25 (migration 015 default). `sent_today` 0,
`sent_today_date` null until the first send.

---

## 6. Prove a send end to end

Send **to inboxes you own**. This is a plumbing test, not a deliverability test.

```bash
curl -X POST https://<champmail>/api/v1/send \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{
        "to": "deep@championsmail.com",
        "subject": "ChampMail BYOD smoke test",
        "html_body": "<p>Plumbing test. {{tracking_url}}</p>",
        "domain_id": "<the domain uuid>"
      }'
```

Check, in order:

1. **It arrived**, and in the inbox rather than spam. Test against a Gmail, an
   Outlook and a Yahoo address you control — placement differs per provider.
2. **Message-ID is real.** Compare the `message_id` in the response against the
   received message's header. They must match. This used to be impossible: the
   code read `msg["Message-ID"]` *after* handing the message to smtplib, where
   the server assigns it, so the stored value was a synthetic
   `<subject@champmail>` string matching nothing — breaking reply threading and
   bounce correlation. Fixed 2026-07-30.
3. **Accounting moved:**
   ```sql
   SELECT email, sent_today, sent_today_date, last_send_at
   FROM email_accounts WHERE inboxkit_uid IS NOT NULL
   ORDER BY last_send_at NULLS FIRST;
   ```
   Exactly one mailbox should show `sent_today = 1`.
4. **Rotation works.** Send twice more. Each send should hit a *different*
   mailbox — least-recently-used ordering. If all three sends land on the same
   mailbox, rotation is broken (this was the `.limit(1)` bug, fixed 2026-07-30).
5. **Tracking fired.** The pixel should register an open in `send_logs`.

### Campaign path (the one that actually matters)

Steps 1-4 exercise the API route. Campaign volume goes through the **Celery
task**, which is a different code path — and until 2026-07-30 it emitted no
events at all. Test it explicitly:

```bash
# Requires the worker AND beat services to be running.
# On Railway: two separate services, see worker.railway.toml / beat.railway.toml
celery -A app.celery_app worker --loglevel=info -Q default,sending &
celery -A app.celery_app beat  --loglevel=info &
```

Then trigger a campaign send and confirm `email.sent` reaches ChampIQ:

```bash
# Requires CHAMPIQ_URL set, or emit_email_event() is a silent no-op.
curl -H "Authorization: Bearer $ADMIN_JWT" https://<champiq>/api/runs/ledger | \
  grep email.sent
```

**If the worker is not running, campaigns are accepted and nothing sends.** That
is not a hypothetical — neither `render.yaml` nor `railway.toml` defined a worker
or beat service before 2026-07-30.

---

## 7. Turn on warmup, then go live

Only now:

```bash
curl -X POST https://<champmail>/api/v1/admin/inboxkit/domain/mailboxes \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"domain": "getchampionsmail.com", "usernames": [], "start_warmup": true}'
```

Warmup routing is already correct: `app/tasks/warmup.py:26` checks
`infra_provider == "inboxkit"`, delegates to InboxKit's warmup API, and skips the
internal seed loop. You are **not** double-warming or double-paying.

Do not rely on ChampMail's own seed-address warmup for these mailboxes — it is
capped at 5 emails/day by a hardcoded seed list, its day counter never increments
(5 never reaches the day-0 limit of 10), and it has no reply loop, so it
generates almost no reputation signal. Warmup is the one part of this stack worth
paying for: the value is a reciprocal pool of real aged inboxes that *reply*, and
that cannot be self-built cheaply.

Ramp: 25/day per mailbox after warmup completes. Scale by adding mailboxes, not
by raising the per-mailbox number.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| `connect` returns `connected: false` with a "path needs pinning" message | Step 1 not done, or the plan lacks Cloudflare domains |
| `records_required` is empty in MANUAL mode | `dns_records` path unresolved — rerun step 1 |
| Mailbox stuck in `configuring_dns` | DNS not propagated, or a conflicting pre-existing MX record |
| `credentials_persisted` stays false | Mailbox not `active` yet, or `INBOXKIT_API_KEY` missing on the **worker** service |
| `domain_id` null on `email_accounts` | Webhook registered after purchase — reconcile by re-fetching mailbox status |
| Send fails `no ready InboxKit mailbox on domain` | No mailbox has `credentials_persisted = true` on that domain |
| Send fails `all N mailbox(es) ... hit their daily send limit` | Working as designed. Wait for reset or raise `daily_send_limit` |
| Campaign accepted, nothing sends | Celery worker not running |
| Sends work but ChampIQ sees nothing | `CHAMPIQ_URL` unset — `emit_email_event()` is a no-op |

## What still needs a human decision

- **`send_batch_task` does not support InboxKit.** It always uses the Go
  mail-engine and never branches on `_domain_uses_inboxkit`, so a batch on an
  InboxKit domain goes to an engine holding no credentials for it. It now logs a
  loud warning. Use per-prospect `send_email_task` until this is resolved —
  fixing it properly means either looping per-prospect (losing the batch API) or
  adding a batch path to the IAL.
- **Endpoint paths in `domain_connect.py` and `deliverability.py`** stay
  unverified until step 1 runs against a real key.
