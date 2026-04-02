---
name: ChampMail CLI
description: Command-line interface for ChampMail — AI-powered cold-email outreach platform
version: 0.1.0
entry_point: champmail
---

# ChampMail CLI

Enterprise cold-email outreach platform accessible from the terminal or AI agents.

## Installation

```bash
cd backend
pip install -e .
# or without install:
python -m cli.champmail_cli
```

## Quick Start (any terminal)

```bash
# Install globally (one-time)
ln -sf ~/Desktop/ChampMail-main-1/champmail ~/.local/bin/champmail

# Then from any directory:
champmail auth login --email admin@champions.dev --password admin123
champmail chat           # conversational AI interface ← start here
```

## Authentication (required first)

```bash
champmail auth login --email admin@champions.dev --password admin123
champmail auth whoami
champmail auth logout
```

## Admin Setup (run once before outreach)

```bash
champmail setup domain   --name outreach.yourcompany.com --provider cloudflare
champmail setup smtp     --host smtp.ethereal.email --port 587 --username U --password P --from-email E
champmail setup imap     --host imap.ethereal.email --port 993 --username U --password P
champmail setup prospect --industry SaaS --source linkedin
champmail setup campaign --from-name "Your Name" --from-email you@company.com --daily-limit 50
champmail setup ai       --api-key sk-or-... --model openai/gpt-4.1-mini
champmail setup show     # view all config (passwords hidden)
champmail setup test smtp|imap|all   # verify connections
```

## Conversational Chat Interface

```bash
champmail chat           # start conversational session (animated intro, AI-guided flow)
champmail chat --setup   # start with setup wizard
champmail chat --plain   # skip animated intro (CI/pipe-friendly)
```

Inside chat: type naturally. Built-in commands:
- `status`  — show setup completion status
- `help`    — command reference
- `clear`   — clear conversation history
- `exit`    — quit

## Interactive REPL

```bash
champmail repl
# starts interactive shell with history, auto-suggest, and completion
```

## Global Flags

| Flag | Description |
|------|-------------|
| `--json` | Machine-readable JSON output (agent-native) |
| `--version` | Print version |
| `--help` | Show help |

---

## Command Reference

### auth

```
champmail auth login   --email EMAIL --password PASSWORD
champmail auth logout
champmail auth whoami
champmail auth register --email EMAIL --password PW --name NAME [--role user|admin]
```

### campaigns

```
champmail campaigns list   [--status STATUS] [--limit N] [--offset N] [--mine]
champmail campaigns create --name NAME [--description D] [--from-name N]
                           [--from-address A] [--daily-limit N]
                           [--template-id ID] [--sequence-id ID]
champmail campaigns get    CAMPAIGN_ID
champmail campaigns stats  CAMPAIGN_ID
champmail campaigns send   CAMPAIGN_ID
champmail campaigns pause  CAMPAIGN_ID
champmail campaigns resume CAMPAIGN_ID
champmail campaigns recipients add   CAMPAIGN_ID --prospect-ids id1,id2
champmail campaigns recipients list  CAMPAIGN_ID [--status STATUS] [--limit N]
```

### prospects

```
champmail prospects list          [--query Q] [--industry I] [--limit N] [--skip N]
champmail prospects get           EMAIL
champmail prospects create        --email EMAIL [--first-name F] [--last-name L]
                                  [--title T] [--company-name N] [--company-domain D]
                                  [--industry I]
champmail prospects update        EMAIL [--first-name F] [--last-name L] [--title T]
champmail prospects delete        EMAIL [--yes]
champmail prospects bulk-import   --file prospects.csv
champmail prospects timeline      EMAIL
```

CSV format for bulk-import:
```
email,first_name,last_name,title,company_domain,industry
john@acme.com,John,Doe,CTO,acme.com,SaaS
```

### sequences

```
champmail sequences list      [--status STATUS] [--limit N]
champmail sequences get       SEQUENCE_ID
champmail sequences create    --name NAME [--description D] [--steps-file steps.json]
champmail sequences pause     SEQUENCE_ID
champmail sequences resume    SEQUENCE_ID
champmail sequences enroll    SEQUENCE_ID --emails email1,email2
champmail sequences analytics SEQUENCE_ID
```

