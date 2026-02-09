#!/bin/bash
#
# Test Canton MCP Server Challenge-Response Authentication
#
# This script tests the complete authentication flow:
# 1. Request challenge
# 2. Sign challenge (using Python for Ed25519 signing)
# 3. Verify signature and get JWT
# 4. Use JWT for MCP requests
#

set -e

# Configuration
MCP_SERVER="${MCP_SERVER:-http://localhost:7284}"
PARTY_ID="${CANTON_PARTY_ID:-}"
KEY_FILE="${CANTON_KEY_FILE:-}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Canton MCP Server - Challenge-Response Auth Test${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Check if party ID is set
if [ -z "$PARTY_ID" ]; then
    echo -e "${YELLOW}PARTY_ID not set. Using default test party...${NC}"
    # Try to find a key file in ~/.canton
    if [ -d "$HOME/.canton" ]; then
        KEY_FILES=(~/.canton/*-key.json)
        if [ -f "${KEY_FILES[0]}" ]; then
            KEY_FILE="${KEY_FILES[0]}"
            PARTY_ID=$(jq -r '.partyId' "$KEY_FILE")
            echo -e "${GREEN}Found key file: $KEY_FILE${NC}"
            echo -e "${GREEN}Party ID: $PARTY_ID${NC}"
        fi
    fi
fi

if [ -z "$PARTY_ID" ]; then
    echo -e "${RED}ERROR: PARTY_ID not set and no key file found in ~/.canton${NC}"
    echo ""
    echo "Usage:"
    echo "  export CANTON_PARTY_ID='alice::1220...'"
    echo "  export CANTON_KEY_FILE='~/.canton/alice-key.json'"
    echo "  ./test-challenge-auth.sh"
    exit 1
fi

if [ -z "$KEY_FILE" ]; then
    # Auto-detect key file from party name
    PARTY_NAME=$(echo "$PARTY_ID" | cut -d':' -f1)
    KEY_FILE="$HOME/.canton/${PARTY_NAME}-key.json"
fi

if [ ! -f "$KEY_FILE" ]; then
    echo -e "${RED}ERROR: Key file not found: $KEY_FILE${NC}"
    exit 1
fi

echo -e "${BLUE}Configuration:${NC}"
echo -e "  MCP Server: $MCP_SERVER"
echo -e "  Party ID: $PARTY_ID"
echo -e "  Key File: $KEY_FILE"
echo ""

# Extract public key from key file
PUBLIC_KEY=$(jq -r '.publicKey' "$KEY_FILE")

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Test 1: Request Challenge${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Try without public key first
echo -e "${YELLOW}Requesting challenge without public key...${NC}"
CHALLENGE_RESPONSE=$(curl -s -X POST "$MCP_SERVER/auth/challenge" \
    -H "Content-Type: application/json" \
    -d "{\"partyId\": \"$PARTY_ID\"}" || echo "")

if echo "$CHALLENGE_RESPONSE" | jq -e '.requiresPublicKey' >/dev/null 2>&1; then
    echo -e "${YELLOW}Public key required for first-time authentication${NC}"
    echo -e "${YELLOW}Requesting challenge with public key...${NC}"

    CHALLENGE_RESPONSE=$(curl -s -X POST "$MCP_SERVER/auth/challenge" \
        -H "Content-Type: application/json" \
        -d "{\"partyId\": \"$PARTY_ID\", \"publicKey\": \"$PUBLIC_KEY\"}")
fi

if ! echo "$CHALLENGE_RESPONSE" | jq -e '.challenge' >/dev/null 2>&1; then
    echo -e "${RED}✗ Failed to get challenge${NC}"
    echo "$CHALLENGE_RESPONSE" | jq .
    exit 1
fi

CHALLENGE=$(echo "$CHALLENGE_RESPONSE" | jq -r '.challenge')
echo -e "${GREEN}✓ Challenge received: ${CHALLENGE:0:32}...${NC}"
echo "$CHALLENGE_RESPONSE" | jq .
echo ""

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Test 2: Sign Challenge${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Sign challenge using Python with PyNaCl
SIGNATURE=$(python3 -c "
import json
import base64
from nacl.signing import SigningKey

# Load private key
with open('$KEY_FILE') as f:
    key_data = json.load(f)

private_key_bytes = base64.b64decode(key_data['privateKey'])
signing_key = SigningKey(private_key_bytes)

# Sign challenge
challenge_bytes = base64.b64decode('$CHALLENGE')
signature_bytes = signing_key.sign(challenge_bytes).signature

# Output base64-encoded signature
print(base64.b64encode(signature_bytes).decode('ascii'))
")

if [ -z "$SIGNATURE" ]; then
    echo -e "${RED}✗ Failed to sign challenge${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Challenge signed: ${SIGNATURE:0:32}...${NC}"
echo ""

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Test 3: Verify Signature and Get JWT${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

VERIFY_RESPONSE=$(curl -s -X POST "$MCP_SERVER/auth/verify" \
    -H "Content-Type: application/json" \
    -d "{
        \"partyId\": \"$PARTY_ID\",
        \"challenge\": \"$CHALLENGE\",
        \"signature\": \"$SIGNATURE\"
    }")

if ! echo "$VERIFY_RESPONSE" | jq -e '.token' >/dev/null 2>&1; then
    echo -e "${RED}✗ Signature verification failed${NC}"
    echo "$VERIFY_RESPONSE" | jq .
    exit 1
fi

TOKEN=$(echo "$VERIFY_RESPONSE" | jq -r '.token')
echo -e "${GREEN}✓ JWT token received${NC}"
echo -e "${GREEN}  Token: ${TOKEN:0:50}...${NC}"
echo ""

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Test 4: Use JWT for MCP Request${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

MCP_RESPONSE=$(curl -s -X POST "$MCP_SERVER/mcp" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json" \
    -d '{
        "jsonrpc": "2.0",
        "method": "tools/list",
        "params": {},
        "id": 1
    }')

if ! echo "$MCP_RESPONSE" | jq -e '.result' >/dev/null 2>&1; then
    echo -e "${RED}✗ MCP request failed${NC}"
    echo "$MCP_RESPONSE" | jq .
    exit 1
fi

TOOL_COUNT=$(echo "$MCP_RESPONSE" | jq '.result.tools | length')
echo -e "${GREEN}✓ MCP request successful${NC}"
echo -e "${GREEN}  Available tools: $TOOL_COUNT${NC}"
echo ""

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Test 5: Invalid Signature (Should Fail)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Request new challenge
CHALLENGE_RESPONSE2=$(curl -s -X POST "$MCP_SERVER/auth/challenge" \
    -H "Content-Type: application/json" \
    -d "{\"partyId\": \"$PARTY_ID\"}")

CHALLENGE2=$(echo "$CHALLENGE_RESPONSE2" | jq -r '.challenge')

# Try with invalid signature
INVALID_SIGNATURE="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="

VERIFY_RESPONSE2=$(curl -s -X POST "$MCP_SERVER/auth/verify" \
    -H "Content-Type: application/json" \
    -d "{
        \"partyId\": \"$PARTY_ID\",
        \"challenge\": \"$CHALLENGE2\",
        \"signature\": \"$INVALID_SIGNATURE\"
    }")

if echo "$VERIFY_RESPONSE2" | jq -e '.token' >/dev/null 2>&1; then
    echo -e "${RED}✗ Invalid signature was accepted (SECURITY BUG!)${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Invalid signature correctly rejected${NC}"
echo -e "${YELLOW}  Error: $(echo "$VERIFY_RESPONSE2" | jq -r '.error')${NC}"
echo ""

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ All Tests Passed!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${GREEN}Challenge-response authentication is working correctly!${NC}"
echo ""
echo -e "${YELLOW}Your JWT token (valid for 1 hour):${NC}"
echo "$TOKEN"
echo ""
echo -e "${YELLOW}Use it in requests:${NC}"
echo "  curl -X POST $MCP_SERVER/mcp \\"
echo "    -H 'Authorization: Bearer $TOKEN' \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"jsonrpc\": \"2.0\", \"method\": \"tools/list\", \"params\": {}, \"id\": 1}'"
echo ""
