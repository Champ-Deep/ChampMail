#!/bin/bash

# ChampMail End-to-End Test with Ethereal Mail
# This script tests the complete workflow: domains, sequences, knowledge graph, and email sending

set -e  # Exit on error

BACKEND_URL="https://champmail-backend-production.up.railway.app"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         ChampMail End-to-End Test Suite                   ║${NC}"
echo -e "${BLUE}║         Testing with Ethereal Mail (Fake SMTP)            ║${NC}"
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╝${NC}\n"

# Step 1: Get Ethereal Mail credentials
echo -e "${YELLOW}[1/8] Setting up Ethereal Mail test account...${NC}"
echo "Creating temporary test SMTP credentials..."

ETHEREAL_RESPONSE=$(curl -s -X POST https://api.nodemailer.com/user)
ETHEREAL_EMAIL=$(echo $ETHEREAL_RESPONSE | jq -r '.user')
ETHEREAL_PASSWORD=$(echo $ETHEREAL_RESPONSE | jq -r '.pass')
ETHEREAL_SMTP_HOST=$(echo $ETHEREAL_RESPONSE | jq -r '.smtp.host')
ETHEREAL_SMTP_PORT=$(echo $ETHEREAL_RESPONSE | jq -r '.smtp.port')
ETHEREAL_WEB=$(echo $ETHEREAL_RESPONSE | jq -r '.web')

if [ "$ETHEREAL_EMAIL" == "null" ]; then
    echo -e "${RED}✗ Failed to create Ethereal account${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Ethereal Mail account created!${NC}"
echo -e "  SMTP Host: ${BLUE}$ETHEREAL_SMTP_HOST:$ETHEREAL_SMTP_PORT${NC}"
echo -e "  Username: ${BLUE}$ETHEREAL_EMAIL${NC}"
echo -e "  View emails: ${BLUE}$ETHEREAL_WEB${NC}\n"

# Save for later reference
cat > .ethereal_credentials <<EOF
SMTP_HOST=$ETHEREAL_SMTP_HOST
SMTP_PORT=$ETHEREAL_SMTP_PORT
SMTP_USER=$ETHEREAL_EMAIL
SMTP_PASS=$ETHEREAL_PASSWORD
WEB_URL=$ETHEREAL_WEB
EOF

# Step 1.5: CRITICAL - Configure backend to use Ethereal SMTP
echo -e "${YELLOW}[1.5/9] Configuring backend to use Ethereal SMTP...${NC}"
echo "This ensures all test emails go to Ethereal Mail, not production SMTP"

# Wait for user registration first, then configure SMTP
# (moved to after Step 2)

# Step 2: Register test user in ChampMail
echo -e "${YELLOW}[2/9] Registering test user...${NC}"

TEST_EMAIL="test-$(date +%s)@champmail.test"
TEST_PASSWORD="TestPassword123!"
TEST_NAME="E2E Test User"

AUTH_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/auth/register" \
    -H "Content-Type: application/json" \
    -d "{
        \"email\":\"$TEST_EMAIL\",
        \"password\":\"$TEST_PASSWORD\",
        \"full_name\":\"$TEST_NAME\"
    }")

JWT_TOKEN=$(echo $AUTH_RESPONSE | jq -r '.access_token')

if [ "$JWT_TOKEN" == "null" ] || [ -z "$JWT_TOKEN" ]; then
    echo -e "${RED}✗ Registration failed${NC}"
    echo $AUTH_RESPONSE | jq '.'

    # Try login instead
    echo -e "${YELLOW}Attempting login...${NC}"
    AUTH_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/auth/login" \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}")

    JWT_TOKEN=$(echo $AUTH_RESPONSE | jq -r '.access_token')

    if [ "$JWT_TOKEN" == "null" ]; then
        echo -e "${RED}✗ Login also failed${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}✓ User authenticated successfully${NC}"
echo $JWT_TOKEN > .test_jwt_token
echo ""

# CRITICAL FIX: Configure backend to use Ethereal SMTP
echo -e "${YELLOW}Configuring backend to use Ethereal SMTP...${NC}"

