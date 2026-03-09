# E2E Testing Guide with Ethereal Mail

## Overview

This guide walks you through testing the complete ChampMail email campaign flow using Ethereal mail (ethereal.email), a fake SMTP service for testing. With test mode enabled, you can bypass DNS verification requirements and test the full workflow without needing real domain configuration.

## What You'll Test

- ✅ Uploading prospect lists via admin UI
- ✅ Selecting and processing prospect lists
- ✅ Configuring Ethereal SMTP credentials
- ✅ Creating email sequences
- ✅ Sending test emails to prospects
- ✅ Template personalization ({{variables}})
- ✅ Sequence timing and progression
- ✅ Open/click tracking

---

## Prerequisites

- Docker and docker-compose installed
- ChampMail running locally
- Admin account access

---

## Step 1: Enable Test Mode

### 1.1 Edit Your .env File

Create or edit the `.env` file in the project root:

```bash
TEST_MODE=true
ENVIRONMENT=development
```

### 1.2 Restart Services

```bash
docker-compose restart backend worker beat
```

### 1.3 Verify Test Mode is Active

Check the backend logs for the test mode warning banner:

```bash
docker-compose logs backend | grep "TEST MODE"
```

You should see:
```
⚠️  TEST MODE ENABLED - DNS VERIFICATION BYPASSED
This mode is for development testing only!
REMEMBER TO SET TEST_MODE=false AFTER TESTING IS COMPLETE
```

---

## Step 2: Create Ethereal Email Account

### 2.1 Visit Ethereal Mail

Go to https://ethereal.email

### 2.2 Create a Test Account

Click **"Create Ethereal Account"** button

### 2.3 Save Your Credentials

You'll receive credentials like:
```
SMTP Host: smtp.ethereal.email
SMTP Port: 587
SMTP Security: STARTTLS
Username: [generated email like name.example@ethereal.email]
Password: [generated password]
```

**Important:** Keep this tab open - you'll need these credentials and will use the web interface to view received emails.

---

## Step 3: Configure ChampMail

### 3.1 Login to ChampMail

Navigate to http://localhost:3000 and login with admin credentials

### 3.2 Configure Email Settings

1. Navigate to **Settings** → **Email Accounts**
2. Click **Add Email Account**
3. Enter Ethereal credentials:
   - **SMTP Host:** smtp.ethereal.email
   - **SMTP Port:** 587
   - **SMTP Username:** [your ethereal email]
   - **SMTP Password:** [your ethereal password]
   - **Use TLS:** ✓ (checked)
   - **From Email:** [your ethereal email]
   - **From Name:** Test Sender
4. Click **Save**
5. Set as **Default Account** (if prompted)

### 3.3 Create a Test Domain (Optional)

1. Navigate to **Domains** → **Add Domain**
2. Enter domain name: `test.ethereal.email` (or any test name)
3. Click **Create**

**Note:** In test mode, the domain will remain "pending" status - this is OK! Test mode bypasses verification.

---

## Step 4: Upload Test Prospect List

### 4.1 Prepare Your CSV File

Create a CSV file with your employee/test data:

```csv
email,first_name,last_name,company_name,title
test1@example.com,John,Doe,Acme Corp,CEO
test2@example.com,Jane,Smith,Tech Inc,CTO
test3@example.com,Bob,Johnson,StartupXYZ,Founder
```

**Supported columns:**
- **Required:** `email`
- **Optional:** `first_name`, `last_name`, `company_name`, `company_domain`, `title`, `phone`, `linkedin_url`, `industry`, `company_size`

### 4.2 Upload via Admin UI

1. Navigate to **Admin** → **Prospect Lists**
2. Click **Upload Prospect List**
3. Drag & drop or select your CSV file
4. Wait for validation to complete
5. Click **Process List** to import prospects into database

### 4.3 Verify Upload Success

- List status should change from `validated` → `processed`
- Check prospect count matches your CSV row count
- Click list name to view details (if available)

---

## Step 5: Create Email Sequence

### 5.1 Navigate to Sequence Builder

1. Go to **Sequences** → **New Sequence**
2. Enter sequence name: `Test Campaign`

### 5.2 Add Email Steps

**Step 1 - Initial Email:**
- **Subject:** `Hi {{first_name}}, quick intro`
- **Template:** Create or select a template
- **Body:**
  ```
  Hi {{first_name}},

  I noticed you're at {{company_name}} and wanted to reach out.

  [Your pitch here]

  Best,
  Test Sender
  ```
- **Delay:** Immediate (0 hours)

**Step 2 - Follow-up Email:**
- **Subject:** `Following up on my previous email`
- **Template:** Create or select a template
- **Delay:** 24 hours (or set to 1 minute for faster testing)

### 5.3 Configure Sequence Settings

