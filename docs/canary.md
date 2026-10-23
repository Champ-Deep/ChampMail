# Canary sends, seeds, cap-only PATCH (M1.1)

A policy pause blocks every campaign send, so recovery could never be measured. A canary is the one bounded exception.

| Call | Contract |
|---|---|
| `POST /api/v1/seeds {address, provider: gmail or outlook}` | 201 `{id, address, provider, created_at}`. Address is stored lowercase. 409 duplicate, 422 bad address or provider. |
| `GET /api/v1/seeds` | `[{id, address, provider, created_at}]` ordered by address. |
| `POST /api/v1/send` with `canary: true` | Same body as a normal send. `to` must equal a registered seed (case-insensitive, bare address only) else **422**. Optional `headers: {"X-Sledgehammer-Canary": "..."}`: that one header is forwarded verbatim, every other header is dropped, CR or LF is a 422. |
| Eligibility | Domain `send_status` active or paused (never retired: **409** `domain_retired`). Blacklisted domain: 409. Mailbox must be `active` and enabled: individually paused or retired is 409 `mailbox_paused` or `mailbox_retired`. Domain operator hold (paused) does not block it. |
| Cap | 6 per domain per UTC day, counter `domains.canary_sends_today` (shown by `GET /domains` as `canary_sends_today` and `canary_cap`). The 7th is **429** `canary_cap`. A definite SMTP refusal gives the slot back. |
| Not consumed | The mailbox `sent_today` campaign cap, `next_send_at` (45 s gap), `last_send_at`. |
| Recording | `send_dispatches.canary = true`. Idempotency (key, replay, conflict, `unknown` parking) is unchanged; `canary` is part of the request fingerprint, so the same key with `canary` flipped is a 409 conflict. |
| `PATCH /api/v1/mailboxes/{id} {cap}` | Cap 1 to 200 (else 422), status and reason untouched. `{cap, status, reason}` together still works. `{}` is 422. |

Success body, as for any send: `{message_id, status: "sent", domain_id, sent_at}`.
