#!/bin/bash

# ChampMail Testing Script
# This script helps you test domains, sequences, and knowledge graph
#
# Note: Valid JWT tokens look like: eyJhbGci...header.eyJzdW...payload.signature
# If manually providing a token, ensure it's from /api/v1/auth/login or /api/v1/auth/register

BACKEND_URL="https://champmail-backend-production.up.railway.app"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}    ChampMail Testing Script${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Step 1: Get JWT Token
echo -e "${YELLOW}Step 1: Authentication${NC}"
echo "You need a JWT token to test the API."
echo ""
read -p "Enter your JWT token (or press Enter to register/login first): " JWT_TOKEN

if [ -z "$JWT_TOKEN" ]; then
    echo -e "\n${BLUE}Would you like to:${NC}"
    echo "1) Register a new account"
    echo "2) Login with existing account"
    read -p "Choose (1 or 2): " AUTH_CHOICE

    if [ "$AUTH_CHOICE" == "1" ]; then
        echo -e "\n${YELLOW}Register New Account${NC}"
        read -p "Email: " EMAIL
        read -s -p "Password: " PASSWORD
        echo ""
        read -p "Full Name: " FULL_NAME

        RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/auth/register" \
            -H "Content-Type: application/json" \
            -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"full_name\":\"$FULL_NAME\"}")

        JWT_TOKEN=$(echo $RESPONSE | jq -r '.access_token')

        if [ "$JWT_TOKEN" == "null" ] || [ -z "$JWT_TOKEN" ]; then
            echo -e "${RED}Registration failed:${NC}"
            echo $RESPONSE | jq '.'
            exit 1
        fi
        echo -e "${GREEN}✓ Registration successful!${NC}"
    else
        echo -e "\n${YELLOW}Login${NC}"
        read -p "Email: " EMAIL
        read -s -p "Password: " PASSWORD
        echo ""

        RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/auth/login" \
            -H "Content-Type: application/json" \
            -d "{\"username\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")

        JWT_TOKEN=$(echo $RESPONSE | jq -r '.access_token')

        if [ "$JWT_TOKEN" == "null" ] || [ -z "$JWT_TOKEN" ]; then
            echo -e "${RED}Login failed:${NC}"
            echo $RESPONSE | jq '.'
            exit 1
        fi
        echo -e "${GREEN}✓ Login successful!${NC}"
    fi
fi

echo -e "\n${GREEN}JWT Token obtained!${NC}\n"

# Save token for reuse
echo $JWT_TOKEN > .champmail_token
echo -e "${BLUE}Token saved to .champmail_token for future use${NC}\n"

# Step 2: Test Knowledge Graph
echo -e "${YELLOW}Step 2: Testing Knowledge Graph${NC}"
echo "Checking FalkorDB connection..."

GRAPH_STATS=$(curl -s "$BACKEND_URL/api/v1/graph/stats" \
    -H "Authorization: Bearer $JWT_TOKEN")

echo $GRAPH_STATS | jq '.'

if echo $GRAPH_STATS | jq -e '.node_counts' > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Knowledge Graph is operational!${NC}\n"
else
    echo -e "${RED}✗ Knowledge Graph connection failed${NC}\n"
fi

# Step 3: Domain Setup
echo -e "${YELLOW}Step 3: Domain Setup${NC}"
read -p "Do you want to test domain setup? (y/n): " TEST_DOMAIN

if [ "$TEST_DOMAIN" == "y" ]; then
    echo ""
    echo "Choose domain setup method:"
    echo "1) Manual DNS setup (you configure DNS records yourself)"
    echo "2) Cloudflare auto-setup (requires Cloudflare API)"
    read -p "Choose (1 or 2): " DOMAIN_METHOD

    read -p "Enter your domain name (e.g., yourdomain.com): " DOMAIN_NAME

    echo -e "\n${BLUE}Creating domain in ChampMail...${NC}"

    DOMAIN_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/domains" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"domain_name\":\"$DOMAIN_NAME\",\"selector\":\"champmail\"}")

    DOMAIN_ID=$(echo $DOMAIN_RESPONSE | jq -r '.id')

    if [ "$DOMAIN_ID" == "null" ] || [ -z "$DOMAIN_ID" ]; then
        echo -e "${RED}Domain creation failed:${NC}"
        echo $DOMAIN_RESPONSE | jq '.'
    else
        echo -e "${GREEN}✓ Domain created successfully!${NC}"
        echo "Domain ID: $DOMAIN_ID"
        echo $DOMAIN_ID > .champmail_domain_id

        if [ "$DOMAIN_METHOD" == "1" ]; then
            echo -e "\n${YELLOW}Getting DNS records to configure...${NC}"

            DNS_RECORDS=$(curl -s "$BACKEND_URL/api/v1/domains/$DOMAIN_ID/dns-records" \
                -H "Authorization: Bearer $JWT_TOKEN")

            echo $DNS_RECORDS | jq '.'

            echo -e "\n${BLUE}Configure these 4 DNS records in your DNS provider:${NC}"
            echo "1. MX Record"
            echo "2. SPF Record (TXT)"
            echo "3. DKIM Record (TXT)"
            echo "4. DMARC Record (TXT)"
            echo ""
            read -p "Press Enter when DNS records are configured..."

            echo -e "\n${BLUE}Verifying DNS records...${NC}"
            VERIFY_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/domains/$DOMAIN_ID/verify" \
                -H "Authorization: Bearer $JWT_TOKEN")

            echo $VERIFY_RESPONSE | jq '.'

            if echo $VERIFY_RESPONSE | jq -e '.all_verified == true' > /dev/null 2>&1; then
                echo -e "${GREEN}✓ All DNS records verified!${NC}\n"
            else
                echo -e "${YELLOW}Some DNS records not yet verified. May need more propagation time.${NC}\n"
            fi
        else
            echo -e "\n${BLUE}Running Cloudflare auto-setup...${NC}"
            AUTO_SETUP=$(curl -s -X POST "$BACKEND_URL/api/v1/domains/$DOMAIN_ID/auto-setup" \
                -H "Authorization: Bearer $JWT_TOKEN")

            echo $AUTO_SETUP | jq '.'
            echo -e "${GREEN}✓ Auto-setup complete!${NC}\n"
        fi
    fi
