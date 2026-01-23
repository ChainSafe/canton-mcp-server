#!/bin/bash
# Quick setup script to enable Canton payments for local testing
# This temporarily updates .env.canton with test settings

set -e

echo "🔧 Setting up local test environment..."
echo ""

# Backup existing .env.canton
if [ -f .env.canton ]; then
    cp .env.canton .env.canton.backup
    echo "✅ Backed up .env.canton to .env.canton.backup"
fi

# Add/update Canton configuration
echo ""
echo "Updating .env.canton with test configuration..."
echo ""

# Update Canton settings using sed (more reliable)
echo "Updating Canton settings in .env.canton..."

# Remove existing Canton settings (if any)
sed -i.bak '/^CANTON_ENABLED=/d; /^CANTON_FACILITATOR_URL=/d; /^CANTON_PAYEE_PARTY=/d; /^CANTON_NETWORK=/d' .env.canton 2>/dev/null || true

# Append new settings
cat >> .env.canton << 'ENVEOF'

# Canton Payment Test Configuration (added for testing)
CANTON_ENABLED=true
CANTON_FACILITATOR_URL=http://46.224.109.63:3000
CANTON_PAYEE_PARTY=damlcopilot-receiver::1220096316d4ea75c021d89123cfd2792cfeac80dfbf90bfbca21bcd8bf1bb40d84c
CANTON_NETWORK=canton-devnet
ENVEOF

echo "✅ Updated .env.canton with:"
echo "   CANTON_ENABLED=true"
echo "   CANTON_FACILITATOR_URL=http://46.224.109.63:3000"
echo "   CANTON_PAYEE_PARTY=damlcopilot-receiver::..."
echo "   CANTON_NETWORK=canton-devnet"

echo ""
echo "✅ Environment configured for testing!"
echo ""
echo "To restore original settings:"
echo "  cp .env.canton.backup .env.canton"
echo ""

