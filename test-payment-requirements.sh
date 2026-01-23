#!/bin/bash
# Test script to verify payment requirements generation (even for free tools)

set -e

echo "🧪 Testing Payment Requirements Generation"
echo "=========================================="
echo ""

MCP_SERVER_URL="http://localhost:7284"
PAYER_PARTY="x402-test-signer::1220f888487f0ea850c8c58a3370cdf205f6a5ebb481ddfbaf35b76abcf510605efc"

echo "📋 Configuration:"
echo "   MCP Server: ${MCP_SERVER_URL}"
echo "   Payer Party: ${PAYER_PARTY}"
echo ""

# Test: Call facilitator /payment-object directly to verify it works
echo "🔍 Step 1: Testing facilitator /payment-object endpoint directly..."
FACILITATOR_URL="http://46.224.109.63:3000"
MERCHANT_PARTY="damlcopilot-receiver::1220096316d4ea75c021d89123cfd2792cfeac80dfbf90bfbca21bcd8bf1bb40d84c"

PAYMENT_OBJECT_RESPONSE=$(curl -s -X POST "${FACILITATOR_URL}/payment-object" \
  -H "Content-Type: application/json" \
  -d "{
    \"amount\": \"0.10\",
    \"merchantParty\": \"${MERCHANT_PARTY}\",
    \"payerParty\": \"${PAYER_PARTY}\",
    \"resource\": \"http://localhost:7284/mcp\",
    \"description\": \"Test payment for daml_reason tool\"
  }" || echo "")

if [ -z "$PAYMENT_OBJECT_RESPONSE" ]; then
    echo "   ❌ Failed to get payment object from facilitator"
    exit 1
fi

echo "   ✅ Payment object received from facilitator"
echo "   Response (first 500 chars):"
echo "$PAYMENT_OBJECT_RESPONSE" | python3 -m json.tool 2>/dev/null | head -30 || echo "$PAYMENT_OBJECT_RESPONSE" | head -30
echo ""

# Check if TransferFactory is present
TRANSFER_FACTORY=$(echo "$PAYMENT_OBJECT_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    factory = data.get('paymentObject', {}).get('transferFactory', {})
    if factory:
        print('✅ TransferFactory found')
        print(f'   Contract ID: {factory.get(\"contractId\", \"N/A\")[:50]}...')
        print(f'   Disclosed contracts: {len(factory.get(\"disclosedContracts\", []))}')
    else:
        print('❌ TransferFactory not found')
except Exception as e:
    print(f'Error: {e}')
" 2>/dev/null || echo "Could not parse response")

echo "$TRANSFER_FACTORY"
echo ""

echo "✅ Payment requirements generation test completed!"
echo ""
echo "Note: The MCP server tools are currently free (\$0.00), so payment verification"
echo "is skipped. To test the full 402 flow, you would need to:"
echo "1. Set a price for the tool (in tool pricing configuration)"
echo "2. Or test with a tool that has a non-zero price"
echo ""
