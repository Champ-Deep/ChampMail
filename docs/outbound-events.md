# Events: tracking, outbox, trusted inputs, IMAP

Every event refers to a `send_dispatches.message_id` (the bare Message-ID, no angle brackets). An event for a
message ChampMail never dispatched cannot exist (foreign key plus an explicit check).

## Where each event type comes from

| event_type | Input path | Trust boundary |
|---|---|---|
| `opened` | `GET /o/<token>.gif` on the domain's tracking host | signed token, host and dispatch checked |
| `clicked` | `GET /c/<token>` (302 to the signed destination) | same |
| `bounced` | hard DSN (5.x.x) read over IMAP | known dispatch only |
| `delivered` | DSN delivery receipt (2.x.x, `Action: delivered`) over IMAP, or `POST /api/v1/events` | known dispatch |
| `replied`, `complained`, `unsubscribed` | `POST /api/v1/events` only | `X-API-Key`, known dispatch |

SMTP acceptance is never reported as `delivered`. Soft bounces (4.x.x) are stored in `bounces` and emit nothing.

ChampMail does not detect replies or complaints itself. `POST /api/v1/events` is the adapter surface: whatever
sees the real signal (a provider webhook, a reply classifier, a feedback-loop reader, a one-click unsubscribe
endpoint) must forward it there. Until such an adapter exists, `replied`, `complained` and `unsubscribed` have a
working input but no producer. Nothing is fabricated.

```
POST /api/v1/events   X-API-Key: ...
{"event_type": "delivered|replied|complained|unsubscribed", "message_id": "...", "timestamp": "2026-10-23T01:00:00Z"}
-> 200 {"status": "queued" | "duplicate", ...}   404 unknown message   422 bad type/timestamp   401 key
```

`timestamp` is optional (default now; naive means UTC). It must not be more than 5 minutes in the future or more
than a minute before the message was dispatched. `bounced`, `opened` and `clicked` are refused here (422).

## Tracking links

`build_message` signs each link: `token = base64url(json{kind, message_id, domain_id, url}) . base64url(HMAC-SHA256)`
with `TRACKING_SECRET` (required, any environment; rotating it breaks every link already sent). The destination is
inside the signature, so there is no open redirect. A request is honoured only if all hold: signature valid
(constant time), kind matches the route, destination is http(s), a non-failed dispatch exists for the message
**and** belongs to the signed domain, and the request `Host` equals that domain's own `tracking_subdomain`.
Anything else is a bare 404 and creates no event. There is no shared-host fallback.

Repeated opens/clicks always answer the same way and create one event per (message, type). A click on any link of
a message is the message's one `clicked` event. If recording fails the recipient still gets the image/redirect (the
failure is logged); that single event is lost.

Routing: the app serves `/o` and `/c` at its root, on whatever host reaches it. The proxy for a tracking host should
expose only those two paths. Behind a proxy that rewrites `Host`, the stored `tracking_subdomain` check will 404
everything: forward the original Host. Open numbers are pixel loads (Apple Mail Privacy Protection and scanners
inflate them), not human opens.

## Outbox (`outbound_events`, migration 0007)

One row per (message_id, event_type), ever (unique). `emit()` is a single `INSERT ... ON CONFLICT DO NOTHING` in the
caller's transaction, so a stored bounce and its pending event commit together; a replayed DSN or a repeated
open cannot create a second row.

States: `pending` (due at `next_attempt_at`), `leased` (a worker holds it until `lease_expires_at`, 120 s),
`delivered` (receiver answered 2xx), `dead`.

- A worker claims one due row with `FOR UPDATE SKIP LOCKED`, bumps `attempts`, commits, then POSTs. Marked
  `delivered` only after a 2xx.
- A worker that dies or is cancelled after the claim leaves a leased row. After the lease expires another worker
  reclaims it. The claim counted as an attempt, so a poison event ends dead instead of looping.
- Failure: back to `pending` with `next_attempt_at = now + min(10 s * 2^(attempts-1), 1 h)`, persisted. The drain
  stops at the first transient failure and tries again next tick.
- `dead`: 400 or 422 from the receiver (payload rejected), or 20 attempts (about a day of downtime). Any other
  status, including 401, 404 and 429, is retried (a wrong secret or URL is fixable; do not destroy events).
- `CHAMPMAIL_CLIENT_URL` unset: events stay `pending`.
- Redis is no longer involved in events.

Headers sent: `x-webhook-secret` and `Idempotency-Key: <event_type>:<message_id>` (stable across retries).

### Delivery guarantee: at-least-once, not exactly-once

If the receiver applies an event and its response is lost, the retry sends the same event again. This cannot be
fixed on the sender. The Sledgehammer receiver should dedupe effects on `Idempotency-Key` / (message_id,
event_type). Harbinger's `/api/email/track` as it stands does not dedupe: a repeat re-stamps the `sent_emails` row and
re-runs its negative-event pipeline (`recordBounce`, the `campaign_people` update, `suppress`, enrollment stop).
The stamp and the status updates are idempotent by construction; whether `recordBounce` (it adjusts an org email
pattern) and `suppress` tolerate a repeat was not verified here and is Harbinger's to confirm. No Harbinger change
was made.

### Replaying dead events

```sql
SELECT id, event_type, message_id, attempts, last_error FROM outbound_events WHERE status = 'dead';
UPDATE outbound_events SET status='pending', attempts=0, next_attempt_at=now(), lease_expires_at=NULL
WHERE id = '<id>';
```

## IMAP

`poll_all` isolates each mailbox (a failure rolls back and moves on), bounds every IMAP operation with a 20 s socket
timeout, and treats a refused LOGIN as an authentication failure: that mailbox is set to `paused` with
`status_reason = 'imap_auth_failed: <server message>'`, only if it was `active` (a manual pause or retire keeps its
own status and reason). Its domain and other mailboxes are untouched; the send path already refuses a paused
mailbox (409 `mailbox_paused`). The worker never sets a mailbox back to `active` and does not poll a mailbox it
paused for auth failure (no login hammering). An operator resumes with `PATCH /api/v1/mailboxes/{id}`
`{"status": "active", "reason": "..."}` once the credentials are fixed. Unreachable servers and timeouts are not
auth failures and pause nothing.

Known limit: a DSN is deduped by the hash of its raw bytes. A byte-identical replay (poll died before marking seen)
dedupes. A re-delivered copy with different transit headers is stored a second time in `bounces`; its event is still
created once.
