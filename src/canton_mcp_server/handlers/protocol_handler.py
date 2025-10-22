"""
MCP Protocol Handlers

Handles core MCP protocol methods:
- Lifecycle: initialize, ping
- Notifications: initialized, cancelled
- Logging: setLevel
- Resources: list (placeholder)
- Prompts: list (placeholder)
"""

import logging

from ..core import RequestManager
from ..core.types import (
    ListPromptsResult,
    ListResourcesResult,
)

logger = logging.getLogger(__name__)
request_manager = RequestManager.instance()


# =============================================================================
# Lifecycle Handlers
# =============================================================================


async def handle_initialize(params: dict) -> dict:
    """
    Handle MCP initialize request.

    Returns server capabilities and information.

    Args:
        params: Initialize parameters from client

    Returns:
        Dict with protocol version, capabilities, and server info
    """
    client_info = params.get("clientInfo", {})
    if client_info:
        logger.info(
            f"Connected client: {client_info.get('name', 'unknown')} v{client_info.get('version', 'unknown')}"
        )

    return {
        "protocolVersion": "2025-06-18",
        "serverInfo": {"name": "canton-mcp-server", "version": "0.1.0"},
        "capabilities": {
            "tools": {"listChanged": False},
            "resources": {"subscribe": False, "listChanged": False},
            "logging": {},
        },
    }


def handle_ping() -> dict:
    """
    Handle MCP ping request.

    Ping is used for connectivity testing and keepalive.
    Returns an empty object per MCP spec.

    Returns:
        Empty dict
    """
    return {}


# =============================================================================
# Notification Handlers
# =============================================================================


def handle_initialized() -> dict:
    """
    Handle notifications/initialized.

    Sent by client after successful initialization.
    Currently just acknowledges receipt.

    Returns:
        Empty dict (202 Accepted)
    """
    logger.debug("Client initialized")
    return {}


async def handle_cancelled(request_id: str = None, reason: str = None) -> dict:
    """
    Handle notifications/cancelled.

    Sent by client to cancel an ongoing operation.

    Per MCP specification:
    - Cancellation notifications are "fire and forget"
    - Should only cancel requests that are still in-progress
    - Unknown/completed requests should be ignored gracefully
    - Cancellation reason should be logged for debugging

    Args:
        request_id: ID of request to cancel
        reason: Optional cancellation reason

    Returns:
        Empty dict
    """
    await request_manager.cancel_request(request_id, reason)
    return {}


# =============================================================================
# Logging Handler
# =============================================================================


def handle_set_level(level: str) -> dict:
    """
    Handle logging/setLevel request.

    Sets the server's logging level.

    Args:
        level: Log level ("debug", "info", "warning", "error")

    Returns:
        Empty dict (success)
    """
    logger.info(f"Setting log level to: {level}")

    # Map MCP log levels to Python logging levels
    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }

    python_level = level_map.get(level.lower(), logging.INFO)
    logging.getLogger().setLevel(python_level)

    return {}


# =============================================================================
# Resource Handlers (Placeholder)
# =============================================================================


def handle_resources_list() -> ListResourcesResult:
    """
    Handle resources/list request.

    Returns list of available Canton canonical resources.

    Returns:
        ListResourcesResult with available resources
    """
    from .resource_handler import handle_resources_list as _handle_resources_list
    return _handle_resources_list()


# =============================================================================
# Prompt Handlers (Placeholder)
# =============================================================================


def handle_prompts_list() -> ListPromptsResult:
    """
    Handle prompts/list request.

    Returns list of available prompts/templates.
    Currently returns empty list.

    Returns:
        ListPromptsResult with empty prompts list

    TODO: Implement actual prompts
    - Strategy analysis prompts
    - Market analysis prompts
    - Trading decision prompts
    """
    return ListPromptsResult(prompts=[])
