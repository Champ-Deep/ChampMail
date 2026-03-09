# Test Mode for Ethereal Mail Testing - Design Document

**Date:** 2026-03-10
**Status:** Approved
**Author:** Claude (with user input)

---

## Context

ChampMail requires DNS verification (MX, SPF, DKIM, DMARC records) for all sending domains before emails can be sent. This prevents testing the complete email campaign flow with services like Ethereal mail (ethereal.email), which don't have real DNS records.

**The Problem:**
- Domains must be "verified" status to send emails
- Test domains (ethereal.email, test.champmail.test) fail DNS verification
- Cannot test end-to-end email flow without real domain configuration
- Blocks local development testing of prospect lists, sequences, and campaigns

**The Need:**
Enable full E2E testing of the ChampMail email flow using Ethereal mail or other test SMTP services without requiring real DNS configuration.

---

## Requirements

### Functional Requirements

1. **DNS Bypass:** Allow sending emails through unverified domains when test mode is enabled
2. **Email Flow:** Support complete workflow:
   - Upload prospect lists via admin UI
   - Configure Ethereal SMTP credentials
   - Create and activate email sequences
   - Send emails to prospects
   - Track opens/clicks
   - Test sequence progression
3. **User Configuration:** Users should manually configure Ethereal SMTP via existing UI (not auto-configured)
4. **Testing Scope:** Enable testing of:
   - Template personalization ({{variables}})
   - Sequence timing and delays
   - Email delivery
   - Open/click tracking

### Non-Functional Requirements

1. **Safety:** Test mode should only work in local development
2. **Visibility:** Clear warnings when test mode is active
3. **Logging:** Comprehensive logging of all email sends (test mode or not)
4. **Simplicity:** Single environment variable check (no complex conditions)
5. **Reminder:** User must be reminded to disable test mode after testing

---

## Design Decisions

### Approved Approach

**Single Environment Variable:** `TEST_MODE=true` (no ENVIRONMENT=development check)

**Rationale:**
- Simple to understand and configure
- Easy to toggle on/off
- User takes responsibility for production safety
- Clear warnings make test mode obvious

### DNS Bypass Strategy

**Implementation:**
1. Add `test_mode: bool = False` to config
2. Create utility helper `is_test_mode_enabled()` that checks `settings.test_mode`
3. Modify `domain_service.get_verified_domains()` to return ALL domains (not just verified) when test mode is enabled
4. Modify `domain_rotation.select_domain()` to use test domain ID if no domains exist in test mode
5. Add test mode warnings to all email send operations

**Why this works:**
- Campaign send service uses `domain_rotator.select_domain()`
- Sequence tasks use `domain_rotator.select_domain()`
- Both rely on `domain_service.get_verified_domains()`
- Bypassing the "verified" filter allows unverified domains to be used

### Logging Strategy

**Test Mode Logging (when active):**
- Startup warning banner (70 char wide, impossible to miss)
- Log warning on every DNS bypass operation
- Log warning on every email send

**General Logging (always active):**
- Log all domain selection operations
- Log all email send attempts (success/failure)
- Log sequence step execution
- Log prospect enrollment
- Include email addresses and message IDs

---

## Implementation

### Files Modified

1. **`/backend/app/core/config.py`**
   - Add `test_mode: bool = False` field
   - No validation required (user responsibility)

2. **`/backend/app/utils/test_mode.py`** (NEW)
   - `is_test_mode_enabled()` - Returns `settings.test_mode` with warning log
   - `get_test_mode_domain_id()` - Returns fixed UUID for fallback

3. **`/backend/app/services/domain_service.py`**
   - Import `is_test_mode_enabled`
   - Modify `get_verified_domains()` to bypass status filter in test mode
   - Add logging for domain count

4. **`/backend/app/services/domain_rotation.py`**
   - Import `is_test_mode_enabled`, `get_test_mode_domain_id`
   - Add test mode fallback when no domains found
   - Add logging for domain selection
   - Fix dictionary access (domains are now dicts, not objects)

5. **`/backend/app/tasks/sequences.py`**
   - Import `is_test_mode_enabled`
   - Add test mode warning before sends
   - Add comprehensive logging (email address, sequence ID, step order, message ID)

