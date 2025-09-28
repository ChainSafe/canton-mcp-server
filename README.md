# Canton MCP Server

A [FastMCP](https://gofastmcp.com/) server for Canton blockchain development, providing tools for DAML validation, authorization patterns, and Canton network management.

## Features

- **DAML Code Validation**: Validate DAML code against canonical authorization patterns and business requirements
- **Authorization Debugging**: Debug DAML authorization errors with detailed analysis and suggested fixes
- **Pattern Suggestions**: Get recommendations for DAML authorization patterns based on workflow requirements
- **Development Tools**: Various utilities for Canton blockchain development

## Installation

### Using uv (recommended)

```bash
# Clone and install
git clone <repository-url>
cd canton-mcp-server
uv sync

# Run the server (multiple options)
uv run canton-mcp-server serve        # Direct command
./start-server.sh                     # Robust startup script (recommended for MCP clients)
```

### Using pip

```bash
# Install from source
pip install -e .

# Run the server
canton-mcp-server serve
```

## Usage

### As an MCP Server

The server provides several tools that can be used by MCP clients:

- `validate_daml_business_logic`: Validate DAML code against business requirements
- `debug_authorization_failure`: Debug authorization errors in DAML code
- `suggest_authorization_pattern`: Get pattern suggestions for workflows
- `test_tool`: Simple test tool for connectivity

### Development

```bash
# Install development dependencies
uv sync --dev

# Test the server tools manually
uv run python dev.py

# Run the server in development mode
uv run python -m canton_mcp_server.server

# Test with MCP Inspector
npx @modelcontextprotocol/inspector uv run canton-mcp-server serve
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

This server follows the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) specification and can be integrated with various MCP clients including:

- Claude Desktop
- Other MCP-compatible AI assistants
- Custom MCP clients

### Configuration Example

Add to your MCP client configuration:

#### Recommended (Robust Startup)
```json
{
  "mcpServers": {
    "canton-mcp-server": {
      "command": "/path/to/canton-mcp-server/start-server.sh",
      "args": []
    }
  }
}
```

#### Alternative (Direct Command)
```json
{
  "mcpServers": {
    "canton-mcp-server": {
      "command": "uv",
      "args": ["run", "canton-mcp-server", "serve"],
      "cwd": "/path/to/canton-mcp-server"
    }
  }
}
```

The `start-server.sh` script is recommended as it handles directory changes and environment setup automatically, making it more reliable across different MCP client implementations.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Related Projects

- [FastMCP](https://gofastmcp.com/) - The FastMCP framework this server is built on
- [Canton](https://www.digitalasset.com/developers) - The Canton blockchain platform
- [DAML](https://docs.daml.com/) - The DAML smart contract language
