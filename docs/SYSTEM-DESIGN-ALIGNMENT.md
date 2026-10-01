# ChampMail — local ↔ system-design alignment (plan.md → this tree)

Maps the **current local code** against the locked architecture in `plan.md`, so we can take the
local version *up to the document level* **without losing the InboxLint pre-send gate** already
landed (`feat/inboxlint-presend-gate`, commit `9be118f`).

**Verdict:** the local tree already has the **shape** the doc specifies — it is well past the plan's
"PR #1" baseline. The Go in-house MTA exists (`mail-engine/`: `builder.go`, `dkim.go`, `deliver.go`,
api/db/redis), and the control-plane services exist (`identity_service`, `events` on Redis,
`ramp_governor`, `suppression_service`, `cloudflare_client`, `domain_rotation`). What's missing is
**8 of the plan's specific "fix now" hardening items** — and none of them touch or conflict with
InboxLint.

---

## 1. Where InboxLint sits in the documented architecture (preserved)

`plan.md §2` puts **Suppression + Ramp-governor + Event bus** in the **control plane**. InboxLint is a
**new control-plane policy gate** in exactly that tier — it already runs in `tasks/sending.py` *after*
tracking/unsubscribe injection and *before* `mail_engine_client.send_email` hands off to the Go MTA:

```
control plane (Python)                              data plane (Go MTA)
  suppression gate ─▶ InboxLint gate ─▶ submission ─▶ builder+DKIM ─▶ :25 outbound
  (team+global)      (spam/CAN-SPAM,                  (QP, RFC-2047,
                      block→don't send)                List-Unsub in h=)
```

This placement is correct and **survives the alignment untouched**. It is *complementary* to the
Phase-1 DKIM requirement, not redundant:

- **InboxLint** guarantees the unsubscribe line / compliance content **exists** before send.
- **`dkim.go` `h=`** guarantees that same `List-Unsubscribe` header is **DKIM-signed** (Gmail/Yahoo
  ignore unsigned one-click unsub).

So the doc's deliverability work and the InboxLint gate reinforce each other. Keep InboxLint as the
control-plane gate; do not move it into the Go builder.

---

## 2. Gap table — plan.md "fix now" items vs this local tree

Verified by reading the files (2026-06-24). ✅ present · ❌ missing · ⚠️ partial.

| # | Plan item (`plan.md §1`) | File | Status | Note |
|---|---|---|---|---|
| A | DKIM relaxed/relaxed + `List-Unsubscribe` in `h=` | `dkim.go`, `builder.go` | ✅ | `SignableHeaderKeys` + `Sign()` auto-cover List-Unsub/Post |
| B | **QP-encode MIME bodies** (CTE: quoted-printable, ≤76 octets) | `builder.go` `buildBody` | ❌ | bodies written raw — **post-signing mutation risk; gates Phase 1** |
| C | **RFC-2047 encoded-word** for `Subject` + non-ASCII display names | `builder.go` | ❌ | no encoding — non-ASCII subjects break |
| D | **Strip CR/LF from header values** (header-injection guard) | `builder.go` `orderedHeaders` | ❌ | values written raw |
| E | **2048-bit key floor** startup guard (reject < 2048) | `dkim.go` `parsePrivateKey` / `config.go` | ❌ | only the *test* uses 2048; no runtime floor |
| F | Suppression **`team_id == team OR team_id IS NULL`** (global suppresses all) | `suppression_service.py` | ❌ | matches exact team only — **global opt-outs leak through** |
| G | Suppression **person-aware** (`person_id`, `email_sha256`, match `email OR person_id`, Gmail `+tag`/dot canon) | `suppression_service.py` + `models/suppression.py` | ❌ | model has no `person_id`/`email_sha256`; `_norm` only lowercases |
| H | Ramp **THROTTLE decrements `warmup_day`** + reputation keyed **per sending IP** | `ramp_governor.py`, `tasks/ramp.py` | ⚠️/❌ | ADVANCE increments day ✅; THROTTLE does **not** decrement; governor keys on **domain only**, not IP |

Already-aligned (no action): two-plane split, Redis event bus (`events.py`), identity spine
(`identity_service.py`), Cloudflare DNS client, domain rotation, the ramp ADVANCE/HOLD/THROTTLE/PAUSE
closed loop, the suppression gate's *placement* in the send path, **and InboxLint**.

---

## 3. Bringing local → document level (ordered, InboxLint preserved)

Follows `plan.md §3` phases. None of these remove or alter the InboxLint gate.

