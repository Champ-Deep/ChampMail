# ChampMail — Cold-outreach improvement plan

Date 2026-06-22. Audit of ChampMail vs the modern cold-email stack + what to add.

## Latest-copy note
Local `~/Documents/ChampMail-main` → remote `developer00777/Champ_mail` (newest, Jun 19).
**`Champ-Deep/ChampMail` (suite-canonical) is a month stale (May 13)** — sync it from
developer00777 so the suite's canonical ChampMail isn't behind the active dev line.

## What ChampMail ALREADY has (mature — most tools are redundant)
Owned Stalwart mail engine (SMTP+IMAP) · domain/inbox **rotation** (`domain_rotation.py`) ·
closed-loop **warmup/ramp-governor** (ADVANCE/HOLD/THROTTLE/PAUSE on live reputation) ·
**suppression** · DKIM/SPF/DMARC + Cloudflare DNS automation · DSN/**bounce** parsing ·
**reply detection** (bounce vs OOO vs human, thread-match, auto-pause, opt-out suppress) ·
open/click **tracking** · **sequences** · **analytics** · FalkorDB knowledge graph · AI
campaigns (Claude) · CloudMeet scheduler · UTM.

## Tools → ChampMail (the list)
| Tool | Verdict |
|---|---|
| **coldflow** (SPF/DKIM/DMARC, SMTP, sequences) | **Redundant** — ChampMail is a superset + owns its engine |
| **Postal** (OSS mail server) | **Skip** — ChampMail uses Stalwart (its own SMTP/IMAP) |
| **Instantly / Smartlead / Lemlist** (managed: unlimited inboxes, warmup, rotation) | **ChampMail replaces these** — owned-infra is the vision's deliverability moat (don't rent inbox infra) |
| **Lavender** (score/coach outbound) | **BUILT** → `message_scorer.py` |
| **harvey** (scrape → write → send → classify replies → auto-respond) | scrape=champscrape · write=Pitch Writer · send=ChampMail · **reply-intent BUILT** → `reply_intent.py` |
| **signal-prospecting-kit** (ICP signals → drafts) | **Integrate** — Harbinger signal → ChampMail sequence trigger (next) |
| **b2b-sdr-agent-template** (10-stage, BANT, WhatsApp/Telegram, ChromaDB) | multichannel → ChampConnect · BANT idea → lead-qual add · ChromaDB → FalkorDB already |
| **sales-outreach-automation-langgraph** (research→qualify→message + CRM) | Champ IQ orchestrator + CRM connectors |

## Built this pass (net-new, tested, pure)
1. **`services/message_scorer.py`** — Lavender-style pre-send scorer: spam words, length,
   reading grade, link ratio, personalization, question, CTA, subject, formatting → 0..1 +
   A–F grade + concrete suggestions. Gate or warn on send. Demo: good email 0.98/A, spam
   email 0.31/F. Also exports `content_quality(subject, body)` → the REAL 0..1 signal for
   **ChampOracle's SSR sim** (replaces the hardcoded `content_quality=0.6`). Self-check passes.
2. **`services/reply_intent.py`** — intent classifier on top of reply_ingest's genuine-reply
   detection: meeting / interested / question / objection / not-interested / unsubscribe /
   referral → recommended action (book / route-human / answer / handle-objection / suppress /
   retarget). Strips quoted history. 7/7 self-check.

## Wiring (next, low-risk)
- **send/sequence gate:** call `message_scorer.score_email` before enqueue; block grade F,
  warn D, attach score to `send_log`. Surface in the UI as a Lavender-style coach.
- **reply pipeline:** after `reply_ingest.classify_inbound` == REPLY, call
  `reply_intent.classify_intent`; route by `action` (meeting→CloudMeet, interested→rep,
  not-interested/unsubscribe→suppression_service, referral→re-target).
- **ChampOracle:** import `content_quality` into the SSR sim as the message-quality prior.

## Roadmap (bigger, later)
- Signal-triggered sequences (Harbinger why-now → auto-enroll).
- Peer-network warmup (mailboxes warm each other) layered onto the ramp-governor.
- BANT/lead qualification scoring (from reply + enrichment).
- Multichannel (WhatsApp/Telegram/RCS) → ChampConnect, not ChampMail core.
