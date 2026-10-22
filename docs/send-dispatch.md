# Send dispatch: idempotency, outcomes, operator handling

`POST /api/v1/send` writes one `send_dispatches` row per accepted send, in the same transaction
as the mailbox claim and before SMTP. The row holds message identity and ownership
(`message_id`, `domain_id`, `mailbox_id`), the optional `idempotency_key`, a `payload_hash`
(conflict detection only, never used to dedupe content), `status`, and the success `response`.
It holds no SMTP secrets and no message content.

## Keys

- Optional `Idempotency-Key` header and optional `idempotency_key` body field. If both are sent they
  must be equal, otherwise 422. Blank or longer than 255 characters is 422.
- Keyless requests (ChampHarbinger) are never deduplicated. They still get a dispatch row.
- Same key and same payload after success: the stored 200 body is returned verbatim. No SMTP, no cap slot.
- Same key, different payload: 409 `idempotency_conflict`.
- Concurrent same-key requests: the unique index on `idempotency_key` picks one winner. A loser's slot
  claim rolls back in the same transaction (no cap consumed, no throttle left behind) and it answers from
  the winner's row, so at most one request ever reaches SMTP, also when the pool spans several mailboxes.

## Status values

| status | meaning | same key again |
|---|---|---|
| sending | claim committed, SMTP outcome not recorded (in flight, or the process died) | 503 `dispatch_in_progress` |
| sent | SMTP accepted the message | 200, stored response |
| failed | provably not accepted (connect, auth, sender/recipient refused, explicit 4xx/5xx reply) | retried on the same row, slot was given back |
| unknown | SMTP outcome ambiguous (read timeout, disconnect, anything unrecognised) | 503 `smtp_outcome_unknown` |

Other refusals: Redis unreachable is 503 `redis_unavailable` before any claim or SMTP (spec 3.12).
Paused/retired mailbox or domain, blacklisted domain, and mailbox without SMTP credentials are 409.
Authentication is 401. Cap and throttle are 429.

## What is NOT guaranteed

SMTP has no transaction. If the server accepts the message and the acknowledgement is lost, ChampMail
cannot know. It records `unknown`, keeps the cap slot spent, and never retransmits on retries or restarts.
This is at-most-once submission per key, not exactly-once delivery. The same applies when the process dies
while the row is `sending`, and when the final `sent` update fails after SMTP succeeded (logged as
"sent but could not record dispatch"; the row stays `sending`). Keyless requests that end `unknown` return
the `message_id` in the 503 body, but a keyless retry is a new send: Harbinger-style callers can double send
after an ambiguous failure. Use keys.

## Operator reconciliation

Find the rows (they carry the `message_id` that is in the Message-ID header):

```sql
SELECT id, idempotency_key, message_id, mailbox_id, status, updated_at
FROM send_dispatches WHERE status IN ('sending','unknown') ORDER BY updated_at;
```

Check the mailbox's Sent folder or the provider for that Message-ID, then:

```sql
-- the message is there: replay it to callers (response must be the original 200 body shape)
UPDATE send_dispatches SET status='sent',
  response=jsonb_build_object('message_id', message_id, 'status','sent', 'domain_id', domain_id::text,
                              'sent_at', to_char(updated_at,'YYYY-MM-DD"T"HH24:MI:SS"+00:00"'))
WHERE id = '<dispatch id>';

-- the message is not there: allow the same key to retry, and give the slot back
UPDATE send_dispatches SET status='failed', response=NULL WHERE id = '<dispatch id>';
UPDATE email_accounts SET sent_today = sent_today - 1
WHERE id = '<mailbox id>' AND sent_today > 0 AND sent_today_date = CURRENT_DATE;
```

Only mark `failed` after confirming absence; marking a delivered message `failed` lets the next retry send it twice.
A `failed` retry still waits out the mailbox's 45-90 s gap (429 `throttled` until then).
