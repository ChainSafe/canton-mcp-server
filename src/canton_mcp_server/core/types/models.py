"""
Core type definitions for the MCP server framework.

This module defines the fundamental types used throughout the framework:
- BaseRequest: Base class for all MCP requests (tools, prompts, resources, etc.)
- ToolRequest: Typed incoming tool call request (inherits from BaseRequest)
- PaymentContext: Payment information wrapper
"""

from abc import ABC
from datetime import datetime
from typing import Generic, Optional, TypeVar, Union

from pydantic import BaseModel, ConfigDict, Field

from canton_mcp_server.utils.conversion import snake_to_camel

from ..types.mcp import JSONRPCNotification, JSONRPCResponse


class MCPModel(BaseModel):
    """
    Base model for all MCP tool parameters and results.

    Automatically converts field names to camelCase for JSON schema and serialization,
    which is required by the MCP protocol.

    Example:
        ```python
        class MyToolParams(MCPModel):
            user_name: str  # ← In Python: snake_case
            age_in_years: int

        # JSON schema will have: userName, ageInYears (camelCase)
        # Python access: params.user_name (snake_case)
        ```
    """

    model_config = ConfigDict(
        alias_generator=snake_to_camel,
        populate_by_name=True,  # Allow both snake_case and camelCase when parsing
    )


# Type variables for generic tool definitions
TParams = TypeVar("TParams", bound=BaseModel)
TResult = TypeVar("TResult")

# What tools can yield: either responses (with results) or notifications (progress, logs)
ToolResponse = Union[JSONRPCResponse, JSONRPCNotification]


class BaseRequest(BaseModel, ABC):
    """
    Base class for all MCP requests.

    Provides unified request representation for:
    - Tool calls
    - Prompt requests (future)
    - Resource reads (future)
    - Sampling requests (future)
    - Any other MCP operation

    Subclasses add their own specific fields (e.g., ToolRequest adds arguments).

    Attributes:
        request_id: Unique identifier for this request (string or int per JSON-RPC 2.0 spec)
        method: MCP method being called (e.g., "tools/call", "prompts/get")
        created_at: When the request was created
        cancelled: Whether cancellation has been requested
        cancellation_reason: Optional reason for cancellation
    """

    request_id: str | int
    method: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Cancellation support
    cancelled: bool = False
    cancellation_reason: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True

    def cancel(self, reason: Optional[str] = None):
        """
        Signal cancellation for this request.

        Args:
            reason: Optional reason for cancellation
        """
        self.cancelled = True
        self.cancellation_reason = reason or "Request cancelled"

    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested."""
        return self.cancelled

    def get_cancellation_reason(self) -> Optional[str]:
        """Get the reason for cancellation, if any."""
        return self.cancellation_reason

    def get_duration(self) -> float:
        """Get request duration in seconds."""
        return (datetime.utcnow() - self.created_at).total_seconds()


class ToolRequest(BaseRequest, Generic[TParams]):
    """
    Typed representation of an incoming MCP tool call request.

    Inherits from BaseRequest (cancellation support, metadata) and adds tool-specific fields.

    Attributes from BaseRequest:
        request_id: Unique identifier for this request
        method: MCP method name (always "tools/call")
        created_at: When the request was created
        cancelled: Whether cancellation has been requested
        cancellation_reason: Optional reason for cancellation

    Tool-specific attributes:
        name: Name of the tool being called
        arguments: Validated and typed parameters
        progress_token: Optional token for progress notifications
        client_info: Optional client metadata
    """

    # Tool-specific fields
    name: str
    arguments: TParams  # Validated parameters (typed!)
    progress_token: Optional[Union[str, int]] = (
        None  # Progress token (can be string or int per JSON-RPC 2.0 spec)
    )
    client_info: Optional[dict] = None

    class Config:
        arbitrary_types_allowed = True


class PaymentContext(BaseModel):
    """
    Payment information for the current tool execution.

    Attached to ToolContext to provide payment status information.

    Attributes:
        enabled: Whether payment system is enabled
        verified: Whether payment has been verified for this request
        amount_usd: Payment amount in USD
        payment: Optional payment payload data
        payer: Optional payer wallet address (from x402 settlement)
        caller: Optional caller identifier (agent/user name)
    """

    enabled: bool
    verified: bool
    amount_usd: float = 0.0
    payment: Optional[dict] = None
    payer: Optional[str] = None  # Wallet address from x402 settlement
    caller: Optional[str] = None  # Agent/user identifier

    class Config:
        arbitrary_types_allowed = True

