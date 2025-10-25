#!/bin/bash
# Test MCP Tool Calls

BASE_URL="http://localhost:7284/mcp"

echo "=== Testing MCP Tools ==="
echo ""

# 1. List all tools
echo "1. List available tools:"
curl -s -X POST "$BASE_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/list",
    "params": {}
  }' | python3 -m json.tool | grep -E '"name"|"description"' | head -20

echo ""
echo ""

# 2. Get canonical resource overview
echo "2. Get canonical resource overview:"
curl -s -X POST "$BASE_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "get_canonical_resource_overview",
      "arguments": {}
    }
  }' | python3 -m json.tool | head -40

echo ""
echo ""

# 3. Recommend resources
echo "3. Recommend canonical resources for asset transfer:"
curl -s -X POST "$BASE_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "recommend_canonical_resources",
      "arguments": {
        "useCase": "asset_transfer",
        "description": "I need to transfer ownership of digital assets between parties",
        "securityLevel": "basic"
      }
    }
  }' | python3 -m json.tool | head -50

echo ""
echo ""

# 4. Validate DAML code
echo "4. Validate simple DAML code:"
curl -s -X POST "$BASE_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "validate_daml_business_logic",
      "arguments": {
        "businessIntent": "Transfer asset ownership",
        "damlCode": "template Asset\n  with\n    owner: Party\n  where\n    signatory owner"
      }
    }
  }' | python3 -m json.tool | head -50

echo ""
echo "=== Test complete ==="
