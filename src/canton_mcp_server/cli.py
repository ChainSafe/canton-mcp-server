"""
Canton MCP Server CLI entry point.
"""

import sys
from .server import app

def main():
    """Main CLI entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        # Run as MCP server
        app.run()
    else:
        # Default behavior
        print("Canton MCP Server")
        print("Usage: canton-mcp-server serve")
        print("  serve    Start the MCP server")

if __name__ == "__main__":
    main()
