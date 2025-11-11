#!/bin/bash
# Test script for canonical resource caching and hot-reload

echo "🧪 Testing Canonical Resource Caching & Hot-Reload"
echo "=================================================="
echo ""

# Check if repos exist
CANONICAL_DOCS_PATH="${CANONICAL_DOCS_PATH:-/Users/martinmaurer/Projects/Martin/canonical-daml-docs}"

if [ ! -d "$CANONICAL_DOCS_PATH" ]; then
    echo "❌ Error: Canonical docs path not found: $CANONICAL_DOCS_PATH"
    exit 1
fi

echo "✅ Found canonical repos at: $CANONICAL_DOCS_PATH"
echo ""

# Check cache directory
CACHE_DIR="$HOME/.canton-mcp"
echo "📁 Cache directory: $CACHE_DIR"

if [ -d "$CACHE_DIR" ]; then
    echo "   Existing cache files:"
    ls -lh "$CACHE_DIR"/resource-cache-*.json 2>/dev/null || echo "   (none)"
else
    echo "   (cache directory will be created)"
fi
echo ""

# Test 1: First run (cold start - no cache)
echo "Test 1: Cold Start (no cache)"
echo "------------------------------"
rm -f "$CACHE_DIR"/resource-cache-*.json
echo "Starting server (this will take a while to scan repos)..."
echo "Press Ctrl+C after you see 'Found XXXX documentation files'"
echo ""

export CANONICAL_DOCS_PATH="$CANONICAL_DOCS_PATH"
uv run canton-mcp-server

echo ""
echo "Test 1 complete!"
echo ""

# Check if cache was created
echo "Test 2: Verify Cache Creation"
echo "------------------------------"
if [ -f "$CACHE_DIR"/resource-cache-*.json ]; then
    CACHE_FILE=$(ls "$CACHE_DIR"/resource-cache-*.json | head -1)
    CACHE_SIZE=$(du -h "$CACHE_FILE" | cut -f1)
    echo "✅ Cache file created: $(basename "$CACHE_FILE")"
    echo "   Size: $CACHE_SIZE"
    
    # Show commit hashes in cache
    echo "   Commit hashes:"
    cat "$CACHE_FILE" | grep -A 10 "commit_hashes" | head -15
else
    echo "❌ No cache file found!"
fi
echo ""

# Test 3: Second run (warm start - with cache)
echo "Test 3: Warm Start (with cache)"
echo "--------------------------------"
echo "Starting server again (should be INSTANT from cache)..."
echo "Press Ctrl+C after you see 'Loaded from disk cache'"
echo ""

uv run canton-mcp-server

echo ""
echo "Test 3 complete!"
echo ""

# Test 4: Hot-reload test
echo "Test 4: Hot-Reload Test (optional)"
echo "-----------------------------------"
echo "To test hot-reload:"
echo "1. Start server with: CANTON_HOT_RELOAD=true uv run canton-mcp-server"
echo "2. In another terminal, cd to one of the canonical repos"
echo "3. Run: git pull"
echo "4. Watch server logs for automatic reload message"
echo ""
echo "Expected log messages:"
echo "  - '🔥 Started hot-reload watcher for canonical repositories'"
echo "  - '📦 Commit hashes changed: ...'"
echo "  - '🔄 Reloading canonical resources...'"
echo "  - '✅ Resources reloaded after git pull'"
echo ""

echo "🎉 Testing complete!"

