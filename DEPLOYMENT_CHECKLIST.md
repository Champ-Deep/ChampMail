# ChampMail MVP Deployment Checklist

This checklist guides you through deploying ChampMail to production on Railway or Render.

## 📋 Pre-Deployment

### 1. Critical Bug Fixes
- [x] Fixed runtime crashes in `backend/app/tasks/analytics.py` (timedelta import, async_session_maker)
- [x] Implemented HMAC webhook signature verification in `backend/app/api/v1/webhooks.py`
- [x] Added production settings validation in `backend/app/core/config.py`
- [x] Restricted CORS to specific domains in `backend/app/main.py`

### 2. Database Migrations
- [x] Created `002_domains_tables.py` migration
- [x] Created `003_email_accounts_table.py` migration
- [x] Created `004_send_logs_table.py` migration
- [ ] Run migrations locally to test:
  ```bash
  cd backend
  alembic upgrade head
  ```

### 3. Security Secrets (REQUIRED)

Generate all required secrets **before** deployment:

```bash
# JWT Secret (32+ characters)
openssl rand -hex 32

# Webhook Secret
openssl rand -hex 32

# Email Encryption Key (Fernet)
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# PostgreSQL Password (if not using managed database)
openssl rand -base64 24
```

**Save these securely** - you'll need them in the next step.

### 4. Environment Variables

Set these in Railway/Render dashboard:

#### Application
- [ ] `ENVIRONMENT=production`
- [ ] `DEBUG=false`
- [ ] `JWT_SECRET_KEY=<generated-secret-32-chars>`
- [ ] `WEBHOOK_SECRET=<generated-secret>`
- [ ] `EMAIL_ENCRYPTION_KEY=<generated-fernet-key>`
- [ ] `FRONTEND_URL=https://your-frontend-domain.com`

#### Database (auto-provided by Railway/Render PostgreSQL)
- [ ] `DATABASE_URL` (or separate POSTGRES_* vars)
- [ ] `POSTGRES_HOST`
- [ ] `POSTGRES_PORT`
- [ ] `POSTGRES_USER`
- [ ] `POSTGRES_PASSWORD`
- [ ] `POSTGRES_DB`

#### Redis (auto-provided by Railway/Render Redis)
- [ ] `REDIS_URL`
- [ ] `REDIS_HOST`
- [ ] `REDIS_PORT`

#### External APIs (Optional for MVP)
- [ ] `ANTHROPIC_API_KEY` (for AI features)
- [ ] `OPENAI_API_KEY` (for embeddings)
- [ ] `NAMECHEAP_API_KEY` (for domain purchases)
- [ ] `CLOUDFLARE_API_TOKEN` (for DNS management)

---

## 🚀 Deployment

### Option A: Railway Deployment

1. **Install Railway CLI**
   ```bash
   npm install -g @railway/cli
   railway login
   ```

2. **Create New Project**
   ```bash
   railway init
   ```

3. **Add PostgreSQL Database**
   - In Railway dashboard, click "New" → "Database" → "PostgreSQL"
   - Railway auto-configures `DATABASE_URL` and `POSTGRES_*` variables

4. **Add Redis Cache**
   - Click "New" → "Database" → "Redis"
   - Railway auto-configures `REDIS_URL`

5. **Deploy Backend**
   - Push to Railway:
     ```bash
     railway up
     ```
   - Or connect GitHub repo in Railway dashboard

6. **Set Environment Variables**
   - Go to project → Variables tab
   - Add all required secrets from step 3-4 above
   - Update `FRONTEND_URL` after frontend is deployed

7. **Deploy Frontend** (Separate Service)
   - Click "New Service"
   - Select Static Site
   - Build command: `cd frontend && npm install && npm run build`
   - Output directory: `frontend/dist`
   - Set `VITE_API_URL=https://your-backend-url.railway.app`

8. **Verify Deployment**
   - Check `/health` endpoint: `curl https://your-backend.railway.app/health`
   - Should return `{"status":"healthy",...}`

### Option B: Render Deployment

1. **Connect GitHub Repository**
   - Go to Render dashboard: https://dashboard.render.com
   - Click "New +" → "Blueprint"
   - Connect your GitHub repository
   - Render will detect `render.yaml` automatically

2. **Review Services**
   - Backend: Web Service (Docker)
   - Frontend: Static Site
   - PostgreSQL: Database
   - Redis: Cache

