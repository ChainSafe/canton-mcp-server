#!/usr/bin/env bash
set -e

# Canton MCP Server startup script
cd "$(dirname "$0")"

# Load environment if .env.canton exists
if [ -f .env.canton ]; then
    echo "📝 Loading configuration from .env.canton"
    export $(grep -v '^#' .env.canton | xargs)
fi

# Use uv if available, fall back to python -m
if command -v uv &> /dev/null; then
    echo "🚀 Starting Canton MCP Server with uv..."
    exec uv run canton-mcp-server serve
elif command -v canton-mcp-server &> /dev/null; then
    echo "🚀 Starting Canton MCP Server..."
    exec canton-mcp-server serve
else
    echo "🚀 Starting Canton MCP Server with python -m..."
    exec python -m canton_mcp_server.cli serve
fi
