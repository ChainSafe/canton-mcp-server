#!/usr/bin/env python3
"""
MCP Test Container - Irregular Tool Caller

Makes random MCP tool calls at irregular intervals to test server
availability and tool functionality.
"""

import json
import os
import random
import sys
import time
from datetime import datetime

import requests


# MCP Server configuration
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://canton-mcp-server:7284/mcp")
MIN_INTERVAL = int(os.getenv("MIN_INTERVAL", "30"))
MAX_INTERVAL = int(os.getenv("MAX_INTERVAL", "300"))

# Tool definitions with sample arguments
TOOLS = [
    {
        "name": "validate_daml_business_logic",
        "arguments": {
            "businessIntent": "Create a simple asset transfer",
            "damlCode": """
template Asset
  with
    owner: Party
    name: Text
  where
    signatory owner
    
    choice Transfer: ContractId Asset
      with newOwner: Party
      controller owner
      do create this with owner = newOwner
            """,
        },
    },
    {
        "name": "debug_authorization_failure",
        "arguments": {
            "errorMessage": "Authorization failed: Party 'Bob' is missing as a signatory",
            "context": "Testing multi-party contract",
        },
    },
    {
        "name": "suggest_authorization_pattern",
        "arguments": {
            "workflowDescription": "Multi-party approval workflow for financial transactions",
            "securityLevel": "enhanced",
        },
    },
    {
        "name": "get_canonical_resource_overview",
        "arguments": {},
    },
    {
        "name": "recommend_canonical_resources",
        "arguments": {
            "useCase": "asset_transfer",
            "description": "Building a digital asset management system with transfer capabilities",
            "securityLevel": "basic",
        },
    },
]


def log(message: str, level: str = "INFO"):
    """Log message with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", flush=True)


def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """Make MCP tool call"""
    request_id = random.randint(1, 999999)
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        response = requests.post(
            MCP_SERVER_URL, json=payload, headers=headers, timeout=30
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        log(f"Request failed: {e}", "ERROR")
        return {"error": str(e)}


def run_test_loop():
    """Main test loop - randomly call tools at irregular intervals"""
    log("🚀 Starting MCP Test Container")
    log(f"   Server: {MCP_SERVER_URL}")
    log(f"   Interval: {MIN_INTERVAL}-{MAX_INTERVAL} seconds")
    log(f"   Tools: {len(TOOLS)} available")
    log("")

    iteration = 0

    while True:
        try:
            iteration += 1

            # Select random tool
            tool = random.choice(TOOLS)
            tool_name = tool["name"]
            arguments = tool["arguments"]

            # Make the call
            log(f"[#{iteration}] Calling tool: {tool_name}")
            result = call_mcp_tool(tool_name, arguments)

            # Check result
            if "error" in result and "jsonrpc" not in result:
                log(f"   ❌ Call failed: {result['error']}", "ERROR")
            elif "error" in result:
                log(f"   ❌ MCP error: {result['error']}", "ERROR")
            elif "result" in result:
                is_error = result["result"].get("isError", False)
                if is_error:
                    log(f"   ⚠️  Tool returned error", "WARN")
                else:
                    log(f"   ✅ Tool executed successfully")
            else:
                log(f"   ⚠️  Unexpected response format", "WARN")

            # Random sleep interval
            sleep_time = random.randint(MIN_INTERVAL, MAX_INTERVAL)
            log(f"   💤 Sleeping for {sleep_time} seconds...")
            log("")
            time.sleep(sleep_time)

        except KeyboardInterrupt:
            log("⏹️  Shutting down gracefully...")
            sys.exit(0)
        except Exception as e:
            log(f"Unexpected error: {e}", "ERROR")
            log("   Waiting 60 seconds before retry...")
            time.sleep(60)


if __name__ == "__main__":
    run_test_loop()

