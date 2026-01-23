#!/bin/bash
# Test script for Canton payment integration with MCP server

set -e

echo "🧪 Testing Canton Payment Integration"
echo "===================================="
echo ""

# Configuration
MCP_SERVER_URL="http://localhost:7284"
FACILITATOR_URL="http://46.224.109.63:3000"
MERCHANT_PARTY="damlcopilot-receiver::1220096316d4ea75c021d89123cfd2792cfeac80dfbf90bfbca21bcd8bf1bb40d84c"
PAYER_PARTY="x402-test-signer::1220f888487f0ea850c8c58a3370cdf205f6a5ebb481ddfbaf35b76abcf510605efc"

echo "📋 Configuration:"
echo "   MCP Server: ${MCP_SERVER_URL}"
echo "   Facilitator: ${FACILITATOR_URL}"
echo "   Merchant Party: ${MERCHANT_PARTY}"
echo "   Payer Party: ${PAYER_PARTY}"
echo ""

# Step 1: Check facilitator health
echo "🏥 Step 1: Checking facilitator health..."
FACILITATOR_HEALTH=$(curl -s "${FACILITATOR_URL}/health" || echo "")
if [ -z "$FACILITATOR_HEALTH" ]; then
    echo "   ❌ Facilitator not reachable at ${FACILITATOR_URL}"
    echo "   Please ensure facilitator is deployed and running"
    exit 1
fi
echo "   ✅ Facilitator is healthy"
echo "   Response: ${FACILITATOR_HEALTH}"
echo ""

# Step 2: Check MCP server health
echo "🏥 Step 2: Checking MCP server health..."
MCP_HEALTH=$(curl -s "${MCP_SERVER_URL}/health" || echo "")
if [ -z "$MCP_HEALTH" ]; then
    echo "   ❌ MCP server not running at ${MCP_SERVER_URL}"
    echo "   Please start the server with: ./start-server.sh"
    exit 1
fi
echo "   ✅ MCP server is running"
echo ""

# Step 3: Test tool call WITHOUT payment (should return 402)
echo "💰 Step 3: Testing tool call WITHOUT payment (expecting 402)..."
TOOL_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${MCP_SERVER_URL}/mcp" \
  -H "Content-Type: application/json" \
  -H "X-Canton-Party-ID: ${PAYER_PARTY}" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "daml_reason",
      "arguments": {
        "businessIntent": "Create a simple IOU",
        "damlCode": "template IOU\n  with\n    issuer: Party\n    owner: Party\n  where\n    signatory issuer"
      }
    }
  }' || echo "")

HTTP_CODE=$(echo "$TOOL_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$TOOL_RESPONSE" | sed '$d')

echo "   HTTP Status: ${HTTP_CODE}"
if [ "$HTTP_CODE" = "402" ]; then
    echo "   ✅ Correctly returned 402 Payment Required"
    echo "   Response body:"
    echo "$RESPONSE_BODY" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE_BODY"
else
    echo "   ⚠️  Unexpected status code (expected 402, got ${HTTP_CODE})"
    echo "   Response body:"
    echo "$RESPONSE_BODY" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE_BODY"
fi
echo ""

# Step 4: Extract payment requirements
echo "📋 Step 4: Analyzing payment requirements..."
if [ "$HTTP_CODE" = "402" ]; then
    TRANSFER_FACTORY=$(echo "$RESPONSE_BODY" | python3 -c "import sys, json; data=json.load(sys.stdin); reqs=data.get('accepts', []); canton_req=[r for r in reqs if isinstance(r, dict) and r.get('scheme')=='exact-canton']; print(json.dumps(canton_req[0].get('extra', {}).get('transferFactory', {}), indent=2))" 2>/dev/null || echo "")
    
    if [ -n "$TRANSFER_FACTORY" ] && [ "$TRANSFER_FACTORY" != "{}" ]; then
        echo "   ✅ TransferFactory found in payment requirements"
        echo "   TransferFactory details:"
        echo "$TRANSFER_FACTORY" | head -10
    else
        echo "   ⚠️  TransferFactory not found in payment requirements"
        echo "   This may indicate the facilitator integration is not working"
    fi
fi
echo ""

echo "✅ Test completed!"
echo ""
echo "Next steps:"
echo "1. If 402 was returned, the payment flow is working correctly"
echo "2. To complete the payment, the client needs to:"
echo "   - Use TransferFactory from payment requirements"
echo "   - Execute the Canton transfer"
echo "   - Retry the tool call with X-PAYMENT header"
echo ""
