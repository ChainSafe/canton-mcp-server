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
    Prompt,
    PromptArgument,
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
        "serverInfo": {
            "name": "canton-mcp-server",
            "version": "0.1.0",
            "description": (
                "Canton DAML MCP Server with Gate 1 Security Enforcement. "
                "Validates DAML smart contracts against canonical authorization patterns "
                "before allowing code creation. Always validate through Gate 1 first."
            )
        },
        "capabilities": {
            "tools": {"listChanged": False},
            "resources": {"subscribe": False, "listChanged": False},
            "prompts": {"listChanged": False},
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

    Returns:
        ListPromptsResult with available prompts including Gate 1 validation instructions
    """
    prompts = [
        Prompt(
            name="gate1-daml-validation",
            description=(
                "CRITICAL SECURITY INSTRUCTION: Always validate DAML code through Gate 1 "
                "BEFORE writing any files. This prevents unsafe authorization patterns from "
                "being created. Use validate_daml_business_logic tool to check code, and if "
                "validation fails, inform the user why and suggest safe alternatives. "
                "Never write DAML code that fails Gate 1 validation to the filesystem."
            ),
            arguments=None
        ),
        Prompt(
            name="daml-best-practices",
            description=(
                "When working with DAML code: "
                "1. Always define signatories (who authorizes contract creation) "
                "2. Controllers must be signatories or observers "
                "3. Use 'ensure' clauses for business logic validation "
                "4. Add observers for parties who need visibility "
                "5. Consider using two-step patterns (propose/accept) for transfers "
                "6. Validate through Gate 1 before writing files"
            ),
            arguments=None
        ),
        Prompt(
            name="canonical-patterns-first",
            description=(
                "Before creating new DAML patterns, search the canonical resource library "
                "using recommend_canonical_resources tool. With 30k+ verified patterns from "
                "the official DAML SDK, there's likely a safe, tested pattern that fits your "
                "use case. This saves time and ensures you're following best practices."
            ),
            arguments=None
        )
    ]
    
    return ListPromptsResult(prompts=prompts)
