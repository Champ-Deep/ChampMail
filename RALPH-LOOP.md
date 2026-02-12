# Ralph Loop: Champion's Email Engine Execution Plan

## What is the Ralph Loop?

An iterative execution framework where each cycle:
1. **R**eview - Assess current state and blockers
2. **A**nalyze - Break down next achievable milestone
3. **L**aunch - Execute with smallest viable increment
4. **P**rove - Validate it works with real test
5. **H**armonize - Integrate with existing components

---

## Current State Assessment

### What Exists (Keep)
| Asset | Path | Value |
|-------|------|-------|
| N8N Workflow | `Email Automation/Email Automation.json` | Reusable patterns |
| AI Prompts | Inside workflow | Well-designed |
| Pinecone Integration | Inside workflow | Can bridge to FalkorDB later |

### What's Missing (Build)
| Component | Priority | Dependency |
|-----------|----------|------------|
| BillionMail | P0 | None (can deploy standalone) |
| FalkorDB + Graphiti | P0 | None (can deploy standalone) |
| FastAPI Backend | P0 | FalkorDB |
| Next.js Frontend | P1 | FastAPI |
| Multi-step Sequences | P0 | n8n + FastAPI |
| CloudMeet Calendar | P1 | FastAPI + Sequences |

---

## Ralph Loop Cycle 1: Foundation Infrastructure [COMPLETED 2026-01-13]

### Goal: Get BillionMail + FalkorDB running

**R - Review:**
- No self-hosted email infrastructure
- No graph database
- Gmail has 500 emails/day limit

**A - Analyze:**
- BillionMail: Docker deployment, ~2-4 hours (deferred - using Gmail for POC)
- FalkorDB: Docker deployment, ~1-2 hours
- Both can run on Railway or local Docker

**L - Launch (Completed):**
```bash
# Infrastructure deployed at: /Users/champion/ChampMail/infrastructure/
cd /Users/champion/ChampMail/infrastructure
docker compose up -d
```

**P - Prove:**
- [x] FalkorDB: Create test node, query it back
- [x] FalkorDB: WORKS_AT relationship tested (Prospect -> Company)
- [x] Redis Cache: SET/GET operations verified
- [ ] BillionMail: Deferred to later (requires domain setup)

**H - Harmonize:**
- FalkorDB running on localhost:6379
- FalkorDB Browser UI at localhost:3000
- Redis Cache on localhost:6380
- Ready for Cycle 2: FastAPI Backend

### Infrastructure Status
| Service | Port | Status |
|---------|------|--------|
| FalkorDB | 6379 | Running |
| FalkorDB Browser | 3000 | Running |
| Redis Cache | 6380 | Running |
| BillionMail | - | Deferred |

---

## Ralph Loop Cycle 2: FastAPI Backend Scaffold

### Goal: API layer that connects n8n, FalkorDB, and future frontend

**R - Review:**
- N8N handles workflows but no REST API
- Frontend will need endpoints
- Graph queries need abstraction

**A - Analyze:**
Minimum viable endpoints:
- `POST /api/v1/prospects` - Create prospect
- `GET /api/v1/prospects/{id}` - Get with graph context
- `POST /api/v1/sequences` - Create sequence
- `POST /api/v1/sequences/{id}/enroll` - Enroll prospects
- `POST /api/v1/graph/ingest` - Add to knowledge graph

**L - Launch:**
Create FastAPI project with:
- Graphiti client integration
- n8n webhook triggers
- Basic auth (JWT)

**P - Prove:**
- [ ] POST prospect → appears in FalkorDB
- [ ] GET prospect → returns with relationships
- [ ] Trigger n8n workflow via API

**H - Harmonize:**
- N8N workflows call FastAPI instead of direct Pinecone
- FastAPI becomes single source of truth

---

## Ralph Loop Cycle 3: Multi-Step Sequence Engine

### Goal: Core value prop - automated email sequences

**R - Review:**
- Current workflow: single email only
- PRD requires 1-10 step sequences
- Need conditional branching (opened, clicked, replied)

**A - Analyze:**
Sequence state machine:
```
ENROLLED → STEP_1 → WAITING → STEP_2 → ... → COMPLETED
                  ↓
              REPLIED (pause)
```