3. **Set Environment Variables**
   - Go to each service → Environment tab
   - Add secrets from step 3-4 above
   - Render auto-generates some secrets (check render.yaml)

4. **Deploy**
   - Click "Apply" to deploy all services
   - Wait for builds to complete (~5-10 minutes)

5. **Update Frontend URL**
   - After backend deploys, copy its URL
   - Go to frontend service → Environment
   - Set `VITE_API_URL=https://champmail-backend.onrender.com`
   - Trigger manual deploy

6. **Verify Deployment**
   - Check health: `curl https://champmail-backend.onrender.com/health`

---

## ✅ Post-Deployment Verification

### 1. Backend Health Check
```bash
curl https://your-backend-domain.com/health

# Expected Response:
# {
#   "status": "healthy",
#   "version": "0.1.0",
#   "environment": "production",
#   "checks": {
#     "postgres": {"status": "healthy"},
#     "redis": {"status": "healthy"},
#     "falkordb": {"status": "unavailable", "message": "..."}
#   }
# }
```

- [ ] Status is "healthy"
- [ ] PostgreSQL check passes
- [ ] Redis check passes
- [ ] FalkorDB shows "unavailable" (expected for MVP)

### 2. Frontend Accessibility
```bash
curl -I https://your-frontend-domain.com

# Expected: HTTP/2 200
```

- [ ] Frontend loads in browser
- [ ] No console errors (open DevTools)
- [ ] Assets load correctly (images, fonts)

### 3. CORS Configuration
Open browser DevTools → Network tab, then:

```javascript
fetch('https://your-backend-domain.com/api/v1/domains', {
  headers: { 'Content-Type': 'application/json' }
})
  .then(r => r.json())
  .then(console.log)
```

- [ ] Request completes successfully (not blocked by CORS)
- [ ] Response is JSON (not "CORS error")

### 4. Database Migration Status
SSH into backend container or check logs:

```bash
# Railway
railway run alembic current

# Render
# Check deployment logs for "Running migrations" message
```

- [ ] Shows migration `004_send_logs` (head)
- [ ] No migration errors in logs

### 5. API Authentication
```bash
# Register test user
curl -X POST https://your-backend-domain.com/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test123!","full_name":"Test User"}'

# Login
curl -X POST https://your-backend-domain.com/api/v1/auth/login \
  -d "username=test@example.com&password=Test123!"

# Expected: {"access_token":"...","token_type":"bearer"}
```

- [ ] User registration works
- [ ] User login returns JWT token

---

## 🧪 Functional Testing

Test critical user flows through the frontend UI:

### Test 1: User Registration & Login
- [ ] Navigate to frontend URL
- [ ] Click "Sign Up" or "Register"
- [ ] Create account with valid email/password
- [ ] Verify redirect to dashboard/login
- [ ] Log in with new credentials
- [ ] Verify access to dashboard

### Test 2: Domain Management
- [ ] Go to Domains page
- [ ] Click "Add Domain"
- [ ] Enter a test domain (e.g., `test-domain.com`)
- [ ] Verify DNS records are shown
- [ ] Check domain appears in domains list

### Test 3: Email Account Configuration
- [ ] Go to Settings → Email Accounts
- [ ] Click "Add Email Account"
- [ ] Configure SMTP settings (use Ethereal for testing):
  - SMTP Host: `smtp.ethereal.email`
  - Port: `587`
  - Use TLS: `true`
  - Get credentials from https://ethereal.email/create
- [ ] Click "Test Connection"
- [ ] Verify success message

### Test 4: Send Test Email
- [ ] Go to Send Console
- [ ] Fill in:
  - From: Your Ethereal email
  - To: Another Ethereal email (or same)
  - Subject: "ChampMail MVP Test"
  - Body: "Testing production deployment"
- [ ] Click "Send Email"
- [ ] Verify success message
- [ ] Check Ethereal inbox: https://ethereal.email/messages
- [ ] Verify email received

### Test 5: Template Management
- [ ] Go to Templates page
- [ ] Click "Create Template"
- [ ] Add template with variables: `Hi {{firstName}}`
- [ ] Save template
- [ ] Verify template appears in list
- [ ] Click "Preview"
- [ ] Test variable substitution