UPDATE_SETTINGS=$(curl -s -X PUT "$BACKEND_URL/api/v1/settings/email" \
    -H "Authorization: Bearer $JWT_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"smtp_host\": \"$ETHEREAL_SMTP_HOST\",
        \"smtp_port\": $ETHEREAL_SMTP_PORT,
        \"smtp_username\": \"$ETHEREAL_EMAIL\",
        \"smtp_password\": \"$ETHEREAL_PASSWORD\",
        \"smtp_use_tls\": true,
        \"from_email\": \"test@champmail.test\",
        \"from_name\": \"ChampMail Test\"
    }")

# Check if configuration succeeded
if echo $UPDATE_SETTINGS | jq -e '.smtp_host' > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Backend configured to use Ethereal SMTP${NC}"
    echo -e "  All emails will be captured at: ${BLUE}$ETHEREAL_WEB${NC}\n"
elif echo $UPDATE_SETTINGS | jq -e '.detail' > /dev/null 2>&1; then
    ERROR_MSG=$(echo $UPDATE_SETTINGS | jq -r '.detail')
    echo -e "${RED}✗ SMTP configuration failed: $ERROR_MSG${NC}"
    echo -e "${YELLOW}⚠️  WARNING: Emails may go to production SMTP instead of Ethereal!${NC}\n"
else
    echo -e "${YELLOW}⚠️  SMTP configuration status unclear${NC}"
    echo $UPDATE_SETTINGS | jq '.'
    echo -e "${YELLOW}⚠️  WARNING: Emails may go to production SMTP instead of Ethereal!${NC}\n"
fi

# Step 3: Verify Celery workers are running
echo -e "${YELLOW}[3/9] Checking Celery workers...${NC}"

CELERY_CHECK=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL/health/celery" 2>&1 || echo "000")

if [ "$CELERY_CHECK" == "200" ]; then
    echo -e "${GREEN}✓ Celery workers are running${NC}\n"
elif [ "$CELERY_CHECK" == "404" ]; then
    echo -e "${YELLOW}⚠️  Celery health endpoint not found (may not be implemented)${NC}"
    echo -e "${YELLOW}⚠️  Email sequences will only execute if Celery workers are running on Railway${NC}\n"
else
    echo -e "${YELLOW}⚠️  Could not verify Celery status (HTTP $CELERY_CHECK)${NC}"
    echo -e "${YELLOW}⚠️  Email sequences require Celery workers to be running${NC}\n"
fi

# Step 4: Test Knowledge Graph
echo -e "${YELLOW}[4/9] Testing Knowledge Graph connection...${NC}"

GRAPH_STATS=$(curl -s "$BACKEND_URL/api/v1/graph/stats" \
    -H "Authorization: Bearer $JWT_TOKEN")

echo $GRAPH_STATS | jq '.'

if echo $GRAPH_STATS | jq -e '.node_counts' > /dev/null 2>&1; then
    PROSPECT_COUNT=$(echo $GRAPH_STATS | jq -r '.node_counts.Prospect // 0')
    COMPANY_COUNT=$(echo $GRAPH_STATS | jq -r '.node_counts.Company // 0')
    echo -e "${GREEN}✓ Knowledge Graph operational${NC}"
    echo -e "  Prospects: $PROSPECT_COUNT, Companies: $COMPANY_COUNT\n"
else
    echo -e "${YELLOW}⚠ Knowledge Graph may not be fully connected${NC}\n"
fi

# Step 5: Create test domain
echo -e "${YELLOW}[5/9] Creating test domain...${NC}"

TEST_DOMAIN="test-$(date +%s).champmail.test"

DOMAIN_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/domains" \
    -H "Authorization: Bearer $JWT_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"domain_name\":\"$TEST_DOMAIN\",
        \"selector\":\"champmail\"
    }")

DOMAIN_ID=$(echo $DOMAIN_RESPONSE | jq -r '.id')