1. **Phase-1 gate (do first — the doc's hard gate).** Fix **B, C, D** in `builder.go` + **E** in
   `dkim.go`/`config.go`. These four are what make `mail-tester 10/10` + Gmail *Show original*
   `SPF/DKIM/DMARC PASS` real. The `dkim_test.go` already proves a 2048 sign round-trips; add a
   builder test asserting QP output + a stripped CR/LF header.
2. **Phase-2 gate.** Fix **F + G** in `suppression_service.py` (+ migration adding `person_id`,
   `email_sha256`, partial unique index on `email WHERE team_id IS NULL`). The suppression gate in
   `sending.py` already runs *before* InboxLint, so order is unchanged.
3. **Phase-3.** Fix **H**: THROTTLE decrements `warmup_day`; add a `sending_ip` dimension to the
   ramp metrics so reputation is per-IP.
4. **Phases 4–5** (`plan.md §3`): inbound MX + IMAP on `emersion/*`, then pool + BYOD. New surface,
   doesn't touch InboxLint.

### What does NOT change
- `tasks/sending.py` InboxLint block stays exactly as committed (fail-open, `block`→don't send).
- `inboxlint.py` stays vendored, stdlib-only, no new dependency.
- The control-plane → data-plane handoff (`mail_engine_client.send_email`) is unchanged; the fixes
  are *inside* the Go builder/signer, downstream of InboxLint.

---

## 3a. Phase 1–3 — DONE (committed)

Applied + verified (`go test ./internal/mailer` green; Python self-checks green):
- **B/C/D** `builder.go`: QP-encode bodies, RFC-2047 Subject/display-names, CR/LF header-injection strip.
- **E** `dkim.go`: 2048-bit key floor on every sign.
- **F/G** `suppression_service.py` + model + migration `010`: `team OR NULL` global gate, person-aware
  (`email OR person_id`), canonicalization (+tag/gmail-dots), partial unique index on global email.
- **H** `ramp_governor.py`/`tasks/ramp.py`: `next_warmup_day` (THROTTLE steps down), `sending_ip` seam.

InboxLint untouched.

## 3b. Phase 4–5 — build spec (needs a live :25 host to validate)

These are **new surface**, not fixes — they require a port-25 host + real MX, so they are specced here
rather than shipped blind. Both build on `emersion/go-smtp` + `go-imap` (`plan.md §3`), which is why
they're separated from the 1–3 hardening.

### Phase 4 — inbound MX + IMAP
- **`mail-engine/internal/smtpd/` (new):** a `go-smtp` server on :25 implementing `smtp.Backend` /
  `smtp.Session`. **The load-bearing correctness rule (plan §3 Phase 4): validate the recipient at
  `Rcpt()` time and return `550` for an unknown mailbox — NEVER accept-then-bounce** (backscatter
  blocklists the IP). Skeleton:
  ```go
  func (s *Session) Rcpt(to string, _ *smtp.RcptOptions) error {
      if !mailboxExists(s.ctx, to) {           // DB lookup against provisioned mailboxes
          return &smtp.SMTPError{Code: 550, EnhancedCode: smtp.EnhancedCode{5,1,1},
              Message: "no such user"}          // reject AT RCPT — no backscatter
      }
      s.rcpts = append(s.rcpts, to); return nil
  }
  func (s *Session) Data(r io.Reader) error {   // verify SPF/DKIM/DMARC via go-msgauth, then store
      res := authVerify(r)                       // go-msgauth: SPF + DKIM + DMARC
      return s.store.Deliver(s.rcpts, res)       // → IMAP mailbox + reply-ingest event
  }
  ```
- **`mail-engine/internal/imapd/` (new):** `go-imap` server + a Maildir/DB mailbox store, IMAP IDLE.
- **Native reply-ingest:** on `Data()`, emit the same `champ.email.v1` reply event the existing
  `reply_ingest.py` consumes — so ReplyIQ/ChampOps see native replies with zero downstream change.
- **TLS:** STARTTLS + 465/993, **MTA-STS** policy file served on the control plane, **DANE/TLSA**
  records published via the Cloudflare client. Re-verify DMARC RUA after.
- **Gate:** `go-smtp :25` rejects unknown RCPT with 550 (no backscatter); Thunderbird connects via
  IMAP; a seed reply round-trips into the event bus.

### Phase 5 — pool + BYOD
- **Pool:** domains 2..N each get own PTR + own DKIM selector/key + own SPF; `domain_rotation` +
  the ramp-governor rotate the **per-IP** warmed pool (the `sending_ip` column from Phase 3 is the key).
- **BYOD:** a provisioning flow that emits the DNS records a client adds to *their* domain
  (`cloudflare_client` already automates ours); same DKIM-provision + **verify-before-send** gate as
  managed domains (`domain_service` verification path).
- **Gate:** a second warmed sender + a BYOD client domain both pass auth and rotate without
  cross-contaminating reputation.

> Why not coded now: a `go-smtp` inbound server is only meaningfully testable against a real :25 host
> with a clean PTR (the `plan.md §6` gates). Shipping it untested would violate the plan's own
> "prove auth passes before proceeding" discipline. The skeleton above is drop-in once Phase 0's host
> exists.

## 4. One-line summary
The local version is **architecturally already the documented system** (two planes, in-house Go MTA,
control-plane gates). To reach *document level* it needs the **8 hardening fixes** above — B/C/D/E
gate Phase 1, F/G gate Phase 2, H gates Phase 3 — and **InboxLint requires zero changes**: it already
sits where the doc puts control-plane policy, and it *strengthens* the Phase-1 unsubscribe/DKIM work
rather than competing with it.
