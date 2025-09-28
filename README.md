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

# Run the server
uv run canton-mcp-server serve
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

# Run tests
uv run pytest

# Run the server in development mode
uv run python -m canton_mcp_server.server
```

## MCP Integration

This server follows the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) specification and can be integrated with various MCP clients including:

- Claude Desktop
- Other MCP-compatible AI assistants
- Custom MCP clients

### Configuration Example

Add to your MCP client configuration:

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