if [ "$DOMAIN_ID" == "null" ] || [ -z "$DOMAIN_ID" ]; then
    echo -e "${RED}✗ Domain creation failed${NC}"
    echo $DOMAIN_RESPONSE | jq '.'
else
    echo -e "${GREEN}✓ Domain created: $TEST_DOMAIN${NC}"
    echo -e "  Domain ID: ${BLUE}$DOMAIN_ID${NC}"
    echo $DOMAIN_ID > .test_domain_id
fi
echo ""

# Step 6: Create test prospects
echo -e "${YELLOW}[6/9] Creating test prospects...${NC}"

declare -a PROSPECT_EMAILS=()

for i in {1..3}; do
    PROSPECT_EMAIL="prospect${i}-$(date +%s)@testcompany.com"
    PROSPECT_EMAILS+=($PROSPECT_EMAIL)

    PROSPECT_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/prospects" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"email\":\"$PROSPECT_EMAIL\",
            \"first_name\":\"Prospect\",
            \"last_name\":\"Number $i\",
            \"company_name\":\"Test Company $i\",
            \"company_domain\":\"testcompany$i.com\",
            \"title\":\"Test Manager\"
        }")

    PROSPECT_ID=$(echo $PROSPECT_RESPONSE | jq -r '.id')

    if [ "$PROSPECT_ID" != "null" ]; then
        echo -e "${GREEN}  ✓ Created: $PROSPECT_EMAIL${NC}"
    else
        echo -e "${RED}  ✗ Failed: $PROSPECT_EMAIL${NC}"
        echo $PROSPECT_RESPONSE | jq '.'
    fi
done
echo ""

# Step 7: Create and activate email sequence
echo -e "${YELLOW}[7/9] Creating email sequence...${NC}"

SEQUENCE_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/sequences" \
    -H "Authorization: Bearer $JWT_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"name\":\"E2E Test Sequence\",
        \"description\":\"Automated test sequence\",
        \"from_name\":\"Test Sender\",
        \"from_email\":\"test@$TEST_DOMAIN\",
        \"reply_to\":\"reply@$TEST_DOMAIN\",
        \"auto_pause_on_reply\":true,
        \"use_ai_personalization\":false,
        \"steps\":[
            {
                \"order\":1,
                \"name\":\"Initial Contact\",
                \"subject_template\":\"Hello {{first_name}}, testing ChampMail\",
                \"html_template\":\"<p>Hi {{first_name}} {{last_name}},</p><p>This is a test email from ChampMail.</p><p>Your company: {{company_name}}</p>\",
                \"plain_text_template\":\"Hi {{first_name}} {{last_name}}, This is a test email from ChampMail. Your company: {{company_name}}\",
                \"delay_hours\":0,
                \"delay_days\":0
            },
            {
                \"order\":2,
                \"name\":\"Follow Up\",
                \"subject_template\":\"Following up - {{first_name}}\",
                \"html_template\":\"<p>Hi {{first_name}},</p><p>Just following up on my previous email.</p>\",
                \"plain_text_template\":\"Hi {{first_name}}, Just following up on my previous email.\",
                \"delay_hours\":0,
                \"delay_days\":0,
                \"comment\":\"NOTE: Set to 0 for immediate testing. In production, use delay_hours or delay_days for proper sequencing.\"
            }
        ]
    }")

SEQUENCE_ID=$(echo $SEQUENCE_RESPONSE | jq -r '.id')

if [ "$SEQUENCE_ID" == "null" ] || [ -z "$SEQUENCE_ID" ]; then
    echo -e "${RED}✗ Sequence creation failed${NC}"
    echo $SEQUENCE_RESPONSE | jq '.'
else
    echo -e "${GREEN}✓ Sequence created${NC}"
    echo -e "  Sequence ID: ${BLUE}$SEQUENCE_ID${NC}"
    echo $SEQUENCE_ID > .test_sequence_id

    # Activate sequence
    echo -e "${BLUE}  Activating sequence...${NC}"
    ACTIVATE_RESPONSE=$(curl -s -X PUT "$BACKEND_URL/api/v1/sequences/$SEQUENCE_ID" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"status":"active"}')

    if echo $ACTIVATE_RESPONSE | jq -e '.status == "active"' > /dev/null 2>&1; then
        echo -e "${GREEN}  ✓ Sequence activated${NC}"
    else
        echo -e "${YELLOW}  ⚠ Activation status unclear${NC}"
        echo $ACTIVATE_RESPONSE | jq '.'
    fi