**L - Launch:**
1. Create sequence data model in FastAPI
2. Build n8n workflow that:
   - Reads sequence definition
   - Executes current step
   - Schedules next step (delay)
   - Handles pause conditions

**P - Prove:**
- [ ] Enroll prospect in 3-step sequence
- [ ] Verify each email sends with correct delay
- [ ] Simulate reply → sequence pauses

**H - Harmonize:**
- Migrate existing single-email workflow into step 1 of sequence
- All personalization logic reused

---

## Ralph Loop Cycle 4: CloudMeet Calendar Integration

### Goal: Native meeting scheduling with auto-booking links in email sequences

**R - Review:**
- No meeting scheduling capability
- Manual calendar coordination required
- No way to auto-pause sequences when meeting is booked
- Prospects must email back to schedule calls

**A - Analyze:**
CloudMeet (open-source Calendly alternative):
- Runs on Cloudflare free tier (Pages + D1 + Workers)
- Supports Google Calendar + Outlook simultaneously
- Auto-generates Google Meet / MS Teams links
- MIT licensed, fully customizable
- Webhook table exists but needs dispatch implementation

Integration architecture:
```
Email Sequence → Booking Link CTA → CloudMeet → Webhook → N8N → Pause Sequence
                                                              → Update FalkorDB
                                                              → Send Confirmation
```

**L - Launch:**

Phase 1: Deploy CloudMeet
```bash
# Clone and configure
cd /Users/champion/ChampMail
git clone https://github.com/dennisklappe/CloudMeet.git  # Already done
cd CloudMeet

# Configure environment
cp .env.example .env
# Set: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
# Set: MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET (for Outlook)
# Set: APP_URL, JWT_SECRET

# Deploy to Cloudflare
npm install
npm run db:init:remote
npm run deploy
```

Phase 2: Add Webhook Dispatch (Fork CloudMeet)
- Create `/src/lib/server/webhooks.ts` - dispatch function with HMAC signing
- Modify `/src/routes/api/bookings/+server.ts` (line 227) - fire `booking.created`
- Modify `/src/routes/api/bookings/cancel/+server.ts` (line 118) - fire `booking.cancelled`
- Modify `/src/routes/api/bookings/reschedule/+server.ts` (line 173) - fire `booking.rescheduled`

Phase 3: N8N Webhook Receiver
- Create webhook endpoint in n8n: `POST /webhook/cloudmeet-booking`
- On `booking.created`:
  - Lookup prospect by email in FalkorDB
  - Pause active sequence for prospect
  - Update prospect status: `meeting_booked`
  - Store meeting details (time, URL, type)
  - Send branded confirmation via BillionMail/Gmail

Phase 4: Email Template Integration
- Add booking link variable to email templates: `{{booking_link}}`
- N8N injects personalized URL: `https://meet.yourdomain.com/book/discovery-call?email={{email}}&name={{name}}`

**P - Prove:**
- [ ] CloudMeet deployed to Cloudflare Pages
- [ ] Google Calendar connected, availability shows correctly
- [ ] Outlook Calendar connected (optional)
- [ ] Test booking creates Google Meet link
- [ ] Webhook fires to n8n on booking
- [ ] Sequence pauses when meeting booked
- [ ] FalkorDB updated with meeting status
- [ ] Booking link in email template works

**H - Harmonize:**
- Booking links auto-inserted in sequence step CTAs
- Meeting data flows to knowledge graph (FalkorDB)
- Reply detection (Cycle 5) can distinguish replies vs. bookings
- Frontend (Cycle 6) shows meeting status per prospect

### CloudMeet Webhook Payloads

```json
// booking.created
{
  "event": "booking.created",
  "timestamp": "2026-01-15T10:30:00Z",
  "signature": "sha256=...",
  "data": {
    "bookingId": "abc-123",
    "eventType": "discovery-call",
    "attendeeName": "John Doe",
    "attendeeEmail": "john@acme.com",
    "startTime": "2026-01-17T14:00:00Z",
    "endTime": "2026-01-17T14:30:00Z",
    "meetingUrl": "https://meet.google.com/xxx-yyy-zzz",
    "meetingType": "google_meet",
    "notes": "Interested in enterprise plan"
  }
}
```

