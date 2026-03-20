# SOP: ChampMail Campaign Execution

Standard Operating Procedure for preparing prospect lists, configuring email credentials, and executing bulk email campaigns.

---

## 1. Preparing Your Prospect List

### File Format

| Format | Extension | Notes |
|--------|-----------|-------|
| CSV | `.csv` | UTF-8 encoding recommended. Comma-separated. |
| Excel | `.xlsx` | First sheet is used. Header row required. |

**Limits:** Max 50 MB, max 100,000 rows per file.

### Required Columns

| Column | Required | Description |
|--------|----------|-------------|
| `email` | **Yes** | Prospect email address. Must be valid format. |
| `first_name` | No | Used in `{{first_name}}` template variables. |
| `last_name` | No | Used in `{{last_name}}` / `{{full_name}}`. |
| `company_name` | No | Used in `{{company}}` / `{{company_name}}`. |
| `company_domain` | No | e.g. `acme.com` (no `https://`). |
| `title` | No | Job title. Used in `{{title}}` / `{{job_title}}`. |
| `phone` | No | Any common format (digits, dashes, parens). |
| `linkedin_url` | No | Full URL starting with `https://`. |
| `industry` | No | Free text. |
| `company_size` | No | e.g. `50-200`, `1000+`. |

### Column Name Aliases

You don't need to match column names exactly. The system auto-maps common variations:

- `Email Address`, `e-mail`, `work email` -> `email`
- `First Name`, `firstname`, `fname` -> `first_name`
- `Last Name`, `lastname`, `surname` -> `last_name`
- `Company`, `Organization`, `org` -> `company_name`
- `Website`, `domain` -> `company_domain`
- `Job Title`, `role`, `position` -> `title`

If auto-mapping can't match a column, you'll be asked to map it manually in the UI.

### Common Mistakes

| Problem | What Happens | Fix |
|---------|-------------|-----|
| Missing `email` column | Upload rejected | Rename your email column to `email` or map it in the UI |
| Invalid email format | Row skipped with error | Clean emails before upload (check for spaces, typos) |
| Duplicate emails | Second occurrence skipped | De-duplicate your list before uploading |
| HTML in text fields | Tags are stripped automatically | No action needed, but clean data is preferred |
| Fields > 255 chars | Truncated with warning | Shorten field values |
| Wrong encoding | Garbled characters | Save as UTF-8 in Excel: File > Save As > CSV UTF-8 |

---

## 2. Configuring Email Credentials

### Where to Configure

**Settings > Email Settings** (legacy single-account)
or
**Settings > Email Accounts** (multi-account)

### SMTP Settings (Outbound)

| Field | Description | Example |
|-------|-------------|---------|
| SMTP Host | Your mail server hostname | `smtp.gmail.com` |
| SMTP Port | `587` for STARTTLS, `465` for SSL | `587` |
| Username | Usually your email address | `user@company.com` |
| Password | App password (not your login password for Gmail) | `xxxx-xxxx-xxxx-xxxx` |
| Use TLS | Enable for port 587 | Checked |

### IMAP Settings (Inbound / Reply Detection)

| Field | Description | Example |
|-------|-------------|---------|
| IMAP Host | Your mail server hostname | `imap.gmail.com` |
| IMAP Port | `993` for SSL | `993` |
| Username | Usually your email address | `user@company.com` |
| Password | Same app password | `xxxx-xxxx-xxxx-xxxx` |
| Use SSL | Enable for port 993 | Checked |
| Mailbox | Folder to monitor | `INBOX` |

### Common Provider Settings

**Gmail / Google Workspace:**
- SMTP: `smtp.gmail.com` : `587` (TLS)
- IMAP: `imap.gmail.com` : `993` (SSL)
- Requires App Password: https://myaccount.google.com/apppasswords

**Outlook / Microsoft 365:**
- SMTP: `smtp.office365.com` : `587` (TLS)
- IMAP: `outlook.office365.com` : `993` (SSL)

**Custom / Self-Hosted:**
- Ask your IT admin for the correct hostnames and ports.
- If using Stalwart or similar, the SMTP submission port is typically `587`.

### Testing Your Connection

1. Fill in all SMTP fields.
2. Click **Test SMTP Connection**.
3. A green banner = success. A red banner = failure with a diagnostic message.
4. Repeat for IMAP.