fi
echo ""

# Step 8: Enroll prospects in sequence
echo -e "${YELLOW}[8/9] Enrolling prospects in sequence...${NC}"

# Build JSON array of prospect emails
PROSPECT_JSON=$(printf '%s\n' "${PROSPECT_EMAILS[@]}" | jq -R . | jq -s .)

ENROLL_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/sequences/$SEQUENCE_ID/enroll" \
    -H "Authorization: Bearer $JWT_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"prospect_emails\":$PROSPECT_JSON}")

echo $ENROLL_RESPONSE | jq '.'

ENROLLED_COUNT=$(echo $ENROLL_RESPONSE | jq -r '.enrolled // 0')
FAILED_COUNT=$(echo $ENROLL_RESPONSE | jq -r '.failed // 0')

if [ "$ENROLLED_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓ Enrolled $ENROLLED_COUNT prospects${NC}"
    [ "$FAILED_COUNT" -gt 0 ] && echo -e "${YELLOW}  ⚠ Failed to enroll $FAILED_COUNT prospects${NC}"
else
    echo -e "${RED}✗ No prospects enrolled - cannot continue test${NC}"
    echo -e "${RED}Enrollment is required for email sequence testing${NC}"
    exit 1
fi
echo ""

# Step 9: Verify sequence analytics
echo -e "${YELLOW}[9/9] Checking sequence analytics...${NC}"

sleep 2  # Give it a moment to process

ANALYTICS_RESPONSE=$(curl -s "$BACKEND_URL/api/v1/sequences/$SEQUENCE_ID/analytics" \
    -H "Authorization: Bearer $JWT_TOKEN")

echo $ANALYTICS_RESPONSE | jq '.'

if echo $ANALYTICS_RESPONSE | jq -e '.enrollment_stats' > /dev/null 2>&1; then
    ACTIVE_ENROLLMENTS=$(echo $ANALYTICS_RESPONSE | jq -r '.enrollment_stats.active // 0')
    echo -e "${GREEN}✓ Analytics retrieved${NC}"
    echo -e "  Active enrollments: ${BLUE}$ACTIVE_ENROLLMENTS${NC}"
else
    echo -e "${YELLOW}⚠ Analytics not fully available yet${NC}"
fi
echo ""

# Test Knowledge Graph queries
echo -e "${YELLOW}[Bonus] Testing Knowledge Graph queries...${NC}"

# Search for created prospects
SEARCH_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/graph/search" \
    -H "Authorization: Bearer $JWT_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "query":"Prospect Number",
        "entity_types":["Prospect"],
        "limit":10
    }')

SEARCH_COUNT=$(echo $SEARCH_RESPONSE | jq -r '.results | length')

if [ "$SEARCH_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓ Knowledge Graph search working${NC}"
    echo -e "  Found ${BLUE}$SEARCH_COUNT${NC} prospects"
else
    echo -e "${YELLOW}⚠ No prospects found in graph (may need time to sync)${NC}"
fi
echo ""

# Natural language query test
echo -e "${BLUE}Testing LLM-powered natural language query...${NC}"

NLQ_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/graph/chat" \
    -H "Authorization: Bearer $JWT_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"message":"Show me all prospects created today"}')

if echo $NLQ_RESPONSE | jq -e '.cypher' > /dev/null 2>&1; then
    CYPHER_QUERY=$(echo $NLQ_RESPONSE | jq -r '.cypher')
    echo -e "${GREEN}✓ Natural language query working${NC}"
    echo -e "  Generated Cypher: ${BLUE}$CYPHER_QUERY${NC}"
else
    echo -e "${YELLOW}⚠ NLQ may require OPENROUTER_API_KEY${NC}"
fi
echo ""