### Files to Modify in CloudMeet

| File | Change | Purpose |
|------|--------|---------|
| `src/lib/server/webhooks.ts` | Create new | Webhook dispatch + HMAC signing |
| `src/routes/api/bookings/+server.ts` | Add dispatch call (line 227) | Fire on booking created |
| `src/routes/api/bookings/cancel/+server.ts` | Add dispatch call (line 118) | Fire on cancellation |
| `src/routes/api/bookings/reschedule/+server.ts` | Add dispatch call (line 173) | Fire on reschedule |
| `src/routes/api/webhooks/+server.ts` | Create new | CRUD for webhook management |
| `src/routes/dashboard/webhooks/+page.svelte` | Create new | UI to configure webhooks |

---

## Ralph Loop Cycle 5: Reply Detection

### Goal: Auto-detect replies and classify sentiment

**R - Review:**
- No IMAP monitoring
- Sequences don't pause on reply
- Manual tracking required

**A - Analyze:**
- Need IMAP connection to Gmail/BillionMail
- Poll for new replies (every 5 min)
- Claude classifies: positive, negative, neutral, OOO

**L - Launch:**
1. Add IMAP node to n8n
2. Create reply-matching logic (thread ID or subject)
3. Claude sentiment classification
4. Update sequence state

**P - Prove:**
- [ ] Send test email to self
- [ ] Reply to it
- [ ] System detects, classifies, pauses sequence

**H - Harmonize:**
- Reply data feeds back to knowledge graph
- Deliverability dashboard shows reply rates

---

## Ralph Loop Cycle 6: Frontend MVP

### Goal: Visual interface for non-technical users

**R - Review:**
- No UI exists
- Users must use n8n directly
- Analytics not visualized

**A - Analyze:**
MVP screens:
1. Dashboard (metrics overview)
2. Prospects list (import, view)
3. Sequence builder (visual editor)
4. Templates (WYSIWYG editor)

**L - Launch:**
```bash
npx create-next-app@latest champions-frontend
# shadcn/ui, TailwindCSS, TanStack Query
```

**P - Prove:**
- [ ] Create sequence from UI
- [ ] Import prospects from CSV
- [ ] View real-time analytics

**H - Harmonize:**
- Frontend calls FastAPI exclusively
- n8n handles background execution only

---

## Execution Priority Matrix

| Cycle | Effort | Impact | Do When? |
|-------|--------|--------|----------|
| 1. Infrastructure | Medium | Critical | ✅ DONE |
| 2. FastAPI | Medium | High | Next |
| 3. Sequences | High | Critical | After FastAPI |
| 4. CloudMeet Calendar | Medium | High | After Sequences |
| 5. Reply Detection | Medium | High | After CloudMeet |
| 6. Frontend | High | High | After Reply Detection |

---

## Quick Wins (Do Today)

1. **Deploy FalkorDB on Railway** (~30 min)
   - Immediate graph database capability

2. **Test BillionMail Docker locally** (~1 hour)
   - Validate self-hosted email works

3. **Create FastAPI skeleton** (~1 hour)
   - Even empty, establishes architecture

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-01-13 | Keep N8N workflow patterns | Prompts and data flow are solid |
| 2026-01-13 | Deprecate roadmap app | Unrelated to email engine |
| 2026-01-13 | Replace Pinecone with FalkorDB | PRD requires knowledge graph |
| 2026-01-13 | Start with BillionMail | Gmail limits won't scale |
| 2026-01-14 | Adopt CloudMeet for calendar | Open source, Cloudflare free tier, Google+Outlook support |
| 2026-01-14 | Fork CloudMeet for webhooks | Webhook table exists but dispatch code needs to be added |

---

## Next Action

**Start Cycle 2: FastAPI Backend**
1. Create FastAPI project skeleton in `/Users/champion/ChampMail/backend/`
2. Add FalkorDB connection (localhost:6379)
3. Implement `/api/v1/prospects` endpoints
4. Add n8n webhook trigger endpoint

**Parallel: Prepare CloudMeet (Cycle 4)**
1. Configure CloudMeet environment variables
2. Set up Google Cloud OAuth credentials
3. Deploy to Cloudflare Pages
4. Fork and add webhook dispatch code

Then return to this document to update progress.
