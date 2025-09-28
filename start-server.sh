#!/bin/bash
cd "$(dirname "$0")"
exec /opt/homebrew/bin/uv run canton-mcp-server serve
