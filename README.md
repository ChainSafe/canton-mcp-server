# Canton MCP Server

[![CI](https://github.com/ChainSafe/canton-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/ChainSafe/canton-mcp-server/actions/workflows/ci.yml)

AI-powered DAML development tools via Model Context Protocol. Provides code analysis, pattern recommendations, and automated Canton environment management.

## Quick Start

```bash
# 1. Clone and start with Docker
git clone <repository-url>
cd canton-mcp-server
docker-compose up -d

# 2. Verify it's running
curl http://localhost:7284/health

# 3. Use with Cursor or Claude Desktop
# Add to your MCP config (see Configuration below)
```

**Server URL:** `http://localhost:7284/mcp`

## Available Tools

### `daml_reason`
Analyze DAML code, recommend patterns, validate business logic.

**Use for:** Code review, pattern suggestions, security analysis

### `daml_automater`  
Automate Canton environments, tests, and builds.

**Use for:** Spinning up Canton networks, running tests, building DARs

## Configuration

### For Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "canton-mcp": {
      "type": "sse",
      "url": "http://<you-server-ip-or.domain>:7284/mcp",
      "headers": {
        "X-Canton-Party-ID": "your-party::1220abc..."
      }
    }
  }
}
```

### For Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "canton": {
      "command": "docker",
      "args": ["exec", "canton-mcp-server", "uv", "run", "canton-mcp-server", "serve"]
    }
  }
}
```

### Environment Variables

Create `.env.canton`:

```bash
# Server
MCP_SERVER_URL=http://localhost:7284

# x402 Payments (REQUIRED for production)
CANTON_ENABLED=true
CANTON_FACILITATOR_URL=http://46.224.109.63:3000
CANTON_PAYEE_PARTY=damlcopilot-receiver::1220...
CANTON_NETWORK=canton-devnet

# DCAP Performance Tracking (optional)
DCAP_ENABLED=true
DCAP_MULTICAST_IP=159.89.110.236
DCAP_PORT=10191

# Canonical docs path (optional, defaults to ../../canonical-daml-docs)
CANONICAL_DOCS_PATH=/path/to/canonical-daml-docs
```

## Installation

### Docker (Recommended)

```bash
docker-compose up -d
docker-compose logs -f
```

### Local Development

```bash
# Using uv (recommended)
uv sync
uv run canton-mcp-server

# Using pip
pip install -e .
canton-mcp-server
```

## Prerequisites

### Canonical DAML Docs (Required)

The server needs access to official DAML repositories for pattern recommendations:

```bash
# Create canonical docs directory (parallel to server)
mkdir -p ../canonical-daml-docs
cd ../canonical-daml-docs

# Clone official repos
git clone https://github.com/digital-asset/daml.git
git clone https://github.com/digital-asset/canton.git
git clone https://github.com/digital-asset/daml-finance.git
```

**Expected structure:**
```
your-projects/
├── canonical-daml-docs/
│   ├── daml/
│   ├── canton/
│   └── daml-finance/
└── canton-mcp-server/
```

Set custom path via `CANONICAL_DOCS_PATH` environment variable if needed.

## x402 Payments

**IMPORTANT:** When using a production/public server, **always include your party ID**:

```bash
# In headers
X-Canton-Party-ID: your-party::1220abc...

# Or in URL
http://server:7284/mcp?payerParty=your-party::1220abc...
```

**Without a party ID, requests will be rejected** (security protection against free access).

**Payment flow:**
1. Tool call requires payment ($0.10 per call)
2. Server registers payment requirement with facilitator
3. Wallet executes payment on Canton blockchain
4. Server verifies payment and processes request

See [canton-x402-facilitator](https://github.com/ChainSafe/canton-x402-facilitator) for payment infrastructure setup.

## Testing

```bash
# List available tools
curl -X POST http://localhost:7284/mcp \
  -H "Content-Type: application/json" \
  -H "X-Canton-Party-ID: your-party::123" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# Call daml_reason
curl -X POST http://localhost:7284/mcp \
  -H "Content-Type: application/json" \
  -H "X-Canton-Party-ID: your-party::123" \
  -d '{
    "jsonrpc":"2.0",
    "id":2,
    "method":"tools/call",
    "params":{
      "name":"daml_reason",
      "arguments":{"businessIntent":"Create a simple IOU contract"}
    }
  }'

# Interactive testing
npx @modelcontextprotocol/inspector http://localhost:7284/mcp
```

## Documentation

- **[CANTON_X402_INTEGRATION.md](./CANTON_X402_INTEGRATION.md)** - Payment integration guide
- **[DEPLOYMENT_SETUP.md](./DEPLOYMENT_SETUP.md)** - Production deployment
- **[QUICK_START.md](./QUICK_START.md)** - Detailed setup guide

## Development

```bash
# Install dev dependencies
uv sync --dev

# Run server
uv run python -m canton_mcp_server.server

# Run tests
pytest
```

## Architecture

**Simple stack:**
- FastAPI server with HTTP+SSE transport
- Two MCP tools (daml_reason, daml_automater)
- x402 payment integration (Canton Coin)
- DCAP performance tracking
- Canonical resource recommendations

**Payment philosophy:**
- No rate limiting (payment IS the limiter)
- No authentication (permissionless by design)
- Single requirement: proof of payment

## Contributing

1. Fork the repository
2. Create a feature branch  
3. Make your changes
4. Submit a pull request

## License

MIT License - see LICENSE file for details.
