# Canton MCP Server

A production-ready MCP server for Canton blockchain development with DAML validation, authorization patterns, DCAP performance tracking, and x402 payment infrastructure.

## Features

- **DAML Code Validation**: Validate DAML code against canonical authorization patterns and business requirements
- **Authorization Debugging**: Debug DAML authorization errors with detailed analysis and suggested fixes
- **Pattern Suggestions**: Get recommendations for DAML authorization patterns based on workflow requirements
- **DCAP Performance Tracking**: Real-time performance monitoring via DCAP v2 protocol
- **x402 Payment Infrastructure**: Built-in payment support (disabled by default, ready for monetization)
- **HTTP+SSE Transport**: Streaming support with Server-Sent Events
- **Type-Safe Tools**: Fully typed parameters and results using Pydantic models

## Installation

### Prerequisites

- Python 3.10 or higher
- uv (recommended) or pip

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
X402_ENABLED=false
X402_WALLET_ADDRESS=
X402_WALLET_PRIVATE_KEY=
X402_NETWORK=base-sepolia
X402_TOKEN=USDC
```

### Enabling Payments

To enable x402 payments for tool usage:

1. Set `X402_ENABLED=true` in `.env.canton`
2. Configure your wallet address and private key
3. Set pricing in tool definitions (default: FREE)

## Usage

### Transport

The server uses **HTTP+SSE (Server-Sent Events)** transport on port `7284`:

- **Base URL**: `http://localhost:7284`
- **MCP Endpoint**: `http://localhost:7284/mcp`
- **Health Check**: `http://localhost:7284/health`
- **Streaming**: Supported via SSE for progress updates

### Available Tools

The server provides three tools for Canton DAML development:

#### 1. `validate_daml_business_logic`
Validate DAML code against canonical authorization patterns.

**Parameters:**
- `business_intent` (string): What you want to achieve
- `daml_code` (string): DAML code to validate
- `security_requirements` (array, optional): Security requirements

**Returns:** Validation results with issues and suggestions

#### 2. `debug_authorization_failure`
Debug DAML authorization errors with detailed analysis.

**Parameters:**
- `error_message` (string): The authorization error message  
- `daml_code` (string, optional): DAML code that caused the error
- `context` (string, optional): Additional context

**Returns:** Analysis and suggested fixes

#### 3. `suggest_authorization_pattern`
Get DAML authorization pattern recommendations.

**Parameters:**
- `workflow_description` (string): Workflow to implement
- `security_level` (string): "basic", "enhanced", or "enterprise" 
- `constraints` (array, optional): Business/technical constraints

**Returns:** Suggested patterns and implementation notes

### Development

```bash
# Install development dependencies
uv sync --dev

# Run the server in development mode
uv run python -m canton_mcp_server.server

# Test with MCP Inspector
npx @modelcontextprotocol/inspector http://localhost:7284/mcp
```

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

The Canton MCP Server uses a production-ready framework with:

- **Tool Base Class**: Type-safe tool development with Pydantic models
- **Pricing System**: Flexible pricing (FREE, FIXED, DYNAMIC) with x402 integration
- **DCAP Integration**: Automatic performance tracking for all tool executions
- **Payment Handler**: x402 payment verification and settlement
- **Request Manager**: Lifecycle management with cancellation support
- **FastAPI Server**: HTTP+SSE transport with streaming capabilities

## Related Projects

- [Model Context Protocol](https://modelcontextprotocol.io/) - The MCP specification
- [x402](https://github.com/x402-protocol) - Payment protocol for AI services
- [Canton](https://www.digitalasset.com/developers) - The Canton blockchain platform
- [DAML](https://docs.daml.com/) - The DAML smart contract language
- [DCAP](https://dcap.dev) - Performance tracking protocol (if available)