Steps JSON format (steps.json):
```json
[
  {"name": "Intro", "subject": "Hi {{first_name}}", "body": "<p>Hello</p>", "delay_hours": 0},
  {"name": "Follow-up", "subject": "Quick follow-up", "body": "<p>Just checking in</p>", "delay_hours": 72}
]
```

### domains

```
champmail domains list
champmail domains get      DOMAIN_ID
champmail domains add      --domain example.com [--provider cloudflare]
champmail domains validate DOMAIN_ID
champmail domains delete   DOMAIN_ID [--yes]
```

### templates

```
champmail templates list
champmail templates get    TEMPLATE_ID
champmail templates create --name NAME --subject SUBJECT --html-file body.html
champmail templates delete TEMPLATE_ID [--yes]
```

### analytics

```
champmail analytics campaign CAMPAIGN_ID
champmail analytics tracking CAMPAIGN_ID
champmail analytics summary  [--limit N]
```

### admin  *(admin role required)*

```
champmail admin users list       [--limit N]
champmail admin users get        USER_ID
champmail admin users delete     USER_ID [--yes]
champmail admin prospects list   [--assigned-to USER_ID] [--limit N]
champmail admin prospects assign PROSPECT_EMAIL --user USER_ID
```

### send

```
champmail send verify                          # test SMTP connection
champmail send email  --to EMAIL --subject SUBJ [--body HTML] [--body-file file.html]
                      [--from-name NAME] [--from-email EMAIL]
champmail send imap-check  [--limit N]         # list inbox messages (Ethereal)
champmail send campaign CAMPAIGN_ID            # trigger campaign → Celery worker
```

### outreach  *(end-to-end cold outreach pipeline)*

Full 6-step pipeline: prospect → research → questionnaire → AI email prep → send → reply tracking.

```
# Run all steps interactively in one wizard:
champmail outreach start EMAIL [--first-name F] [--last-name L] [--title T]
                               [--company C] [--domain D] [--industry I]
                               [--answers-file answers.json]
                               [--draft-file draft.json]
                               [--skip-send]

# Or run each step independently:
champmail outreach prospect      EMAIL  [--first-name F] [--last-name L] [--title T]
                                        [--phone P] [--linkedin URL]
                                        [--company C] [--domain D] [--industry I]
champmail outreach research      EMAIL
champmail outreach questionnaire EMAIL  [--answers-file answers.json]
champmail outreach prep          EMAIL  [--subject S] [--save draft.json]
champmail outreach send          EMAIL  [--subject S] [--body HTML]
                                        [--draft-file draft.json]
                                        [--from-name N] [--from-email E]
champmail outreach replies       EMAIL  [--limit N]
champmail outreach status        EMAIL
```

Questionnaire answers JSON format (for --answers-file):
```json
{
  "goal":       "book a demo",
  "pain_point": "manual outreach takes too long",
  "value_prop": "AI-personalised cold email at scale",
  "context":    "they just raised a Series A",
  "cta":        "15-min call this week",
  "tone":       "casual",
  "sender":     "Alex, Head of Growth",
  "from_email": "alex@yourcompany.com"
}
```

### tunnel

```
champmail tunnel start  [--port 8000] [--subdomain myapp] [--wait 15]
champmail tunnel status
```

### health

```
champmail health check
```

---

## JSON Output Examples

All commands support `--json` for agent-parseable output:

```bash
champmail --json campaigns list
# {"ok": true, "campaigns": [...], "total": 5}

champmail --json auth login --email admin@champions.dev --password admin123
# {"ok": true, "email": "admin@champions.dev", "role": "admin", "user_id": "..."}

champmail --json health check
# {"ok": true, "status": "healthy", "postgres": "ok", "redis": "ok", "champgraph": "ok"}
```

## Session Storage

Session token is stored in `~/.champmail/session.json`.
Command history is saved to `~/.champmail/history`.

## Architecture Notes

- CLI invokes backend service layer **directly** (no HTTP round-trip)
- Async operations use `asyncio.run_until_complete` under the hood
- All mutations commit via SQLAlchemy async sessions
- Graph operations go through ChampGraph HTTP API (`app.db.falkordb`)
- Celery tasks (sending, warmup, sequences) run in background workers —
  the CLI triggers state changes; actual sending is done by workers
