"""
MCP Server Framework - Core Module

This package provides the foundation for building MCP tools:
- Tool base class for implementing tools
- ToolContext for accessing request data and helpers
- Type-safe request/response models
- Automatic tool registration
- Pricing system
- Validation helpers

Example:
    ```python
    from . import Tool, ToolContext, register_tool
    from .pricing import ToolPricing, PricingType
    from pydantic import BaseModel

    class MyParams(BaseModel):
        name: str

    @register_tool
    class MyTool(Tool[MyParams, dict]):
        name = "my_tool"
        description = "My cool tool"
        params_model = MyParams
        pricing = ToolPricing(type=PricingType.FREE)

        async def execute(self, ctx: ToolContext[MyParams]):
            yield ctx.success({"result": f"Hello {ctx.params.name}!"})
    ```
"""

# Base classes
from .base import Tool
from .context import ToolContext

# Pricing
from .pricing import PricingType, ToolPricing

# Registry
from .registry import ToolNotFoundError, get_registry, register_tool

# Request management
from .request_manager import RequestManager

# MCP Protocol Responses (factories)
from .responses import (
    ErrorCodes,
    NotificationResponse,
    PromptResponse,
    ResourceResponse,
    Response,
)

# Type definitions
from .types import (
    ToolResponse,  # Type alias: Union[JSONRPCResponse, JSONRPCNotification]
)
from .types import (
    BaseRequest,
    MCPModel,
    PaymentContext,
    ToolRequest,
)

__all__ = [
    # Base
    "Tool",
    "ToolContext",
    # Types
    "BaseRequest",
    "MCPModel",
    "ToolRequest",
    "ToolResponse",  # Type for what tools yield
    "PaymentContext",
    # Registry
    "register_tool",
    "get_registry",
    "ToolNotFoundError",
    # Pricing
    "ToolPricing",
    "PricingType",
    # Request management
    "RequestManager",
    # MCP Responses (internal use via ctx methods)
    "Response",
    "ErrorCodes",
    "ResourceResponse",
    "PromptResponse",
    "NotificationResponse",
]

