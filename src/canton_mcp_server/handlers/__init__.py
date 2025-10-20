"""
MCP Request Handlers

Organized handlers for all MCP protocol methods.
"""

# Protocol handlers (lifecycle, notifications, logging, resources, prompts)
from .protocol_handler import (
    handle_cancelled,
    handle_initialize,
    handle_initialized,
    handle_ping,
    handle_prompts_list,
    handle_resources_list,
    handle_set_level,
)

# Tool handlers (tools/list, tools/call)
from .tool_handler import handle_tools_call, handle_tools_list

__all__ = [
    # Lifecycle
    "handle_initialize",
    "handle_ping",
    # Notifications
    "handle_initialized",
    "handle_cancelled",
    # Logging
    "handle_set_level",
    # Resources
    "handle_resources_list",
    # Prompts
    "handle_prompts_list",
    # Tools
    "handle_tools_list",
    "handle_tools_call",
]
