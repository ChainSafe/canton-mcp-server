#!/bin/bash
# Fix Production Issues
# Addresses the issues found in deployment

set -e

SSH_HOST="${SSH_HOST:-devops@91.99.186.83}"
SERVER_PATH="/opt/canton-mcp-server"

echo "🔧 Fixing Canton MCP Server Production Issues"
echo ""

# ============================================
# Fix 1: Install DAML SDK in Docker Container
# ============================================
echo "📦 Fix 1: Installing DAML SDK in Docker Container"
echo "This will update the Dockerfile to include DAML SDK..."
echo ""

cat > /tmp/dockerfile_daml_patch << 'EOF'

# Install DAML SDK
RUN apt-get update && apt-get install -y \
    curl \
    openjdk-21-jdk \
    && rm -rf /var/lib/apt/lists/*

# Install DAML SDK (latest stable)
RUN curl -sSL https://get.daml.com/ | sh -s 3.4.0 && \
    echo 'export PATH="$HOME/.daml/bin:$PATH"' >> ~/.bashrc

# Add DAML to PATH
ENV PATH="/root/.daml/bin:${PATH}"
EOF

echo "Add the following to your Dockerfile after the base image:"
cat /tmp/dockerfile_daml_patch
echo ""
echo "Would you like me to update the Dockerfile automatically? (We'll review it first)"
echo ""

# ============================================
# Fix 2: Create .env.canton Template
# ============================================
echo "📝 Fix 2: Creating .env.canton on server"
echo "Creating .env.canton file with template..."
echo ""

ssh "$SSH_HOST" bash << 'ENDSSH'
cd /opt/canton-mcp-server

# Create .env.canton if it doesn't exist
if [ ! -f .env.canton ]; then
    cat > .env.canton << 'EOF'
# Canton MCP Server Environment Configuration

# ============================================
# LLM Configuration
# ============================================
# Anthropic API Key (for LLM-based authorization extraction)
# Get your key from: https://console.anthropic.com/
ANTHROPIC_API_KEY=

# Enable LLM-based authorization extraction
ENABLE_LLM_AUTH_EXTRACTION=true

# ============================================
# DCAP Configuration (Optional)
# ============================================
# Semantic discovery via DCAP
DCAP_ENABLED=false
DCAP_SERVER_URL=
DCAP_SERVER_ID=canton-mcp-prod
DCAP_SERVER_NAME=Canton MCP Production Server

# ============================================
# X402 Payment Configuration (Optional)
# ============================================
# Micropayment system for paid API access
X402_ENABLED=false
X402_WALLET_ADDRESS=
X402_WALLET_PRIVATE_KEY=
X402_NETWORK=base-sepolia
X402_TOKEN=USDC

# ============================================
# Server Configuration
# ============================================
LOG_LEVEL=info
EOF
    
    chmod 600 .env.canton
    echo "✅ Created .env.canton template"
    echo "⚠️  Please add your ANTHROPIC_API_KEY to .env.canton"
else
    echo "✅ .env.canton already exists"
fi
ENDSSH

echo ""

# ============================================
# Fix 3: Verify Cronjob
# ============================================
echo "⏰ Fix 3: Verifying Cronjob"
ssh "$SSH_HOST" bash << 'ENDSSH'
# Check if cronjob exists
if ! crontab -l 2>/dev/null | grep -q "update-canonical-repos"; then
    echo "⚠️  Cronjob not found. Adding it now..."
    
    # Get current crontab
    crontab -l 2>/dev/null > /tmp/current_cron || true
    
    # Add new cronjob
    echo "0 3 * * * /opt/update-canonical-repos.sh >> /var/log/canton-repo-updates.log 2>&1" >> /tmp/current_cron
    
    # Install new crontab
    crontab /tmp/current_cron
    rm /tmp/current_cron
    
    echo "✅ Cronjob added (runs daily at 3am)"
else
    echo "✅ Cronjob already configured"
    crontab -l | grep update-canonical-repos
fi
ENDSSH

echo ""

# ============================================
# Summary
# ============================================
echo "════════════════════════════════════════"
echo "✅ Fixes Applied"
echo "════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "1. Update Dockerfile to include DAML SDK (see above)"
echo "2. Add ANTHROPIC_API_KEY to /opt/canton-mcp-server/.env.canton on server"
echo "3. Rebuild and restart: cd $SERVER_PATH && docker compose up -d --build"
echo "4. Test the server: curl http://91.99.186.83:7284/health"
echo ""