- **From Name:** Test Sender
- **From Email:** [your ethereal email]
- **Reply To:** [your ethereal email]
- **Auto-pause on reply:** ✓ (checked)

### 5.4 Activate Sequence

Click **Activate Sequence**

---

## Step 6: Enroll Prospects

### 6.1 Enroll from Sequence Page

1. On the sequence page, click **Enroll Prospects**
2. Select your uploaded prospect list
3. Click **Enroll All** (or select specific prospects)

### 6.2 Verify Enrollment

- Check enrollment count
- Status should be `active` for enrolled prospects

---

## Step 7: Monitor Sends

### 7.1 Check Celery Worker Logs

Watch the worker logs for send activity:

```bash
docker-compose logs -f worker
```

Look for:
```
⚠️  TEST MODE: Sending email with DNS verification bypassed
Sending email to test1@example.com (sequence: [...], step: 1)
✓ Email sent successfully to test1@example.com (message_id: [...])
```

### 7.2 View Emails in Ethereal

1. Return to your Ethereal tab (https://ethereal.email/messages)
2. Click your test account email
3. View sent emails in the inbox
4. Click an email to view full content

### 7.3 Verify Template Personalization

Check that variables were replaced:
- `{{first_name}}` → `John`
- `{{company_name}}` → `Acme Corp`

### 7.4 Test Tracking Pixels

**Opens:**
- Emails should include a 1x1 tracking pixel in the body
- Check backend logs for open tracking (if you load images in Ethereal)

**Clicks:**
- Links should be wrapped with tracking URLs
- Format: `http://localhost:8000/api/v1/tracking/click?url=[original]&sig=[signature]`

---

## Step 8: Test Sequence Progression

### 8.1 Wait for Next Step

If you set a 24-hour delay, you'll need to wait. For faster testing:
1. Edit sequence step 2
2. Set delay to `1 minute` or `0.1 hours`
3. Save and re-enroll prospects

### 8.2 Verify Step 2 Sends

After the delay:
- Check worker logs for step 2 sends
- Check Ethereal inbox for follow-up emails
- Verify correct subject line and content

---

## Step 9: Test Reply Detection (Optional)

### 9.1 Simulate a Reply

From Ethereal's interface:
1. Click **Reply** on an email
2. Send a test reply

### 9.2 Check Auto-Pause

If reply detection is configured:
- Check if sequence paused for that prospect
- Check backend logs for reply detection

---

## Troubleshooting

### Issue: "No verified domains available for sending"

**Solution:**
- Verify `TEST_MODE=true` in `.env`
- Restart backend: `docker-compose restart backend worker beat`
- Check logs for test mode warning banner

### Issue: Emails not sending

**Checklist:**
1. ✓ Ethereal credentials configured in Email Settings
2. ✓ Sequence activated
3. ✓ Prospects enrolled with `active` status
4. ✓ Celery worker running: `docker-compose ps worker`
5. ✓ Check worker logs: `docker-compose logs worker`

### Issue: Template variables not resolving

**Solution:**
- Ensure CSV has correct column names: `first_name`, `last_name`, `company_name`
- Check case sensitivity (use lowercase column names)
- Verify prospect data in database

### Issue: Tracking links not working

**Solution:**
- Ensure `PUBLIC_API_URL` in `.env` is set correctly
- Check tracking service configuration
- Verify signature generation in logs

---

## Cleanup

### After Testing is Complete

**CRITICAL: Disable Test Mode**

1. Edit `.env`:
   ```bash
   TEST_MODE=false
   ```

2. Restart services:
   ```bash
   docker-compose restart backend worker beat
   ```

3. Verify test mode is disabled:
   ```bash
   docker-compose logs backend | grep "TEST MODE"
   ```
   (Should see no warnings)

### Delete Test Data

- Delete test prospect lists via Admin UI
- Delete test sequences
- Delete test domains (optional)

---

## Production Checklist

Before deploying to production:

- [ ] `TEST_MODE=false` in production `.env`
- [ ] Real domain configured with proper DNS records (MX, SPF, DKIM, DMARC)
- [ ] Production SMTP credentials configured (not Ethereal)
- [ ] Email accounts verified
- [ ] Prospect lists uploaded with real data
- [ ] Sequences tested and activated
- [ ] Rate limits configured appropriately
- [ ] Monitoring and alerts set up

---

## Next Steps

- Review sequence analytics in the dashboard
- Test A/B variants (if implemented)
- Configure warmup schedules for new domains
- Set up webhook integrations
- Configure reply detection with real IMAP

---

## Support

If you encounter issues:
1. Check Docker logs: `docker-compose logs`
2. Review backend logs: `docker-compose logs backend`
3. Check worker logs: `docker-compose logs worker`
4. Verify configuration: Review `.env` settings
5. Check database: Verify prospect/sequence records

For bugs or feature requests, see the main README.
