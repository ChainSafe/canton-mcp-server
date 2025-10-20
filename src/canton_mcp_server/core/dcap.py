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
SERVER_ID = "canton-mcp"
SERVER_NAME = "Canton MCP Server"
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
) -> None:
    """
    Send DCAP perf_update message via direct UDP.

    Broadcasts tool performance metrics to real-time dashboards. Fails silently to
    never interrupt tool execution.

    Args:
        tool_name: Name of the tool that was executed
        exec_ms: Execution time in milliseconds
        success: Whether the tool execution succeeded
        args: Tool arguments (will be anonymized)
        cost_paid: Cost of the tool execution (optional)
        currency: Currency of the cost (default: "USDC")
    """
    try:
        # Get configuration from environment
        config = _get_dcap_config()

        # Skip if no multicast IP configured
        if not config:
            logger.debug("⚠️ DCAP not enabled - no IP configured")
            return

        # Build DCAP message (spec-compliant format)
        message = {
            "v": 2,  # Protocol version
            "ts": int(time.time()),  # Unix timestamp
            "t": "perf_update",  # Message type
            "sid": SERVER_ID,  # Server identifier
            "tool": tool_name,
            "exec_ms": exec_ms,
            "success": success,
            "ctx": {"args": anonymize_args(args) if args else {}},
        }

        # Add cost information if provided
        if cost_paid is not None:
            message["cost_paid"] = cost_paid
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


def is_dcap_enabled() -> bool:
    """
    Check if DCAP broadcasting is enabled via environment variable.

    Returns:
        True if DCAP should broadcast, False otherwise
    """
    from ..env import get_env_bool

    return get_env_bool("DCAP_ENABLED", default=True)

