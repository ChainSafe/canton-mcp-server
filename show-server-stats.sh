#!/bin/bash
# Show statistics for all MCP servers

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║         Canton MCP Multi-Server Statistics                     ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Container status
echo "📊 Container Status:"
echo "─────────────────────────────────────────────────────────────────"
docker-compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
echo ""

# Test container call distribution
echo "📞 Test Container Call Distribution:"
echo "─────────────────────────────────────────────────────────────────"
echo "Server 1 (7284): $(docker-compose logs mcp-tester | grep -c 'canton-mcp-server →') calls"
echo "Server 2 (7285): $(docker-compose logs mcp-tester | grep -c 'canton-mcp-server-2 →') calls"
echo "Server 3 (7286): $(docker-compose logs mcp-tester | grep -c 'canton-mcp-server-3 →') calls"
echo ""

# Success rates
echo "✅ Success/Failure Rates:"
echo "─────────────────────────────────────────────────────────────────"
TOTAL=$(docker-compose logs mcp-tester | grep -c "Calling")
SUCCESS=$(docker-compose logs mcp-tester | grep -c "✅")
FAILED=$(docker-compose logs mcp-tester | grep -c "❌")
ERRORS=$(docker-compose logs mcp-tester | grep -c "⚠️")

echo "Total calls:  $TOTAL"
echo "Successful:   $SUCCESS ($(echo "scale=1; $SUCCESS * 100 / $TOTAL" | bc 2>/dev/null || echo "N/A")%)"
echo "Failed:       $FAILED"
echo "Tool errors:  $ERRORS"
echo ""

# DCAP Configuration
echo "📡 DCAP Configuration:"
echo "─────────────────────────────────────────────────────────────────"
echo "Server 1: $(docker-compose exec -T canton-mcp-server env | grep DCAP_SERVER_ID | cut -d'=' -f2 | tr -d '\r')"
echo "Server 2: $(docker-compose exec -T canton-mcp-server-2 env | grep DCAP_SERVER_ID | cut -d'=' -f2 | tr -d '\r')"
echo "Server 3: $(docker-compose exec -T canton-mcp-server-3 env | grep DCAP_SERVER_ID | cut -d'=' -f2 | tr -d '\r')"
echo "Target:   $(docker-compose exec -T canton-mcp-server env | grep DCAP_MULTICAST_IP | cut -d'=' -f2 | tr -d '\r'):$(docker-compose exec -T canton-mcp-server env | grep DCAP_PORT | cut -d'=' -f2 | tr -d '\r')"
echo ""

# Recent activity
echo "🕐 Recent Activity (Last 10 calls):"
echo "─────────────────────────────────────────────────────────────────"
docker-compose logs --tail 100 mcp-tester | grep "Calling" | tail -10
echo ""

echo "💡 Tip: Run 'docker-compose logs -f mcp-tester' to watch live"

