# DCAP Configuration Guide

This document describes the environment variables needed to enable DCAP semantic_discover broadcasting for the Canton MCP Server.

## Overview

The Canton MCP Server now supports **DCAP v2.5 semantic_discover** broadcasting, which advertises all available tools to the DCAP network. This allows Semanticore and other intelligence systems to discover and route agents to your tools.

## Architecture

**Phase 1: Raw Advertisement (This Server)**
- Broadcasts `semantic_discover` messages with tool metadata and `connector` object
- Includes: tool name, description, connection details, x402 payment requirements
- Semantic fields (`when`, `good_at`, `bad_at`) are left **empty**

**Phase 2: Intelligence Enrichment (Semanticore)**
- Listens to raw `semantic_discover` messages and stores tools
- Observes `perf_update` messages to build intelligence
- Fills semantic fields based on observed usage patterns
- Returns enriched tool recommendations to agents

## Required Environment Variables

### Core DCAP Settings

```bash
# Enable DCAP broadcasting (default: true)
DCAP_ENABLED=true

# Target IP for DCAP UDP broadcasts
# Production relay: 159.89.110.236
DCAP_MULTICAST_IP=159.89.110.236

# DCAP UDP port (default: 10191)
DCAP_PORT=10191

# Server identifier (used in DCAP messages)
DCAP_SERVER_ID=canton-mcp

# Human-readable server name
DCAP_SERVER_NAME=Canton MCP Server
```

### Semantic Discover Settings (New in v2.5)

```bash
# Full MCP endpoint URL (REQUIRED for semantic_discover)
# This should be the publicly accessible URL where agents can connect
# Examples:
#   - Production: https://canton.example.com/mcp
#   - Development: http://localhost:7284/mcp
DCAP_SERVER_URL=http://localhost:7284/mcp

# Interval for periodic semantic_discover broadcasts (in seconds)
# Default: 300 (5 minutes)
DCAP_DISCOVER_INTERVAL_SEC=300
```

### Optional Fallback Settings

```bash
# Fallback caller identifier (used when X-Caller-ID header is missing)
DCAP_DEFAULT_CALLER=unknown-client

# Fallback payer address (used when x402 payment info is unavailable)
DCAP_DEFAULT_PAYER=0x0000000000000000000000000000000000000000
```

## How It Works

### 1. Startup Broadcasting

When the server starts, it:
1. Loads all registered tools
2. Broadcasts a `semantic_discover` message for each tool
3. Logs: `📡 Broadcasting {N} tools to DCAP network...`

### 2. Periodic Broadcasting

A background task re-broadcasts all tools every `DCAP_DISCOVER_INTERVAL_SEC` seconds (default: 5 minutes).

This ensures:
- New Semanticore instances discover existing tools
- Tool metadata stays fresh in the network
- Price changes are propagated

### 3. Message Format (DCAP v2.5)

```json
{
  "v": 2,
  "t": "semantic_discover",
  "ts": 1759843829,
  "sid": "canton-mcp",
  "tool": "validate_daml",
  "does": "Validates DAML smart contract syntax and semantics",
  "when": [],       // Empty - filled by Semanticore
  "good_at": [],    // Empty - filled by Semanticore
  "bad_at": [],     // Empty - filled by Semanticore
  "connector": {
    "transport": "sse",
    "endpoint": "http://localhost:7284/mcp",
    "auth": {
      "type": "x402",
      "required": true,
      "details": {
        "network": "base-sepolia",
        "asset": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        "price_per_call": 50000,
        "currency": "USDC"
      }
    },
    "protocol": {
      "type": "mcp",
      "version": "2024-11-05",
      "methods": ["tools/list", "tools/call"]
    }
  }
}
```

## Testing

### 1. Check Logs on Startup

```bash
npm start
# or
python -m canton_mcp_server.server
```

You should see:
```
📡 Broadcasting 5 tools to DCAP network...
✅ Broadcast complete: 5 tools advertised
📡 DCAP semantic_discover broadcasting enabled (interval: 300s)
```

### 2. Listen for UDP Messages

Use the test listener script:

```bash
cd /path/to/canton-mcp-server
python test-dcap-listener.py
```

You should see `semantic_discover` messages for each tool.

### 3. Check Relay WebSocket

Connect to the relay's `/raw` WebSocket stream:

```bash
wscat -c ws://159.89.110.236:10191/raw
```

You should see your `semantic_discover` messages in the stream.

## Troubleshooting

### No messages broadcast on startup

**Check:**
1. `DCAP_ENABLED=true`
2. `DCAP_MULTICAST_IP` is set
3. `DCAP_SERVER_URL` is set

**Logs:**
- ⚠️ "DCAP not enabled - no IP configured" → Set `DCAP_MULTICAST_IP`
- ⚠️ "DCAP enabled but DCAP_SERVER_URL not configured" → Set `DCAP_SERVER_URL`

### Messages too large (>65KB)

If you see:
```
⚠️ Large DCAP message (70000 bytes) for tool_name - may require IP fragmentation
```

This is **expected** for tools with complex schemas. UDP/IP handles fragmentation automatically up to ~65KB.

If messages exceed 65KB:
- Simplify tool descriptions
- Reduce schema complexity
- Contact the DCAP team for protocol extension

### Firewall blocking UDP

Ensure your firewall allows outbound UDP traffic to `DCAP_MULTICAST_IP:DCAP_PORT`.

## Integration with x402 Payments

If `X402_ENABLED=true`, the `connector.auth` object will include payment details:

```json
"auth": {
  "type": "x402",
  "required": true,
  "details": {
    "network": "base-sepolia",
    "asset": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    "price_per_call": 50000,
    "currency": "USDC"
  }
}
```

Otherwise, it will be:

```json
"auth": {
  "type": "none",
  "required": false
}
```

## See Also

- [DCAP Specification v2.5](https://github.com/martinmaurer/dcap/blob/main/DCAP-v2.5.md)
- [Test DCAP Setup](./TEST_DCAP.md)
- [Multi-Server Setup](./MULTI_SERVER_SETUP.md)