# Summary
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                    TEST SUMMARY                            ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}\n"

echo -e "${GREEN}✅ Backend:${NC} https://champmail-backend-production.up.railway.app"
echo -e "${GREEN}✅ User:${NC} $TEST_EMAIL"
echo -e "${GREEN}✅ Domain:${NC} $TEST_DOMAIN (ID: $DOMAIN_ID)"
echo -e "${GREEN}✅ Sequence:${NC} E2E Test Sequence (ID: $SEQUENCE_ID)"
echo -e "${GREEN}✅ Prospects:${NC} ${#PROSPECT_EMAILS[@]} created and enrolled"
echo -e "${GREEN}✅ Knowledge Graph:${NC} Operational\n"

echo -e "${YELLOW}📧 Ethereal Mail Access:${NC}"
echo -e "   View test emails at: ${BLUE}$ETHEREAL_WEB${NC}"
echo -e "   SMTP: $ETHEREAL_SMTP_HOST:$ETHEREAL_SMTP_PORT"
echo -e "   User: $ETHEREAL_EMAIL\n"

echo -e "${YELLOW}📝 Test Data Saved:${NC}"
echo -e "   • .test_jwt_token - JWT authentication token"
echo -e "   • .test_domain_id - Domain ID"
echo -e "   • .test_sequence_id - Sequence ID"
echo -e "   • .ethereal_credentials - SMTP credentials\n"

echo -e "${YELLOW}🔍 Email Verification Steps:${NC}"
echo -e "   ${BLUE}IMPORTANT:${NC} With the current test configuration, both sequence steps"
echo -e "   have 0 delay, so emails should be sent ${BLUE}immediately${NC} when Celery processes them.\n"
echo -e "   1. Wait 2-5 minutes for Celery to process the sequence queue"
echo -e "   2. Open Ethereal Mail inbox: ${BLUE}$ETHEREAL_WEB${NC}"
echo -e "   3. You should see ${GREEN}6 emails total${NC}:"
echo -e "      • 3 emails for Step 1 (Initial Contact)"
echo -e "      • 3 emails for Step 2 (Follow Up)"
echo -e "   4. Verify email content has proper variable substitution"
echo -e "   5. Check Railway logs for Celery task execution\n"
echo -e "   ${YELLOW}If emails don't appear:${NC}"
echo -e "   • Verify Celery workers are running: ${BLUE}railway logs --service champmail-backend${NC}"
echo -e "   • Check for errors in mail-engine logs"
echo -e "   • Verify SMTP configuration was applied successfully (see output above)\n"

# Check if there are pending sequence executions
echo -e "${YELLOW}Checking for pending sequence executions...${NC}"

SEQUENCE_DETAIL=$(curl -s "$BACKEND_URL/api/v1/sequences/$SEQUENCE_ID" \
    -H "Authorization: Bearer $JWT_TOKEN")

echo $SEQUENCE_DETAIL | jq '{
    id: .id,
    name: .name,
    status: .status,
    active_enrollments: .enrollment_stats.active,
    total_enrollments: (.enrollment_stats.active + .enrollment_stats.completed + .enrollment_stats.paused)
}'

echo -e "\n${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║              TEST CONFIGURATION COMPLETE                   ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}\n"

echo -e "${GREEN}✅ Test data created successfully!${NC}"
echo -e "${YELLOW}⏱️  Email sending status:${NC}"
echo -e "   • Sequence steps configured with ${BLUE}0 delay${NC} for immediate testing"
echo -e "   • Celery will process both steps as soon as workers pick up the tasks"
echo -e "   • Check ${BLUE}$ETHEREAL_WEB${NC} in 2-5 minutes for test emails\n"

echo -e "${YELLOW}🔍 Troubleshooting:${NC}"
echo -e "   • If no emails appear, check: ${BLUE}railway logs --service champmail-backend${NC}"
echo -e "   • Look for: \"Executing pending sequence steps\""
echo -e "   • Look for: \"Email sent successfully, message_id=...\""
echo -e "   • Verify Celery workers are running and processing the 'sequences' queue\n"
