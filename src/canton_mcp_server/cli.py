"""
Canton MCP Server CLI entry point.
"""

import uvicorn

from .env import get_env
from .server import app


def main():
    """Main CLI entry point - starts the Canton MCP Server"""
    mcp_server_url = get_env("MCP_SERVER_URL", "http://localhost:7284")
    print("\n" + "─" * 60)
    print(f"  Canton MCP Server v0.1 | {mcp_server_url}/mcp")
    print("  DAML Validation & Authorization Patterns")
    print("─" * 60 + "\n")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=7284,
        log_level="info",
        timeout_keep_alive=30 * 60,
        timeout_graceful_shutdown=30,
    )


if __name__ == "__main__":
    main()