**The Test Connection button verifies:**
- DNS resolution of the hostname
- TCP connectivity to the port
- TLS/SSL handshake
- Authentication with your credentials
- (IMAP only) Mailbox selection

---

## 3. Executing a Campaign

### Step-by-Step Flow

1. **Upload Prospect List**
   - Go to **Prospect Lists > Upload List**.
   - Drop your `.csv` or `.xlsx` file.
   - The system reads headers and shows a column mapping screen.
   - Review auto-mapped columns (green = mapped, amber = skipped).
   - Fix any unmapped required columns (email must be mapped).
   - Click **Confirm & Upload**.

2. **Create a Campaign**
   - Go to **Campaigns > New Campaign**.
   - Name the campaign and select the uploaded prospect list.
   - Configure sender identity (From Name, From Address).
   - Set daily send limit (default: 100).

3. **Set Up Template**
   - Write your email template with variables: `{{first_name}}`, `{{company}}`, etc.
   - Or use the AI pipeline: describe your campaign and let AI generate personalized emails.

4. **Preview & Test**
   - Use **Send Test** to send a preview to your own email.
   - Verify formatting, variable substitution, and deliverability.

5. **Send**
   - Click **Send Campaign**.
   - Monitor the progress bar in real-time:
     - **Sent** (green) - Successfully delivered
     - **Failed** (red) - Delivery failed after retries
     - **Skipped** (grey) - Invalid email or duplicate
   - Use **Pause** to stop sending (you can resume later).
   - Use **Cancel** to abort permanently.

### What Happens Behind the Scenes

- Emails are sent one at a time with a 2-second throttle between sends.
- Transient SMTP errors (timeout, temporary rejection) are retried up to 3 times with exponential backoff (2s, 4s, 8s).
- If the SMTP server fails 5 times in a row, a **circuit breaker** pauses sending for 60 seconds.
- After 3 circuit breaker trips (15 consecutive failures), the campaign aborts with status `failed_smtp`.
- When paused or aborted, the system saves its position. Resuming picks up where it left off.

---

## 4. Troubleshooting

### Upload Errors

| Error | Cause | Fix |
|-------|-------|-----|
| "Unsupported file type" | Not a `.csv` or `.xlsx` file | Re-export as CSV or XLSX |
| "File is empty" | 0 bytes | Check the file has data |
| "File has no headers" | First row is blank | Add a header row |
| "Could not find an 'email' column" | No column maps to email | Rename column to `email` or use column mapping |
| "Row N: Invalid email" | Bad email format | Fix the email in your source data |
| "Row N: Duplicate email" | Same email appears twice | De-duplicate before upload |

### SMTP Errors

| Error | Cause | Fix |
|-------|-------|-----|
| "Authentication failed" | Wrong username or password | Double-check credentials. Gmail requires an App Password. |
| "Connection timed out" | Server unreachable or port blocked | Verify hostname/port. Check firewall rules. |
| "DNS lookup failed" | Bad hostname | Check spelling of the SMTP host. |
| "Connection refused" | Server down or wrong port | Try port 465 instead of 587 (or vice versa). |
| "SSL certificate verification failed" | Self-signed or expired cert | Contact your mail server admin. |
| "Server disconnected unexpectedly" | TLS mismatch | Toggle the TLS checkbox. Port 587 = STARTTLS, Port 465 = SSL. |

### Campaign Send Errors

| Error | Cause | Fix |
|-------|-------|-----|
| "No enrolled recipients" | Prospect list not linked or no active prospects | Check campaign has a prospect list with active contacts |
| "Circuit breaker tripped" | SMTP server repeatedly failing | Check server status, wait, then resume |
| "Disposable email not allowed" | Prospect uses throwaway email | Remove these contacts from your list |
| Campaign stuck at "sending" | Background process crashed | Pause, wait 30s, then resume |

---

## Quick Reference

```
Upload: Prospect Lists > Upload List > Map Columns > Confirm
Config: Settings > Email Settings > Fill SMTP/IMAP > Test Connection
Send:   Campaigns > New > Select List > Template > Send
Monitor: Campaign Detail > Progress Bar (polls every 3s)
Pause:  Campaign Detail > Pause button
Resume: Campaign Detail > Resume button (picks up where it left off)
```