fi

# Step 4: Email Sequences
echo -e "${YELLOW}Step 4: Email Sequences${NC}"
read -p "Do you want to test email sequences? (y/n): " TEST_SEQUENCES

if [ "$TEST_SEQUENCES" == "y" ]; then
    echo -e "\n${BLUE}Creating a test sequence...${NC}"

    SEQUENCE_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/sequences" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{
            "name": "Test Sequence",
            "description": "Testing sequence functionality",
            "from_name": "ChampMail Test",
            "from_address": "test@champmail.com",
            "auto_pause_on_reply": true,
            "steps": [
                {
                    "step_number": 1,
                    "step_type": "email",
                    "delay_days": 0,
                    "delay_hours": 0,
                    "subject": "Test Email 1",
                    "body": "<p>This is test email 1</p>"
                },
                {
                    "step_number": 2,
                    "step_type": "email",
                    "delay_days": 1,
                    "delay_hours": 0,
                    "subject": "Test Email 2",
                    "body": "<p>This is test email 2</p>"
                }
            ]
        }')

    SEQUENCE_ID=$(echo $SEQUENCE_RESPONSE | jq -r '.id')

    if [ "$SEQUENCE_ID" == "null" ] || [ -z "$SEQUENCE_ID" ]; then
        echo -e "${RED}Sequence creation failed:${NC}"
        echo $SEQUENCE_RESPONSE | jq '.'
    else
        echo -e "${GREEN}✓ Sequence created successfully!${NC}"
        echo "Sequence ID: $SEQUENCE_ID"
        echo $SEQUENCE_ID > .champmail_sequence_id

        echo -e "\n${BLUE}Activating sequence...${NC}"
        curl -s -X PUT "$BACKEND_URL/api/v1/sequences/$SEQUENCE_ID" \
            -H "Authorization: Bearer $JWT_TOKEN" \
            -H "Content-Type: application/json" \
            -d '{"status":"active"}' | jq '.'

        echo -e "${GREEN}✓ Sequence activated!${NC}\n"
    fi
fi

# Step 5: Create Test Prospect
echo -e "${YELLOW}Step 5: Test Prospects${NC}"
read -p "Do you want to create a test prospect? (y/n): " CREATE_PROSPECT

if [ "$CREATE_PROSPECT" == "y" ]; then
    read -p "Prospect email: " PROSPECT_EMAIL
    read -p "First name: " FIRST_NAME
    read -p "Last name: " LAST_NAME
    read -p "Company name: " COMPANY_NAME

    echo -e "\n${BLUE}Creating prospect...${NC}"
    PROSPECT_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/prospects" \
        -H "Authorization: Bearer $JWT_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"email\":\"$PROSPECT_EMAIL\",
            \"first_name\":\"$FIRST_NAME\",
            \"last_name\":\"$LAST_NAME\",
            \"company_name\":\"$COMPANY_NAME\"
        }")

    echo $PROSPECT_RESPONSE | jq '.'
    echo -e "${GREEN}✓ Prospect created and added to knowledge graph!${NC}\n"
fi

# Summary
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}    Testing Complete!${NC}"
echo -e "${BLUE}========================================${NC}\n"

echo -e "Your ChampMail instance is ready to use!"
echo -e "Backend URL: ${GREEN}$BACKEND_URL${NC}"
echo -e "\nSaved files:"
echo -e "  • .champmail_token - Your JWT token"
[ -f .champmail_domain_id ] && echo -e "  • .champmail_domain_id - Domain ID"
[ -f .champmail_sequence_id ] && echo -e "  • .champmail_sequence_id - Sequence ID"

echo -e "\n${YELLOW}Next steps:${NC}"
echo "1. Test the knowledge graph with natural language queries"
echo "2. Enroll prospects in your sequence"
echo "3. Monitor analytics and email delivery"

echo -e "\nFor more details, check the testing guide in:"
echo -e "  ${BLUE}/Users/deep/.claude/plans/compressed-coalescing-crown.md${NC}\n"
