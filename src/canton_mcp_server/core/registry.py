"""
Tool registry for automatic tool discovery and management.

This module provides:
- ToolRegistry: Central registry for all tools
- @register_tool: Decorator for automatic tool registration
- get_registry(): Access to global registry
"""

import logging
from typing import Dict, List

from .base import Tool

logger = logging.getLogger(__name__)


class ToolNotFoundError(Exception):
    """Raised when requested tool is not found in registry"""

    pass


class ToolRegistry:
    """
    Central registry for all MCP tools.

    Automatically discovers and manages tools that use the @register_tool
    decorator. Provides methods for listing and retrieving tools.

    Example:
        ```python
        registry = get_registry()

        # Get a specific tool
        tool = registry.get_tool("run_backtest")

        # List all tools
        all_tools = registry.list_tools()

        # Generate MCP tools/list response
        mcp_response = registry.get_mcp_tools_list()
        ```
    """

    def __init__(self):
        """Initialize empty registry"""
        self._tools: Dict[str, Tool] = {}
        logger.debug("Tool registry initialized")

    def register(self, tool: Tool) -> None:
        """
        Register a tool in the registry.

        Args:
            tool: Tool instance to register

        Raises:
            ValueError: If tool with same name already registered
        """
        if tool.name in self._tools:
            raise ValueError(
                f"Tool '{tool.name}' is already registered. "
                f"Existing: {self._tools[tool.name].__class__.__name__}, "
                f"New: {tool.__class__.__name__}"
            )

        self._tools[tool.name] = tool

        # Log registration with pricing info
        pricing_type = (
            tool.pricing.type.value if hasattr(tool.pricing, "type") else "unknown"
        )
        logger.info(f"Registered tool: {tool.name} (pricing: {pricing_type})")

    def get_tool(self, name: str) -> Tool:
        """
        Get a tool by name.

        Args:
            name: Tool name to retrieve

        Returns:
            Tool instance

        Raises:
            ToolNotFoundError: If tool not found
        """
        if name not in self._tools:
            available = ", ".join(self._tools.keys())
            raise ToolNotFoundError(
                f"Tool '{name}' not found. " f"Available tools: {available}"
            )

        return self._tools[name]

    def list_tools(self) -> List[Tool]:
        """
        List all registered tools.

        Returns:
            List of all tool instances
        """
        return list(self._tools.values())

    def get_mcp_tools_list(self):
        """
        Generate MCP tools/list response.

        Converts all registered tools into the MCP ListToolsResult format,
        including input/output schemas.

        Returns:
            ListToolsResult compatible with MCP protocol
        """
        from .types.mcp import ListToolsResult
        from .types.mcp import Tool as MCPTool

        mcp_tools = []

        for tool in self._tools.values():
            # Build MCP tool definition
            mcp_tool = MCPTool(
                name=tool.name,
                description=tool.description,
                input_schema=tool.get_input_schema(),
            )

            # Add output schema if available
            output_schema = tool.get_output_schema()
            if output_schema:
                # MCP spec allows output_schema as extension
                mcp_tool.output_schema = output_schema

            mcp_tools.append(mcp_tool)

        logger.debug(f"Generated MCP tools list: {len(mcp_tools)} tools")

        return ListToolsResult(tools=mcp_tools)

    def __len__(self) -> int:
        """Return number of registered tools"""
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        """Check if tool is registered"""
        return name in self._tools


# Global registry instance
_registry = ToolRegistry()


def register_tool(cls):
    """
    Decorator to automatically register a tool.

    Use this decorator on tool classes to automatically register them
    when the module is imported.

    Example:
        ```python
        @register_tool
        class MyTool(Tool[MyParams, MyResult]):
            name = "my_tool"
            description = "Does something"
            params_model = MyParams
            pricing = ToolPricing(type=PricingType.FREE)

            async def execute(self, ctx):
                yield ctx.success({"result": "done"})
        ```

    Args:
        cls: Tool class to register

    Returns:
        The same class (unmodified)
    """
    # Instantiate the tool
    instance = cls()

    # Register it
    _registry.register(instance)

    # Return the class (decorator pattern)
    return cls


def get_registry() -> ToolRegistry:
    """
    Get the global tool registry.

    Returns:
        Global ToolRegistry instance
    """
    return _registry
