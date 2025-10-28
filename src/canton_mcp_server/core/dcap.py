"""
DCAP (Distributed Claude Agent Protocol) Broadcasting

Sends performance updates to notify dashboards of tool execution metrics.
Uses UDP multicast for broadcasting.
Fails silently to never break tool execution.
"""

import json
import logging
import socket
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# DCAP Configuration (loaded from environment)
TRANSPORT_TYPE = "streamable-http"
UDP_MAX_SIZE = 1472  # Maximum safe UDP packet size


def _get_dcap_config():
    """Get DCAP configuration from environment variables"""
    from ..env import get_env, get_env_int

    multicast_ip = get_env("DCAP_MULTICAST_IP", "")

    # If no multicast IP configured, return None
    if not multicast_ip:
        return None

    return {
        "multicast_ip": multicast_ip,
        "port": get_env_int("DCAP_PORT", 10191),
        "server_id": get_env("DCAP_SERVER_ID", "canton-mcp"),
        "server_name": get_env("DCAP_SERVER_NAME", "Canton MCP Server"),
    }


def anonymize_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Anonymize sensitive data in tool arguments.

    Truncates strings, summarizes collections to prevent data leakage.

    Args:
        args: Original tool arguments

    Returns:
        Anonymized version of arguments
    """
    anonymized = {}

    for key, value in args.items():
        if isinstance(value, str):
            # Truncate long strings
            anonymized[key] = value[:20] + "..." if len(value) > 20 else value
        elif isinstance(value, (int, float, bool)):
            # Keep numeric/boolean values as-is
            anonymized[key] = value
        elif isinstance(value, list):
            # Show list size only
            anonymized[key] = f"[{len(value)} items]"
        elif isinstance(value, dict):
            # Show dict size only
            anonymized[key] = f"{{{len(value)} fields}}"
        elif value is None:
            anonymized[key] = None
        else:
            # Convert unknown types to string
            anonymized[key] = str(value)[:20]

    return anonymized


def send_perf_update(
    tool_name: str,
    exec_ms: int,
    success: bool,
    args: Optional[Dict[str, Any]] = None,
    cost_paid: Optional[float] = None,
    currency: str = "USDC",
    caller: Optional[str] = None,
    payer: Optional[str] = None,
) -> None:
    """
    Send DCAP v2.4 perf_update message via direct UDP.

    Broadcasts tool performance metrics to real-time dashboards. Fails silently to
    never interrupt tool execution.

    Args:
        tool_name: Name of the tool that was executed
        exec_ms: Execution time in milliseconds
        success: Whether the tool execution succeeded
        args: Tool arguments (will be anonymized)
        cost_paid: Cost of the tool execution (optional)
        currency: Currency of the cost (default: "USDC")
        caller: Caller identifier (agent/user name)
        payer: Payer wallet address (from x402 settlement)
    """
    try:
        # Get configuration from environment
        config = _get_dcap_config()

        # Skip if no multicast IP configured
        if not config:
            logger.debug("⚠️ DCAP not enabled - no IP configured")
            return

        # Get fallback defaults for caller and payer from environment
        # These are only used when real values cannot be determined from request
        from ..env import get_env
        default_caller = get_env("DCAP_DEFAULT_CALLER", "unknown-client")
        default_payer = get_env("DCAP_DEFAULT_PAYER", "0x0000000000000000000000000000000000000000")

        # Build DCAP v2.4 message (spec-compliant format)
        # caller: Extracted from X-Caller-ID header or User-Agent
        # payer: Extracted from x402 payment header or settlement response
        message = {
            "v": 2,  # Protocol version 2.4
            "ts": int(time.time()),  # Unix timestamp
            "t": "perf_update",  # Message type
            "sid": config["server_id"],  # Server identifier
            "tool": tool_name,
            "exec_ms": exec_ms,
            "success": success,
            "ctx": {
                "caller": caller or default_caller,  # Agent/user identifier (from header)
                "payer": payer or default_payer,  # Wallet address (from x402 payment)
                "args": anonymize_args(args) if args else {},
            },
        }

        # Add cost information if provided
        if cost_paid is not None:
            message["cost_paid"] = int(cost_paid)  # Atomic units (USDC has 6 decimals)
            message["currency"] = currency

        # Log the message
        logger.debug(f"🪱 DCAP message: {message}")

        # Send via UDP multicast
        _send_udp(config["multicast_ip"], config["port"], message, tool_name)

    except Exception as e:
        # Silent failure - don't break tool execution
        logger.warning(f"⚠️ DCAP broadcast failed for {tool_name}: {e}")


def _send_udp(multicast_ip: str, port: int, message: dict, tool_name: str) -> None:
    """Send DCAP message via UDP (multicast or direct)"""
    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

    # Set multicast TTL only if using multicast address (239.x.x.x)
    if multicast_ip.startswith("239."):
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

    # Convert to JSON
    json_message = json.dumps(message)

    # Ensure message fits in UDP packet (max 1472 bytes)
    message_bytes = json_message.encode("utf-8")
    if len(message_bytes) > UDP_MAX_SIZE:
        # Remove args if too large
        if "ctx" in message and "args" in message["ctx"]:
            message["ctx"]["args"] = {}
            json_message = json.dumps(message)
            message_bytes = json_message.encode("utf-8")

    # Send via UDP (multicast or direct)
    sock.sendto(message_bytes, (multicast_ip, port))
    sock.close()

    logger.debug(f"🪱 DCAP thump sent (UDP): {tool_name} -> {multicast_ip}:{port}")


def send_semantic_discover(
    tool_name: str,
    description: str,
    server_url: str,
    payment_enabled: bool = False,
) -> None:
    """
    Send DCAP v2.5 semantic_discover message via UDP.

    Broadcasts tool capability advertisement with connector information.
    Semantic fields (when, good_at, bad_at) are left empty and will be
    filled by Semanticore based on observed performance patterns.

    Args:
        tool_name: Name of the tool being advertised
        description: Human-readable description of what the tool does
        server_url: Full MCP endpoint URL (e.g., "https://canton.example.com/mcp")
        payment_enabled: Whether x402 payment is required (price determined at call time via x402)
    """
    try:
        # Get configuration from environment
        config = _get_dcap_config()

        # Skip if no multicast IP configured
        if not config:
            logger.debug("⚠️ DCAP not enabled - no IP configured")
            return

        # Build connector object (DCAP v2.5)
        connector = {
            "transport": "sse",  # This server uses Server-Sent Events (HTTP-based streaming)
            "endpoint": server_url,
            "protocol": {
                "type": "mcp",
                "version": "2024-11-05",
                "methods": ["tools/list", "tools/call"]
            }
        }

        # Add auth details if payment is enabled
        if payment_enabled:
            connector["auth"] = {
                "type": "x402",
                "required": True,
                "details": {
                    "network": "base-sepolia",
                    "asset": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",  # USDC on Base Sepolia
                    "currency": "USDC"
                    # No price field - actual price determined via x402 negotiation at call time
                }
            }
        else:
            connector["auth"] = {
                "type": "none",
                "required": False
            }

        # Build DCAP v2.5 semantic_discover message
        message = {
            "v": 2,  # Protocol version 2.5
            "ts": int(time.time()),  # Unix timestamp
            "t": "semantic_discover",  # Message type
            "sid": config["server_id"],  # Server identifier
            "tool": tool_name,
            "does": description,
            # Semantic fields are empty - filled later by Semanticore based on observations
            "when": [],
            "good_at": [],
            "bad_at": [],
            "connector": connector
        }

        # Log the message (truncate for readability)
        logger.debug(f"🔍 DCAP semantic_discover: {tool_name}")

        # Send via UDP (allows up to ~65KB with IP fragmentation)
        _send_udp_large(config["multicast_ip"], config["port"], message, tool_name)

    except Exception as e:
        # Silent failure - don't break server startup
        logger.warning(f"⚠️ DCAP semantic_discover failed for {tool_name}: {e}")


def broadcast_all_tools(server_url: str, payment_handler=None) -> None:
    """
    Broadcast semantic_discover messages for all registered tools.

    Called on server startup and periodically to advertise capabilities
    to the DCAP network.

    Args:
        server_url: Full MCP endpoint URL
        payment_handler: Optional payment handler to check pricing
    """
    try:
        from .registry import get_registry

        config = _get_dcap_config()
        if not config:
            logger.debug("⚠️ DCAP not enabled - skipping tool broadcast")
            return

        registry = get_registry()
        tools = registry.list_tools()

        logger.info(f"📡 Broadcasting {len(tools)} tools to DCAP network...")

        for tool in tools:
            # Determine if payment is required
            payment_enabled = False

            if payment_handler and payment_handler.enabled:
                # Check if this tool requires payment
                if tool.pricing and tool.pricing.type.value != "free":
                    payment_enabled = True

            # Send discovery message
            send_semantic_discover(
                tool_name=tool.name,
                description=tool.description,
                server_url=server_url,
                payment_enabled=payment_enabled,
            )

        logger.info(f"✅ Broadcast complete: {len(tools)} tools advertised")

    except Exception as e:
        logger.warning(f"⚠️ Failed to broadcast tools: {e}")


def _send_udp_large(multicast_ip: str, port: int, message: dict, tool_name: str) -> None:
    """
    Send large DCAP message via UDP (allows IP fragmentation up to ~65KB).

    For semantic_discover messages which may exceed 1472 bytes due to
    connector object details. UDP/IP layer handles fragmentation automatically.

    Args:
        multicast_ip: Target IP address
        port: Target port
        message: DCAP message dict
        tool_name: Tool name (for logging)
    """
    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

    # Set multicast TTL only if using multicast address (239.x.x.x)
    if multicast_ip.startswith("239."):
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

    # Convert to JSON
    json_message = json.dumps(message)
    message_bytes = json_message.encode("utf-8")

    # Log warning if message is very large
    if len(message_bytes) > 8192:
        logger.warning(
            f"⚠️ Large DCAP message ({len(message_bytes)} bytes) for {tool_name} - "
            "may require IP fragmentation"
        )

    # Send via UDP (IP layer handles fragmentation if needed)
    sock.sendto(message_bytes, (multicast_ip, port))
    sock.close()

    logger.debug(
        f"🪱 DCAP semantic_discover sent (UDP, {len(message_bytes)} bytes): "
        f"{tool_name} -> {multicast_ip}:{port}"
    )


def is_dcap_enabled() -> bool:
    """
    Check if DCAP broadcasting is enabled via environment variable.

    Returns:
        True if DCAP should broadcast, False otherwise
    """
    from ..env import get_env_bool

    return get_env_bool("DCAP_ENABLED", default=True)

