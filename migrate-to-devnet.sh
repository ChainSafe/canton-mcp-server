#!/bin/bash
# Canton MCP Server - DevNet Migration Script
# This script helps migrate from localnet to devnet configuration

set -e

echo "================================================"
echo "Canton MCP Server - DevNet Migration"
echo "================================================"
echo ""

# Check if running in correct directory
if [ ! -f ".env.canton" ]; then
    echo "❌ Error: .env.canton not found"
    echo "   Run this script from /home/skynet/canton/canton-mcp-server"
    exit 1
fi

# Backup current config
BACKUP_FILE=".env.canton.localnet.backup.$(date +%Y%m%d_%H%M%S)"
echo "📦 Backing up current .env.canton to $BACKUP_FILE"
cp .env.canton "$BACKUP_FILE"

# Check if devnet template exists
if [ ! -f ".env.canton.devnet" ]; then
    echo "❌ Error: .env.canton.devnet template not found"
    echo "   Expected at: /home/skynet/canton/canton-mcp-server/.env.canton.devnet"
    exit 1
fi

# Copy DevNet template
echo "📝 Copying DevNet template to .env.canton"
cp .env.canton.devnet .env.canton

echo ""
echo "✅ Migration template applied!"
echo ""
echo "================================================"
echo "⚠️  REQUIRED: Update these values in .env.canton"
echo "================================================"
echo ""
echo "1. OAuth2 Credentials (get from ChainSafe):"
echo "   CANTON_OAUTH_CLIENT_ID=YOUR_AUTH0_CLIENT_ID"
echo "   CANTON_OAUTH_CLIENT_SECRET=YOUR_AUTH0_CLIENT_SECRET"
echo "   CANTON_USER_ID=YOUR_AUTH0_USER_ID"
echo ""
echo "2. Your DevNet Party IDs:"
echo "   CANTON_PAYEE_PARTY=your-party::1220..."
echo "   CANTON_PROVIDER_PARTY=your-party::1220..."
echo ""
echo "3. Package ID (after deploying DAR):"
echo "   BILLING_PACKAGE_ID=your-package-id"
echo ""
echo "4. Billing Portal URL (if deployed):"
echo "   BILLING_PORTAL_URL=https://your-devnet-billing-portal.com"
echo ""
echo "================================================"
echo "📖 Next Steps"
echo "================================================"
echo ""
echo "1. Read the migration guide:"
echo "   cat DEVNET_MIGRATION_GUIDE.md"
echo ""
echo "2. Edit .env.canton with your credentials:"
echo "   nano .env.canton"
echo ""
echo "3. Test OAuth2 authentication:"
echo "   curl -X POST https://dev-2j3m40ajwym1zzaq.eu.auth0.com/oauth/token \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"grant_type\":\"client_credentials\",\"client_id\":\"YOUR_ID\",\"client_secret\":\"YOUR_SECRET\",\"audience\":\"https://canton.network.global\"}'"
echo ""
echo "4. Start the MCP server:"
echo "   python -m canton_mcp_server.server"
echo ""
echo "5. Check endpoints reference:"
echo "   cat DEVNET_ENDPOINTS.md"
echo ""
echo "📁 Your localnet config backed up to:"
echo "   $BACKUP_FILE"
echo ""
