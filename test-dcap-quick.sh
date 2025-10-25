#!/bin/bash
# Quick DCAP Test Script
# Tests if Canton MCP Server is sending DCAP performance updates

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║       DCAP Performance Updates Test                            ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check if listener script exists
if [ ! -f "test-dcap-listener.py" ]; then
    echo "❌ test-dcap-listener.py not found!"
    exit 1
fi

# Check current DCAP configuration
echo "📋 Current DCAP Configuration:"
echo "─────────────────────────────────"
docker-compose exec -T canton-mcp-server env | grep DCAP || echo "⚠️  DCAP variables not set"
echo ""

# Check if DCAP is enabled
DCAP_IP=$(docker-compose exec -T canton-mcp-server env | grep DCAP_MULTICAST_IP | cut -d'=' -f2 | tr -d '\r')

if [ -z "$DCAP_IP" ]; then
    echo "⚠️  DCAP_MULTICAST_IP is not configured!"
    echo ""
    echo "To enable DCAP, run:"
    echo ""
    echo "  # Using host.docker.internal (Mac/Windows):"
    echo "  DCAP_MULTICAST_IP=host.docker.internal docker-compose up -d"
    echo ""
    echo "  # Or using your host IP (Linux):"
    echo "  DCAP_MULTICAST_IP=\$(hostname -I | awk '{print \$1}') docker-compose up -d"
    echo ""
    exit 1
fi

echo "✅ DCAP is configured to send to: $DCAP_IP"
echo ""

# Offer to start listener
echo "📡 Ready to test DCAP"
echo "─────────────────────────────────"
echo ""
echo "In a separate terminal, run:"
echo ""
echo "  python3 test-dcap-listener.py"
echo ""
echo "Then trigger a tool call:"
echo ""
echo "  curl -X POST http://localhost:7284/mcp \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"get_canonical_resource_overview\",\"arguments\":{}}}'"
echo ""
echo "Or just wait for the test container to make calls (it calls every 30-300 seconds)"
echo ""
echo "You should see DCAP messages appear in the listener!"
echo ""