### Test 6: Prospect Management
- [ ] Go to Prospects page
- [ ] Click "Add Prospect"
- [ ] Enter prospect details:
  - Email: `prospect@example.com`
  - First Name: `John`
  - Company: `Test Corp`
- [ ] Save prospect
- [ ] Verify prospect appears in list
- [ ] Click prospect to view details
- [ ] Delete prospect
- [ ] Verify removed from list

---

## 🔒 Security Verification

### Production Settings
- [ ] No default secrets in use (JWT, passwords)
- [ ] `ENVIRONMENT=production` set
- [ ] `DEBUG=false` in production
- [ ] CORS restricted to known domains (no `*`)
- [ ] Webhook signatures enabled (if using webhooks)

### HTTPS & Certificates
- [ ] HTTPS enforced (automatic on Railway/Render)
- [ ] SSL certificate valid
- [ ] HTTP redirects to HTTPS
- [ ] No mixed content warnings in browser

### Database Security
- [ ] Database credentials not in code
- [ ] Database accessible only from backend service
- [ ] Database backups enabled (Railway/Render provide daily snapshots)

---

## 📊 Monitoring

### Basic Monitoring (Free Tier)

1. **Uptime Monitoring**
   - Sign up for Uptime Robot (free): https://uptimerobot.com
   - Add monitor for `/health` endpoint
   - Set alert email

2. **Error Tracking**
   - Check Railway/Render logs daily:
     - Railway: Dashboard → Service → Deployments → View Logs
     - Render: Dashboard → Service → Logs
   - Look for ERROR/CRITICAL level logs

3. **Performance**
   - Test response times:
     ```bash
     curl -w "@curl-format.txt" -o /dev/null -s https://your-backend-domain.com/health
     ```
   - Health check should respond in < 500ms
   - API endpoints should respond in < 1s

---

## 🚨 Known Limitations (MVP)

The following features are intentionally excluded from MVP:

- [ ] **FalkorDB**: Using PostgreSQL only for MVP (graph features disabled)
- [ ] **Campaigns Page**: Shows "Coming Soon" placeholder
- [ ] **Analytics Page**: Displays sample data with disclaimer banner
- [ ] **Sequences**: UI exists but limited backend integration
- [ ] **Celery Beat**: No scheduled tasks (manual triggers only)
- [ ] **Advanced Monitoring**: No Prometheus, Sentry, or Grafana
- [ ] **CI/CD**: No automated testing/deployment pipeline
- [ ] **Automated Backups**: Relying on Railway/Render daily snapshots
- [ ] **Mail Engine**: Using direct SMTP (Go service not deployed)

**These will be addressed in post-MVP phases.**

---

## 🐛 Troubleshooting

### Backend won't start
- Check environment variables are set correctly
- Verify database migrations ran (`alembic upgrade head`)
- Check logs for specific error messages
- Verify PostgreSQL and Redis are running

### Frontend shows CORS errors
- Verify `FRONTEND_URL` is set in backend env vars
- Check frontend is using correct backend URL
- Ensure HTTPS is enabled on both services
- Check browser DevTools → Network → Headers

### Database connection fails
- Verify `DATABASE_URL` or `POSTGRES_*` variables are set
- Check database service is running
- Test connection from backend container
- Ensure firewall allows backend → database traffic

### Health check returns 503
- Check PostgreSQL is accessible
- Verify Redis is accessible
- Review detailed error in health check response
- Check service logs for connection errors

### Emails not sending
- Verify SMTP credentials are correct
- Test SMTP connection (Use Ethereal first)
- Check email account is verified in UI
- Review send logs for error messages

---

## ✅ Deployment Complete!

Once all checks pass:

- [ ] Save all credentials securely (password manager)
- [ ] Document backend and frontend URLs
- [ ] Share access with team members
- [ ] Schedule first backup verification
- [ ] Plan post-MVP improvements (see plan file)

**Next Steps:**
1. Monitor logs for 24 hours
2. Test with real users (limit: 10-50 for MVP)
3. Collect feedback
4. Plan Phase 8-10 improvements (full monitoring, features, CI/CD)

---

## 📞 Support

- Railway Docs: https://docs.railway.app
- Render Docs: https://render.com/docs
- ChampMail Issues: https://github.com/your-repo/issues

**Estimated MVP deployment time: 2-4 hours**

Good luck! 🚀