6. **`/backend/app/services/campaign_send_service.py`**
   - Import `is_test_mode_enabled`
   - Add test mode warning before sends
   - Improve logging (include email addresses, message IDs)

7. **`/backend/app/main.py`**
   - Import `is_test_mode_enabled`
   - Add startup warning banner when test mode active

8. **`/docker-compose.yml`**
   - Add `TEST_MODE: ${TEST_MODE:-false}` to backend, worker, beat services
   - Add full environment config to worker and beat (needed for test mode detection)

9. **`/.env.example`**
   - Add `TEST_MODE=false` with documentation and warning comment

10. **`/docs/E2E_TESTING_GUIDE.md`** (NEW)
    - Comprehensive testing guide
    - Step-by-step Ethereal setup
    - Troubleshooting section
    - Cleanup instructions

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        TEST MODE FLOW                        │
└─────────────────────────────────────────────────────────────┘

  User uploads CSV → Admin UI → prospect_lists table
                                        ↓
                        User creates sequence via UI
                                        ↓
                        User enrolls prospects
                                        ↓
                    Celery task: execute_pending_steps()
                                        ↓
                      Check is_test_mode_enabled()
                                ↓              ↓
                           YES (warn)      NO (normal)
                                ↓              ↓
              domain_service.get_verified_domains()
                     ↓                         ↓
         Return ALL domains          Return verified only
                     ↓                         ↓
              domain_rotator.select_domain()
                                ↓
                    Send email via mail_engine
                                ↓
                    Log: ✓ Email sent to [email]
                                ↓
                      Email delivered to Ethereal
```

---

## Safety Mechanisms

1. **Default False:** `TEST_MODE` defaults to false in all configs
2. **Startup Warning:** 70-character banner on backend startup (impossible to miss)
3. **Per-Send Warnings:** Log warning on every email send in test mode
4. **Documentation:** Clear instructions to disable after testing
5. **User Reminder:** Added todo item to remind user to disable

**What we DON'T enforce:**
- No ENVIRONMENT=development check (per user request)
- No production safeguards (user responsibility)
- User must remember to disable

---

## Testing Plan

### Manual E2E Test

1. Set `TEST_MODE=true` in `.env`
2. Restart: `docker-compose restart backend worker beat`
3. Verify startup banner in logs
4. Create Ethereal account at ethereal.email
5. Configure Ethereal SMTP via Settings → Email Accounts UI
6. Create test domain (any name, will stay "pending")
7. Upload CSV with test prospects via Admin UI
8. Process prospect list
9. Create email sequence with 2 steps via UI
10. Enroll prospects
11. Verify emails in Ethereal inbox
12. Check template personalization worked
13. Verify tracking pixels/links injected
14. Wait for step 2 (or set short delay)
15. Verify sequence progression
16. Set `TEST_MODE=false`
17. Restart services
18. Verify no test mode warnings

---

## Success Criteria

- [x] TEST_MODE environment variable configurable
- [x] DNS verification bypassed when enabled
- [x] Unverified domains can send emails
- [x] Complete E2E flow works with Ethereal
- [x] Template personalization works
- [x] Sequence progression works
- [x] Tracking works (opens/clicks)
- [x] Clear warnings when test mode active
- [x] Comprehensive logging added
- [x] Documentation complete
- [x] User reminded to disable after testing

---

## Future Enhancements

1. **Auto-disable:** Add expiration timer for test mode (e.g., auto-disable after 24 hours)
2. **Env validation:** Optionally enforce ENVIRONMENT=development check via config flag
3. **Test mode UI:** Add visual indicator in frontend when test mode is active
4. **Audit log:** Record when test mode is enabled/disabled
5. **Integration tests:** Add automated tests for test mode flow

---

## Rollback Plan

If issues arise:

1. Set `TEST_MODE=false` in `.env`
2. Restart services: `docker-compose restart backend worker beat`
3. Revert code changes:
   ```bash
   git revert [commit-hash]
   ```

No database migrations required - all changes are code-only.

---

## Conclusion

Test mode enables local E2E testing of ChampMail's email flow without requiring real DNS configuration. The implementation is simple, safe (with clear warnings), and well-documented. Users can now test prospect uploads, sequence creation, email personalization, and delivery using Ethereal mail or similar services.

**Key Takeaway:** This unblocks development testing while maintaining production safety through visibility (warnings) and user responsibility.
