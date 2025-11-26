#!/bin/bash
# Production Deployment Test Script
# Tests all critical functionality of the Canton MCP Server

set -e

SERVER_URL="${SERVER_URL:-http://91.99.186.83:7284}"
SSH_HOST="${SSH_HOST:-devops@91.99.186.83}"
SERVER_PATH="/opt/canton-mcp-server"

echo "🧪 Testing Canton MCP Server Deployment"
echo "Server: $SERVER_URL"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
PASSED=0
FAILED=0

test_pass() {
    echo -e "${GREEN}✅ PASS${NC}: $1"
    ((PASSED++))
}

test_fail() {
    echo -e "${RED}❌ FAIL${NC}: $1"
    ((FAILED++))
}

test_warn() {
    echo -e "${YELLOW}⚠️  WARN${NC}: $1"
}

# ============================================
# Test 1: Health Check
# ============================================
echo "📋 Test 1: Health Check"
if curl -sf "$SERVER_URL/health" | grep -q "healthy"; then
    test_pass "Server health endpoint responding"
else
    test_fail "Server health endpoint not responding"
fi
echo ""

# ============================================
# Test 2: MCP Tools List
# ============================================
echo "📋 Test 2: MCP Tools Available"
TOOLS_RESPONSE=$(curl -s -X POST "$SERVER_URL/mcp" \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}')

if echo "$TOOLS_RESPONSE" | grep -q "daml_reason"; then
    test_pass "daml_reason tool available"
else
    test_fail "daml_reason tool not found"
fi

if echo "$TOOLS_RESPONSE" | grep -q "daml_automater"; then
    test_pass "daml_automater tool available"
else
    test_fail "daml_automater tool not found"
fi
echo ""

# ============================================
# Test 3: MCP Resources (Canonical Docs)
# ============================================
echo "📋 Test 3: Canonical Documentation Resources"
RESOURCES_RESPONSE=$(curl -s -X POST "$SERVER_URL/mcp" \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"resources/list","params":{}}')

DOC_COUNT=$(echo "$RESOURCES_RESPONSE" | grep -o '"uri"' | wc -l | tr -d ' ')

if [ "$DOC_COUNT" -gt 10000 ]; then
    test_pass "Canonical docs loaded ($DOC_COUNT files)"
elif [ "$DOC_COUNT" -gt 0 ]; then
    test_warn "Only $DOC_COUNT docs loaded (expected ~14,851)"
else
    test_fail "No canonical docs loaded"
fi
echo ""

# ============================================
# Test 4: SSH Access & Server Files
# ============================================
echo "📋 Test 4: Server File System"
echo "Checking server configuration..."

if ssh -o ConnectTimeout=5 "$SSH_HOST" "test -d $SERVER_PATH" 2>/dev/null; then
    test_pass "Server directory exists: $SERVER_PATH"
    
    # Check canonical repos
    if ssh "$SSH_HOST" "test -d /opt/canonical-daml-docs-daml" 2>/dev/null; then
        test_pass "Canonical repo 'daml' exists"
    else
        test_fail "Canonical repo 'daml' missing"
    fi
    
    if ssh "$SSH_HOST" "test -d /opt/canonical-daml-docs-canton" 2>/dev/null; then
        test_pass "Canonical repo 'canton' exists"
    else
        test_fail "Canonical repo 'canton' missing"
    fi
    
    if ssh "$SSH_HOST" "test -d /opt/canonical-daml-docs-daml-finance" 2>/dev/null; then
        test_pass "Canonical repo 'daml-finance' exists"
    else
        test_fail "Canonical repo 'daml-finance' missing"
    fi
    
    # Check .env.canton
    if ssh "$SSH_HOST" "test -f $SERVER_PATH/.env.canton" 2>/dev/null; then
        test_pass ".env.canton file exists"
    else
        test_warn ".env.canton file missing (ANTHROPIC_API_KEY not set)"
    fi
    
else
    test_warn "Cannot SSH to server (skipping file checks)"
fi
echo ""

# ============================================
# Test 5: Cronjob Configuration
# ============================================
echo "📋 Test 5: Cronjob for Repo Updates"
if ssh "$SSH_HOST" "crontab -l 2>/dev/null | grep -q update-canonical-repos" 2>/dev/null; then
    test_pass "Cronjob configured for repo updates"
    echo "   Schedule: $(ssh "$SSH_HOST" "crontab -l 2>/dev/null | grep update-canonical-repos")"
else
    test_warn "Cronjob not found (repos won't auto-update)"
fi
echo ""

# ============================================
# Test 6: Update Script
# ============================================
echo "📋 Test 6: Update Script Exists"
if ssh "$SSH_HOST" "test -x /opt/update-canonical-repos.sh" 2>/dev/null; then
    test_pass "Update script exists and is executable"
else
    test_fail "Update script missing or not executable"
fi
echo ""

# ============================================
# Test 7: Docker Container Status
# ============================================
echo "📋 Test 7: Docker Container"
if ssh "$SSH_HOST" "cd $SERVER_PATH && docker compose ps | grep -q 'Up'" 2>/dev/null; then
    test_pass "Docker container running"
    
    # Check for DAML SDK in container
    if ssh "$SSH_HOST" "cd $SERVER_PATH && docker compose exec -T canton-mcp-server which daml" 2>/dev/null; then
        test_pass "DAML SDK installed in container"
    else
        test_fail "DAML SDK missing in container (daml_reason will fail)"
    fi
else
    test_warn "Cannot check Docker container status"
fi
echo ""

# ============================================
# Summary
# ============================================
echo "════════════════════════════════════════"
echo "📊 Test Results Summary"
echo "════════════════════════════════════════"
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 All tests passed!${NC}"
    exit 0
else
    echo -e "${YELLOW}⚠️  Some tests failed. See issues above.${NC}"
    exit 1
fi



