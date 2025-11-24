#!/bin/bash
# Update canonical DAML documentation repositories
# This script is deployed to /opt/update-canonical-repos.sh on the server

set -e

echo "=========================================="
echo "Updating Canonical DAML Repositories"
echo "$(date)"
echo "=========================================="

REPOS=(
  "/opt/canonical-daml-docs-daml"
  "/opt/canonical-daml-docs-canton"
  "/opt/canonical-daml-docs-daml-finance"
)

for repo in "${REPOS[@]}"; do
  if [ -d "$repo" ]; then
    echo ""
    echo "📦 Updating $repo..."
    cd "$repo"
    
    # Fetch latest changes
    git fetch origin
    
    # Get current and new commit
    OLD_COMMIT=$(git rev-parse HEAD)
    git reset --hard origin/main
    NEW_COMMIT=$(git rev-parse HEAD)
    
    if [ "$OLD_COMMIT" = "$NEW_COMMIT" ]; then
      echo "   ✅ Already up to date ($NEW_COMMIT)"
    else
      echo "   ✅ Updated: $OLD_COMMIT -> $NEW_COMMIT"
    fi
  else
    echo "⚠️  Repository not found: $repo"
  fi
done

echo ""
echo "🔄 Restarting Canton MCP Server..."
cd /opt/canton-mcp-server
docker compose restart

echo ""
echo "=========================================="
echo "✅ Update complete!"
echo "=========================================="

