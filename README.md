# Canton MCP Server

[![CI](https://github.com/ChainSafe/canton-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/ChainSafe/canton-mcp-server/actions/workflows/ci.yml)

A **DAML-Safe by Construction** development platform that generates provably safe DAML code using verified canonical resources, DAML compiler integration, and Haskell's formal verification capabilities.

## Core Philosophy: "DAML-Safe by Construction"

**Leverage DAML compiler's existing mathematical proofs. Extend with safety annotations and formal verification.**

## Features

### 🛡️ **Safe Code Generation**
- **DAML Compiler Integration**: All patterns validated through DAML compilation
- **Safety Annotations**: Add safety metadata to DAML templates
- **Safe Code Generation**: Generate provably safe DAML code
- **Safety Certificates**: Mathematical proof of code safety

### 🔍 **Enhanced Validation Tools**
- **DAML Code Validation**: Validate against canonical patterns with DAML compiler safety
- **Authorization Debugging**: Debug with DAML's built-in authorization model
- **Pattern Suggestions**: Get recommendations from DAML-compiler-validated patterns
- **Compilation Validation**: Validate DAML compilation safety

### 📚 **Canonical Resources**
- **3,667+ Documentation Files**: From official DAML, Canton, and DAML Finance repositories
- **Git-Verified Content**: All resources verified via GitHub API
- **Structured Ingestion**: Categorized by use case, security level, and complexity
- **Intelligent Recommendations**: AI-powered resource suggestions
- **LLM Enrichment** (Optional): Claude Haiku 3.5-based metadata enrichment for better search relevance

### 🚀 **Production Infrastructure**
- **DCAP Performance Tracking**: Real-time performance monitoring via DCAP v2 protocol
- **x402 Payment Infrastructure**: Built-in payment support (disabled by default)
- **HTTP+SSE Transport**: Streaming support with Server-Sent Events
- **Type-Safe Tools**: Fully typed parameters and results using Pydantic models

## Prerequisites

### Required: Canonical DAML Documentation Repositories

**⚠️ CRITICAL**: The Canton MCP Server requires access to official DAML documentation repositories to function. The server loads canonical patterns, anti-patterns, and documentation directly from these repos.

#### 1. Clone the Official Repositories

Clone these three repositories into a directory called `canonical-daml-docs`:

```bash
# Navigate to your projects directory (e.g., where you'll clone canton-mcp-server)
cd /path/to/your/projects

# Create and populate canonical-daml-docs directory
mkdir canonical-daml-docs
cd canonical-daml-docs

# Clone the three official repositories
git clone https://github.com/digital-asset/daml.git
git clone https://github.com/digital-asset/canton.git
git clone https://github.com/digital-asset/daml-finance.git

cd ..
```

**Expected directory structure:**

**Option A** (common setup):
```
your-projects/
├── canonical-daml-docs/
│   ├── daml/                    # Official DAML SDK
│   ├── canton/                  # Canton blockchain
│   └── daml-finance/            # DAML Finance libraries
└── servers/
    └── canton-mcp-server/       # This repository (default: ../../canonical-daml-docs)
```

**Option B** (flat structure):
```
your-projects/
├── canonical-daml-docs/
│   ├── daml/
│   ├── canton/
│   └── daml-finance/
└── canton-mcp-server/           # This repository (set CANONICAL_DOCS_PATH=../canonical-daml-docs)
```

#### 2. Configure the Path

The server looks for canonical docs in `../../canonical-daml-docs` by default (two directories up).

This matches **Option A** above. For **Option B** or custom setups, set the `CANONICAL_DOCS_PATH` environment variable.

**If your directory structure is different**, set the `CANONICAL_DOCS_PATH` environment variable:

```bash
# Option 1: Set in .env.canton file
echo "CANONICAL_DOCS_PATH=/absolute/path/to/canonical-daml-docs" >> .env.canton

# Option 2: Set in your shell
export CANONICAL_DOCS_PATH=/absolute/path/to/canonical-daml-docs

# Option 3: Use relative path
export CANONICAL_DOCS_PATH=../../some-other-location/canonical-daml-docs
```

#### 3. Verify Setup

After starting the server, check the logs for:
```
✅ Loaded canonical resources from: /path/to/canonical-daml-docs
   - DAML: X files
   - Canton: Y files  
   - DAML Finance: Z files
```

**Without these repositories, resource recommendation tools will not work!**

## Installation

### System Requirements

- Python 3.10 or higher
- uv (recommended) or pip
- Git (for cloning canonical repositories)

### Using uv (recommended)

```bash
# Clone and install
git clone <repository-url>
cd canton-mcp-server
uv sync

# Run the server
uv run canton-mcp-server
```

### Using pip

```bash
# Install from source
pip install -e .

# Run the server
canton-mcp-server
```

### Using Docker (recommended for development)

```bash
# Clone the repository
git clone <repository-url>
cd canton-mcp-server

# Copy environment template (optional)
cp .env.canton.example .env.canton
# Edit .env.canton with your configuration

# Start with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the server
docker-compose down
```

The Docker setup includes:
- **Hot-reload**: Source code changes automatically reload (Python code only)
- **Health checks**: Automatic container health monitoring
- **Port mapping**: Server accessible at `http://localhost:7284`
- **Resource files**: Baked into image (rebuild to update)

**Useful commands:**
```bash
# Rebuild after resource changes
docker-compose up -d --build

# Access container shell
docker-compose exec canton-mcp-server bash

# View server logs
docker-compose logs -f canton-mcp-server

# Restart the server
docker-compose restart canton-mcp-server
```

**Note**: The Docker setup mounts source code for development. The server loads canonical resources from the `canonical-daml-docs` directory (see Prerequisites section).

### MCP Test Container

The Docker setup includes an automated test container (`mcp-tester`) that continuously validates the MCP server by making random tool calls at irregular intervals.

#### Overview

**Purpose:**
- Continuous integration testing
- Server availability monitoring
- Load testing and stress testing
- Tool functionality verification
- Real-world usage simulation

**Architecture:**
- Independent Python container
- Communicates with server via internal Docker network
- No external dependencies beyond requests library
- Automatic restart on failure
- Minimal resource footprint

**Files:**
```
test-container/
├── Dockerfile          # Python 3.12-slim image
├── requirements.txt    # requests>=2.32.0
└── mcp_tester.py      # Test orchestration script
```

#### Tools Tested

The container randomly calls all 5 MCP tools with realistic test data:

1. **validate_daml_business_logic**
   - Tests: DAML code validation engine
   - Sample: Simple asset transfer template

2. **debug_authorization_failure**
   - Tests: Authorization error analysis
   - Sample: Missing signatory error scenario

3. **suggest_authorization_pattern**
   - Tests: Pattern recommendation engine
   - Sample: Multi-party approval workflow

4. **get_canonical_resource_overview**
   - Tests: Resource registry and metadata
   - Sample: Full overview request

5. **recommend_canonical_resources**
   - Tests: Resource recommendation system
   - Sample: Asset transfer use case

#### Usage

**Basic Commands:**

```bash
# Start both server and tester
docker-compose up -d

# View live tester logs
docker-compose logs -f mcp-tester

# View last 50 log lines
docker-compose logs --tail 50 mcp-tester

# Stop only the tester (keep server running)
docker-compose stop mcp-tester

# Start only the tester
docker-compose start mcp-tester

# Restart tester
docker-compose restart mcp-tester

# Check tester status
docker-compose ps mcp-tester

# Remove tester completely
docker-compose rm -s -f mcp-tester
```

**Running Without Tester:**

To disable the test container permanently:

1. Edit `docker-compose.yml`
2. Comment out or remove the `mcp-tester` service section
3. Restart: `docker-compose up -d`

Or run only the server:

```bash
docker-compose up -d canton-mcp-server
```

#### Configuration

**Environment Variables:**

```bash
# Interval configuration
MIN_INTERVAL=30        # Minimum seconds between calls (default: 30)
MAX_INTERVAL=300       # Maximum seconds between calls (default: 300)

# Server URL (usually auto-configured)
MCP_SERVER_URL=http://canton-mcp-server:7284/mcp
```

**Set via docker-compose.yml:**

```yaml
services:
  mcp-tester:
    environment:
      - MIN_INTERVAL=60
      - MAX_INTERVAL=600
```

**Set via .env file:**

```bash
# .env file
MIN_INTERVAL=60
MAX_INTERVAL=600
```

**Set via command line:**

```bash
MIN_INTERVAL=60 MAX_INTERVAL=600 docker-compose up -d
```

#### Log Output

**Success Example:**

```
mcp-tester  | [2025-10-24 17:30:15] [INFO] 🚀 Starting MCP Test Container
mcp-tester  | [2025-10-24 17:30:15] [INFO]    Server: http://canton-mcp-server:7284/mcp
mcp-tester  | [2025-10-24 17:30:15] [INFO]    Interval: 30-300 seconds
mcp-tester  | [2025-10-24 17:30:15] [INFO]    Tools: 5 available
mcp-tester  | [2025-10-24 17:30:15] [INFO] 
mcp-tester  | [2025-10-24 17:30:15] [INFO] [#1] Calling tool: validate_daml_business_logic
mcp-tester  | [2025-10-24 17:30:16] [INFO]    ✅ Tool executed successfully
mcp-tester  | [2025-10-24 17:30:16] [INFO]    💤 Sleeping for 127 seconds...
mcp-tester  | [2025-10-24 17:30:16] [INFO] 
mcp-tester  | [2025-10-24 17:33:23] [INFO] [#2] Calling tool: debug_authorization_failure
mcp-tester  | [2025-10-24 17:33:23] [INFO]    ✅ Tool executed successfully
mcp-tester  | [2025-10-24 17:33:23] [INFO]    💤 Sleeping for 245 seconds...
```

**Error Handling:**

```
mcp-tester  | [2025-10-24 17:30:51] [ERROR] Request failed: Connection refused
mcp-tester  | [2025-10-24 17:30:51] [ERROR]    ❌ Call failed: Connection refused
mcp-tester  | [2025-10-24 17:30:51] [INFO]    💤 Sleeping for 33 seconds...
```

**Tool Error Example:**

```
mcp-tester  | [2025-10-24 17:31:24] [INFO] [#3] Calling tool: recommend_canonical_resources
mcp-tester  | [2025-10-24 17:31:24] [WARN]    ⚠️  Tool returned error
mcp-tester  | [2025-10-24 17:31:24] [INFO]    💤 Sleeping for 182 seconds...
```

#### Monitoring & Troubleshooting

**Check if tester is running:**

```bash
docker-compose ps mcp-tester
# Expected: "Up" status
```

**View real-time logs:**

```bash
docker-compose logs -f mcp-tester
# Press Ctrl+C to exit
```

**Count successful calls:**

```bash
docker-compose logs mcp-tester | grep "✅" | wc -l
```

**Count failed calls:**

```bash
docker-compose logs mcp-tester | grep "❌" | wc -l
```

**Check last call:**

```bash
docker-compose logs --tail 10 mcp-tester | grep "Calling tool"
```

**Common Issues:**

1. **Connection Refused** - Server not yet ready
   - Wait 10-15 seconds for server startup
   - Tester will automatically retry

2. **Tool Returns Error** - Expected for some tools during testing
   - Check server logs: `docker-compose logs canton-mcp-server`
   - Some errors are intentional test scenarios

3. **Tester Keeps Restarting** - Configuration issue
   - Check environment variables
   - Verify MIN_INTERVAL < MAX_INTERVAL

#### Use Cases

**Development:**
```bash
# Fast testing during development
MIN_INTERVAL=5 MAX_INTERVAL=30 docker-compose up -d
docker-compose logs -f mcp-tester
```

**Production Monitoring:**
```bash
# Less frequent for production
MIN_INTERVAL=300 MAX_INTERVAL=900 docker-compose up -d
```

**Load Testing:**
```bash
# Scale up multiple testers
docker-compose up -d --scale mcp-tester=5
```

**CI/CD Integration:**
```bash
# Start services
docker-compose up -d

# Wait for stability
sleep 30

# Check for errors
if docker-compose logs mcp-tester | grep -q "❌"; then
  echo "Test failures detected"
  exit 1
fi
```

#### Statistics

View aggregated test statistics:

```bash
# Total calls made
docker-compose logs mcp-tester | grep -c "Calling tool"

# Success rate
echo "Successful: $(docker-compose logs mcp-tester | grep -c '✅')"
echo "Failed: $(docker-compose logs mcp-tester | grep -c '❌')"
echo "Errors: $(docker-compose logs mcp-tester | grep -c '⚠️')"
```

## Configuration

The server uses environment variables for configuration. Create a `.env.canton` file (or set system environment variables):

```bash
# MCP Server Configuration
MCP_SERVER_URL=http://localhost:7284

# DCAP (Performance Tracking) - ENABLED by default
DCAP_ENABLED=true
DCAP_MULTICAST_IP=159.89.110.236  # UDP relay address (or use multicast like 239.255.0.1)
DCAP_PORT=10191

# x402 Payment Configuration - DISABLED by default

# Option 1: USDC on Base Sepolia (EVM)
X402_ENABLED=false
X402_WALLET_ADDRESS=
X402_WALLET_PRIVATE_KEY=
X402_NETWORK=base-sepolia
X402_TOKEN=USDC

# Option 2: Canton Coins on Canton Network
CANTON_ENABLED=false
CANTON_FACILITATOR_URL=http://localhost:3000
CANTON_PAYEE_PARTY=
CANTON_NETWORK=canton-local
```

### Enabling Payments

The Canton MCP Server supports **dual payment options**, allowing clients to pay with either USDC or Canton Coins:

#### Option 1: USDC on Base Sepolia (EVM)

To enable USDC payments:

1. Set `X402_ENABLED=true` in `.env.canton`
2. Configure your Ethereum wallet address: `X402_WALLET_ADDRESS=0x...`
3. Optionally set private key for automated settlement: `X402_WALLET_PRIVATE_KEY=...`
4. Set network: `X402_NETWORK=base-sepolia` (or `base-mainnet` for production)

#### Option 2: Canton Coins on Canton Network

To enable Canton Coin payments:

1. Set `CANTON_ENABLED=true` in `.env.canton`
2. Start your Canton x402 facilitator service (see [canton-x402-facilitator](https://github.com/your-org/canton-x402-facilitator))
3. Configure facilitator URL: `CANTON_FACILITATOR_URL=http://localhost:3000`
4. Set your Canton payee party ID: `CANTON_PAYEE_PARTY=ServiceProvider::12207...abc`
5. Set network: `CANTON_NETWORK=canton-local` (or `canton-testnet`, `canton-mainnet`)

#### Dual Payment Configuration

You can enable **both** payment methods simultaneously. When both are enabled:

- Clients receive payment requirements for **both** USDC and Canton Coins in 402 responses
- Clients choose which payment method to use based on available funds
- The server automatically routes verification and settlement to the correct facilitator
- DCAP performance tracking correctly reports currency used (USDC or CC)

**Example dual configuration:**
```bash
# Enable both payment methods
X402_ENABLED=true
X402_WALLET_ADDRESS=0x1234...
X402_NETWORK=base-sepolia

CANTON_ENABLED=true
CANTON_FACILITATOR_URL=http://localhost:3000
CANTON_PAYEE_PARTY=ServiceProvider::12207d6f70656e2d736f757263652d6c6564676572
CANTON_NETWORK=canton-local
```

#### Pricing

Set pricing in tool definitions (default: FREE). Prices are specified in USD and automatically converted:
- **USDC**: Converted to atomic units (6 decimals) for Base Sepolia
- **Canton Coins**: Direct 1:1 USD-to-CC mapping for ad-hoc price stability

See `src/canton_mcp_server/core/pricing.py` for pricing configuration options.

### LLM Enrichment (Optional)

The Canton MCP Server supports optional LLM-based enrichment of canonical resources using Claude Haiku 3.5. This dramatically improves search relevance by generating contextual summaries and domain concepts for each resource.

#### Benefits

- **Better Search Relevance**: Enriched summaries enable better contextual matching in `recommend_canonical_resources`
- **Domain Concept Extraction**: Identifies business/technical concepts like "hedge fund", "collateral posting", "portfolio rebalancing"
- **Incremental Updates**: Only enriches new/changed files (based on Git blob hashes)
- **Persistent Cache**: Enrichments cached in `~/.canton-mcp/enrichment-cache.json` (survives restarts)

#### Setup

1. **Enable enrichment** in `.env.canton`:
```bash
ENABLE_LLM_ENRICHMENT=true
ANTHROPIC_API_KEY=sk-ant-...
```

2. **Install dependencies** (if not already installed):
```bash
uv sync
# or
pip install anthropic>=0.34.0
```

3. **Run initial enrichment** (one-time, for all 30,000+ files):
```bash
canton-mcp enrich --all
```

**Cost Estimate**: ~$5-10 for initial enrichment of 30,000 files using Claude Haiku 3.5

#### Usage

**Enrich new/changed files** (automatic on server startup, or manual):
```bash
canton-mcp enrich --new
```

**Re-enrich all files** (force refresh):
```bash
canton-mcp enrich --all
```

**Check enrichment status**:
```bash
canton-mcp enrich --status
```

**View enrichment statistics**:
```bash
canton-mcp enrich --stats
```

#### How It Works

1. **Automatic Enrichment**: When `ENABLE_LLM_ENRICHMENT=true`, the server automatically enriches new/changed files on startup (non-blocking)
2. **Incremental Updates**: Only files with new Git blob hashes are enriched (changed files)
3. **Cache Management**: Enrichments are cached by blob hash in `~/.canton-mcp/enrichment-cache.json`
4. **Fallback**: If enrichment is disabled or unavailable, the server falls back to rule-based keyword extraction

#### Configuration Options

```bash
# Enable/disable enrichment
ENABLE_LLM_ENRICHMENT=false  # Default: false

# Anthropic API key (required if enabled)
ANTHROPIC_API_KEY=sk-ant-...

# Model selection (default: claude-3-5-haiku-20241022)
LLM_ENRICHMENT_MODEL=claude-3-5-haiku-20241022

# Batch size for processing (default: 20)
LLM_ENRICHMENT_BATCH_SIZE=20

# Max tokens per response (default: 500)
LLM_ENRICHMENT_MAX_TOKENS=500
```

#### Enrichment Metadata

Each enriched resource includes:
- **Summary**: 1-2 sentence description of what the resource teaches/shows
- **Keywords**: 10-15 technical/business terms
- **Use Cases**: Categorized use cases (asset_management, financial_instruments, etc.)
- **Security Level**: basic/enhanced/enterprise
- **Complexity Level**: beginner/intermediate/advanced
- **Domain Concepts**: Business/technical concepts for better matching

## Usage

### Transport

The server uses **HTTP+SSE (Server-Sent Events)** transport on port `7284`:

- **Base URL**: `http://localhost:7284`
- **MCP Endpoint**: `http://localhost:7284/mcp`
- **Health Check**: `http://localhost:7284/health`
- **Streaming**: Supported via SSE for progress updates

### Available Tools

The server provides comprehensive tools for safe DAML development:

#### 🛡️ **Safe Code Generation Tools**

##### `generate_safe_daml_code`
Generate provably safe DAML code using DAML-compiler-validated patterns.

**Parameters:**
- `business_intent` (string): What you want to achieve
- `use_case` (string): Primary use case (e.g., "asset_management", "financial_instruments")
- `security_level` (string): "basic", "enhanced", or "enterprise"
- `constraints` (array, optional): Business/technical constraints

**Returns:** Generated DAML code with safety certificate and compilation validation

##### `certify_daml_pattern`
Certify DAML patterns with safety annotations and mathematical proof.

**Parameters:**
- `daml_code` (string): DAML template to certify
- `safety_properties` (array): Safety properties to verify
- `business_context` (string): Business context for validation

**Returns:** Safety certificate with DAML compilation validation

#### 🔍 **Enhanced Validation Tools**

##### `validate_daml_business_logic`
Validate DAML code against canonical patterns with DAML compiler safety.

**Parameters:**
- `business_intent` (string): What you want to achieve
- `daml_code` (string): DAML code to validate
- `security_requirements` (array, optional): Security requirements

**Returns:** Validation results with DAML compilation safety checks

##### `validate_daml_compilation`
Validate DAML compilation safety and authorization model compliance.

**Parameters:**
- `daml_code` (string): DAML code to validate
- `validation_level` (string): "basic", "enhanced", or "enterprise"

**Returns:** Compilation validation results with safety guarantees

##### `debug_authorization_failure`
Debug DAML authorization errors using DAML's built-in authorization model.

**Parameters:**
- `error_message` (string): The authorization error message  
- `daml_code` (string, optional): DAML code that caused the error
- `context` (string, optional): Additional context

**Returns:** Analysis and suggested fixes using DAML compiler insights

##### `suggest_authorization_pattern`
Get DAML authorization pattern recommendations from DAML-compiler-validated patterns.

**Parameters:**
- `workflow_description` (string): Workflow to implement
- `security_level` (string): "basic", "enhanced", or "enterprise" 
- `constraints` (array, optional): Business/technical constraints

**Returns:** Suggested patterns with DAML compilation validation

#### 📚 **Resource Management Tools**

##### `recommend_canonical_resources`
Get intelligent recommendations for canonical DAML resources.

**Parameters:**
- `use_case` (string): Primary use case
- `description` (string): Detailed description of what you're building (be specific for better matches!)
- `security_level` (string, optional): Required security level
- `complexity_level` (string, optional): Required complexity level
- `constraints` (array, optional): Specific constraints or requirements

**Returns:** Curated list of relevant canonical resources with safety certificates

**Note:** If LLM enrichment is enabled, recommendations use enriched summaries and domain concepts for better contextual matching.

##### `get_canonical_resource_overview`
Get overview of available canonical resources organized by use case and safety level.

**Parameters:** None

**Returns:** Structured overview of all available canonical resources

##### `get_daml_safety_certificate`
Retrieve safety certificates for DAML patterns and templates.

**Parameters:**
- `pattern_id` (string): Pattern identifier
- `certificate_type` (string): Type of certificate requested

**Returns:** Safety certificate with mathematical proof and DAML compilation validation

### Development

```bash
# Install development dependencies
uv sync --dev

# Run the server in development mode
uv run python -m canton_mcp_server.server

# Test with MCP Inspector
npx @modelcontextprotocol/inspector http://localhost:7284/mcp
```

## Testing MCP Tools

The Canton MCP Server provides multiple ways to test tool calls:

### 1. Quick Test Script

Run the provided test script to verify all tools:

```bash
./test-mcp-tools.sh
```

This tests:
- Listing available tools
- Getting canonical resource overview
- Recommending resources for asset transfer
- Validating DAML code

### 2. MCP Inspector (Interactive UI)

The official MCP Inspector provides a web-based interface to test tools:

```bash
npx @modelcontextprotocol/inspector http://localhost:7284/mcp
```

Open your browser to the displayed URL to interact with all tools visually.

### 3. curl Commands

Test individual tools with curl:

```bash
# List all tools
curl -X POST http://localhost:7284/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# Validate DAML code
curl -X POST http://localhost:7284/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "validate_daml_business_logic",
      "arguments": {
        "businessIntent": "Create a simple IOU",
        "damlCode": "template IOU\n  with\n    issuer: Party\n    owner: Party\n  where\n    signatory issuer"
      }
    }
  }'

# Debug authorization failure
curl -X POST http://localhost:7284/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "debug_authorization_failure",
      "arguments": {
        "errorMessage": "Authorization failed: missing signatory"
      }
    }
  }'

# Suggest authorization pattern
curl -X POST http://localhost:7284/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "suggest_authorization_pattern",
      "arguments": {
        "workflowDescription": "Multi-party approval for asset transfer",
        "securityLevel": "enhanced"
      }
    }
  }'
```

### 4. Python Client

Test with Python requests:

```python
import requests

response = requests.post(
    "http://localhost:7284/mcp",
    headers={
        "Content-Type": "application/json",
        "Accept": "application/json"
    },
    json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "validate_daml_business_logic",
            "arguments": {
                "businessIntent": "Create a simple IOU",
                "damlCode": """
                    template IOU
                      with
                        issuer: Party
                        owner: Party
                      where
                        signatory issuer
                """
            }
        }
    }
)

print(response.json())
```

### 5. Claude Desktop Integration

To use with Claude Desktop, add to your configuration file:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "canton": {
      "command": "docker",
      "args": [
        "exec",
        "canton-mcp-server",
        "uv",
        "run",
        "canton-mcp-server",
        "serve"
      ]
    }
  }
}
```

Or for non-Docker installations:

```json
{
  "mcpServers": {
    "canton": {
      "command": "uv",
      "args": ["run", "canton-mcp-server", "serve"],
      "cwd": "/path/to/canton-mcp-server"
    }
  }
}
```

### Available Tools

All tools are FREE by default:

1. **validate_daml_business_logic** - Validate DAML code against canonical patterns
2. **debug_authorization_failure** - Debug authorization errors with detailed analysis
3. **suggest_authorization_pattern** - Get pattern recommendations for workflows
4. **recommend_canonical_resources** - Get intelligent resource recommendations
5. **get_canonical_resource_overview** - Overview of available canonical resources

## Test DAML Contracts

The `test-daml/` directory contains comprehensive DAML contract examples for testing:

- **BasicIou.daml** - Simple debt tracking with transfer and settlement
- **MultiPartyContract.daml** - Complex multi-party approval workflows
- **SupplyChain.daml** - Product tracking, shipping, and quality control
- **AssetManagement.daml** - Asset transfer and management patterns
- **TradingExample.daml** - Financial trading and order matching
- **ProblematicExamples.daml** - Authorization anti-patterns for testing validators

Use these contracts to test the MCP tools:

```bash
# Test validation with BasicIou
# Use MCP client to call validate_daml_business_logic with BasicIou.daml content

# Debug authorization issues with ProblematicExamples
# Use MCP client to call debug_authorization_failure with error scenarios

# Get pattern suggestions for SupplyChain workflows
# Use MCP client to call suggest_authorization_pattern with supply chain requirements
```

## Resource Schemas

The Canton MCP Server uses JSON schemas to validate resource files from the canonical DAML repositories. These schemas define the structure for patterns, anti-patterns, rules, and documentation extracted from the official repositories:

### Pattern Schema (`schemas/pattern.schema.json`)
- **Required fields**: `name`, `version`, `description`, `tags`, `author`, `created_at`, `pattern_type`, `daml_template`, `authorization_requirements`, `when_to_use`, `when_not_to_use`, `security_considerations`, `test_cases`
- **Version format**: Semantic versioning (e.g., "1.0.0")
- **Date format**: ISO 8601 timestamps (e.g., "2024-01-15T10:00:00Z")

### Anti-Pattern Schema (`schemas/anti-pattern.schema.json`)
- **Required fields**: `name`, `version`, `description`, `tags`, `author`, `created_at`, `anti_pattern_type`, `severity`, `problematic_code`, `why_problematic`, `detection_pattern`, `correct_alternative`, `impact`, `remediation`
- **Severity levels**: `low`, `medium`, `high`, `critical`

### Rule Schema (`schemas/rule.schema.json`)
- **Required fields**: `name`, `version`, `description`, `tags`, `author`, `created_at`, `rule_type`, `severity`, `enforcement`, `rules`
- **Enforcement levels**: `advisory`, `recommended`, `mandatory`

### Documentation Schema (`schemas/doc.schema.json`)
- **Required fields**: `name`, `version`, `description`, `tags`, `author`, `created_at`, `doc_type`, `audience`, `difficulty`, `overview`, `sections`
- **Document types**: `guide`, `tutorial`, `reference`, `best-practices`, `troubleshooting`, `api-docs`
- **Audience levels**: `beginners`, `developers`, `architects`, `operators`, `all`

### Schema Validation

Resources are automatically validated against their schemas when loaded. Invalid resources are rejected with detailed error messages. The schema validation ensures:

- **Data integrity**: All required fields are present
- **Type safety**: Fields have correct data types
- **Format compliance**: Dates, versions, and other fields follow proper formats
- **Content quality**: Minimum length requirements for descriptions and other text fields

### Example Valid Pattern Resource

```yaml
name: simple-transfer
version: "1.0.0"
description: Basic pattern for transferring ownership of an asset
tags: [transfer, authorization, basic]
author: Canton Team
created_at: "2024-01-15T10:00:00Z"
pattern_type: asset_transfer
daml_template: |
  template Transfer
    with
      owner: Party
      asset: Asset
    where
      signatory owner
      
      choice TransferOwnership : ContractId Transfer
        with
          newOwner: Party
        controller owner
        do
          create this with owner = newOwner

authorization_requirements:
  - id: REQ-AUTH-001
    rule: "Controller must be signatory or have explicit authorization"
    satisfied: true
    explanation: "owner is signatory and controller"

when_to_use:
  - "Simple ownership transfers"
  - "Unilateral actions by asset owner"

when_not_to_use:
  - "Multi-party approval needed"
  - "Complex state transitions"

security_considerations:
  - "Ensure owner is signatory"
  - "Validate asset state before transfer"

test_cases:
  - description: "Valid transfer"
    passes: true
    code: "alice transfers to bob"
```

## MCP Integration

This server follows the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) specification using HTTP+SSE transport.

### MCP Inspector

Test the server interactively:

```bash
npx @modelcontextprotocol/inspector http://localhost:7284/mcp
```

### MCP Client Configuration

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "canton": {
      "command": "uv",
      "args": ["run", "canton-mcp-server", "serve"],
      "cwd": "/path/to/canton-mcp-server",
      "env": {
        "DCAP_ENABLED": "true",
        "DCAP_MULTICAST_IP": "159.89.110.236",
        "DCAP_PORT": "10191"
      }
    }
  }
}
```

## DCAP Performance Tracking

The server automatically broadcasts performance metrics using DCAP v2 protocol:

- **Protocol Version**: 2
- **Transport**: UDP (direct or multicast)
- **Default Port**: 10191
- **Metrics Tracked**: Tool name, execution time, success/failure, anonymized parameters

Configure DCAP in `.env.canton` or via environment variables. Performance data is sent to dashboards/monitoring systems without impacting tool execution.

**Note**: Set `DCAP_MULTICAST_IP` to either:
- A direct UDP relay address (e.g., `159.89.110.236`)
- A multicast address (e.g., `239.255.0.1`)

The server automatically detects multicast addresses (239.x.x.x) and configures the socket appropriately.

## Adding New Tools

The Canton MCP Server uses a powerful framework that makes adding new tools straightforward and type-safe. Follow these guidelines to implement new tools that integrate seamlessly with DCAP tracking, x402 payments, and MCP protocol compliance.

### Tool Implementation Guide

#### 1. Create Your Tool File

Create a new file in `src/canton_mcp_server/tools/` (e.g., `my_new_tool.py`):

```python
"""
My New Tool

Brief description of what this tool does.
"""

from typing import List, Optional
from pydantic import Field

from ..core import Tool, ToolContext, register_tool
from ..core.pricing import PricingType, ToolPricing
from ..core.types.models import MCPModel


# IMPORTANT: Use MCPModel, not BaseModel!
# MCPModel automatically handles camelCase/snake_case conversion for MCP protocol
class MyToolParams(MCPModel):
    """Parameters for my tool"""
    
    user_input: str = Field(description="User's input data")
    optional_config: Optional[str] = Field(
        default=None, 
        description="Optional configuration"
    )


class MyToolResult(MCPModel):
    """Result from my tool"""
    
    success: bool = Field(description="Whether operation succeeded")
    output_data: str = Field(description="The result data")
    details: List[str] = Field(description="Additional details")


@register_tool  # This decorator auto-registers the tool
class MyNewTool(Tool[MyToolParams, MyToolResult]):
    """Tool for doing something awesome"""
    
    # Tool metadata (required)
    name = "my_new_tool"
    description = "Does something awesome with user input"
    params_model = MyToolParams
    result_model = MyToolResult
    
    # Pricing configuration (optional, defaults to FREE)
    pricing = ToolPricing(
        type=PricingType.FREE  # or FIXED, DYNAMIC
        # base_price_usd=0.01  # For FIXED pricing
    )
    
    async def execute(self, ctx: ToolContext[MyToolParams, MyToolResult]):
        """Execute the tool logic"""
        
        # Access validated, typed parameters
        user_input = ctx.params.user_input
        config = ctx.params.optional_config
        
        # Send progress updates (optional)
        yield ctx.progress(0, 100, "Starting processing...")
        
        # Send log messages (optional)
        yield ctx.log("info", f"Processing: {user_input}")
        
        # Do your work here
        output = f"Processed: {user_input}"
        
        # Update progress
        yield ctx.progress(100, 100, "Complete!")
        
        # Create typed result
        result = MyToolResult(
            success=True,
            output_data=output,
            details=["Step 1 completed", "Step 2 completed"]
        )
        
        # Return structured result
        # DCAP tracking happens automatically!
        # x402 payment settlement happens automatically!
        yield ctx.structured(result)
```

#### 2. Key Requirements

**✅ DO:**
- Inherit from `MCPModel` for all parameter and result classes
- Use type hints and Pydantic `Field()` descriptions
- Use the `@register_tool` decorator
- Define `name`, `description`, `params_model`, `result_model`
- Use `ctx.params` to access validated parameters
- Use `ctx.structured(result)` to return typed results
- Use `yield` for all responses (progress, logs, results)

**❌ DON'T:**
- Use plain Pydantic `BaseModel` (breaks MCP protocol camelCase)
- Forget the `@register_tool` decorator
- Return results directly (use `yield ctx.structured(...)`)
- Use blocking I/O (use async/await)
- Access raw request data (use `ctx.params` instead)

#### 3. Parameter and Result Models

The `MCPModel` base class provides automatic camelCase conversion:

```python
from ..core.types.models import MCPModel

class MyParams(MCPModel):
    user_name: str  # ← Python: snake_case
    age_in_years: int
    
# JSON schema will have: userName, ageInYears (camelCase)
# Python access: params.user_name (snake_case)
# MCP protocol: {"userName": "...", "ageInYears": 25} (camelCase)
```

This ensures:
- Your Python code uses pythonic snake_case
- MCP protocol uses standard camelCase
- Schemas and responses match automatically

#### 4. Context Methods

The `ToolContext` provides helpful methods:

```python
# Access parameters
ctx.params.field_name

# Progress updates (optional)
yield ctx.progress(current, total, "Status message")

# Log messages (optional)
yield ctx.log("info", "Processing...")
yield ctx.log("warning", "Non-critical issue")
yield ctx.log("error", "Something failed")

# Return structured result
yield ctx.structured(result_object)

# Return with summary text
yield ctx.structured(result_object, summary_text="Operation completed successfully")

# Check payment status
if ctx.payment.verified:
    # Payment was verified
    amount = ctx.payment.amount_usd
```

#### 5. Pricing Configuration

Tools can be FREE, FIXED price, or DYNAMIC:

```python
# Free tool (default)
pricing = ToolPricing(type=PricingType.FREE)

# Fixed price per execution
pricing = ToolPricing(
    type=PricingType.FIXED,
    base_price_usd=0.01  # 1 cent per execution
)

# Dynamic pricing (calculated at runtime)
pricing = ToolPricing(
    type=PricingType.DYNAMIC,
    min_price_usd=0.001,
    max_price_usd=1.0
)
```

#### 6. Automatic Features

When you follow this pattern, you get automatically:

- ✅ **DCAP Performance Tracking** - All executions are tracked
- ✅ **x402 Payment Handling** - Payment verification and settlement
- ✅ **MCP Protocol Compliance** - Proper schema generation and responses
- ✅ **Type Safety** - Full IDE autocomplete and type checking
- ✅ **Progress Streaming** - Real-time updates via SSE
- ✅ **Error Handling** - Standardized error responses
- ✅ **Request Management** - Cancellation support and lifecycle tracking

#### 7. Testing Your Tool

```python
# The tool is automatically discovered and registered!
# Just restart the server:
uv run canton-mcp-server serve

# Test with MCP Inspector:
npx @modelcontextprotocol/inspector http://localhost:7284/mcp

# Or test with curl:
curl -X POST http://localhost:7284/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "my_new_tool",
      "arguments": {
        "userInput": "test data"
      }
    }
  }'
```

#### 8. Advanced: Error Handling

```python
async def execute(self, ctx: ToolContext[MyToolParams, MyToolResult]):
    try:
        # Your logic here
        result = MyToolResult(...)
        yield ctx.structured(result)
        
    except ValueError as e:
        # Return error response
        yield ctx.error(f"Invalid input: {e}")
        
    except Exception as e:
        # Log and return error
        yield ctx.log("error", f"Unexpected error: {e}")
        yield ctx.error("Internal error occurred")
```

#### 9. Advanced: Cancellation Support

```python
async def execute(self, ctx: ToolContext[MyToolParams, MyToolResult]):
    for i in range(100):
        # Check if cancelled
        if ctx.request.is_cancelled():
            yield ctx.log("warning", "Operation cancelled by user")
            return
            
        # Do work
        await process_chunk(i)
        yield ctx.progress(i, 100, f"Processing chunk {i}")
```

### Example: Complete Tool

See `src/canton_mcp_server/tools/validate_daml_business_logic.py` for a complete, production-ready example that demonstrates all these patterns.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Architecture

### **DAML-Safe by Construction Platform**

The Canton MCP Server implements a comprehensive safety-first architecture:

#### **Safety Gates Architecture**
- **Gate 1: DAML Compiler Safety** - All patterns must compile successfully
- **Gate 2: Safety Annotations** - Patterns must have safety metadata
- **Gate 3: Formal Verification** - Safety properties must be verified
- **Gate 4: Production Readiness** - Must be production-tested

#### **Backend Engines**
- **DAML Compiler Integration**: Validates all patterns through DAML compilation
- **Safety Annotation System**: Adds safety metadata to DAML templates
- **Safe Code Generation Engine**: Generates provably safe DAML code
- **Authorization Safety Engine**: Leverages DAML's built-in authorization model
- **Business Logic Safety Engine**: Uses DAML's consistency guarantees

#### **MCP Tool Layer**
- **Safe Code Generation Tools**: Generate and certify DAML code
- **Enhanced Validation Tools**: Validate with DAML compiler safety
- **Resource Management Tools**: Access canonical resources with safety certificates

#### **Production Infrastructure**
- **Tool Base Class**: Type-safe tool development with Pydantic models
- **Pricing System**: Flexible pricing (FREE, FIXED, DYNAMIC) with x402 integration
- **DCAP Integration**: Automatic performance tracking for all tool executions
- **Payment Handler**: x402 payment verification and settlement
- **Request Manager**: Lifecycle management with cancellation support
- **FastAPI Server**: HTTP+SSE transport with streaming capabilities

### **Safety Principles**

1. **DAML-Safe by Construction**: Leverage DAML compiler's existing safety guarantees
2. **Compiler-First Safety**: All validation goes through DAML compilation
3. **Safety Annotations**: Add safety metadata to DAML templates
4. **Complete Audit Trails**: Every DAML compilation must be logged

## Related Projects

- [Model Context Protocol](https://modelcontextprotocol.io/) - The MCP specification
- [x402]([https://github.com/x402-protocol](https://github.com/ChainSafe/canton-mcp-server/issues/4)) - Payment protocol for AI services
- [Canton](https://www.digitalasset.com/developers) - The Canton blockchain platform
- [DAML](https://docs.daml.com/) - The DAML smart contract language
- [DCAP]([https://dcap.dev](https://github.com/boorich/dcap)) - Performance tracking protocol (if available)
