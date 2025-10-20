"""
Prompt Response Classes

Prompt-specific response functionality for MCP protocol.
"""

from typing import Any, List, Optional

from ..responses.base import Response
from ..types.mcp import JSONRPCResponse, RequestId


class PromptResponse(Response):
    """Factory for prompt-related JSON-RPC 2.0 responses

    Handles responses for prompt operations like:
    - Listing available prompts
    - Getting prompt details and messages
    - Prompt argument validation

    Examples:

    # Prompt list response
    PromptResponse.list_success(id, prompts)

    # Get prompt response
    PromptResponse.get_success(id, description, messages)

    # Prompt error
    PromptResponse.error(id, -1, "Prompt not found")
    """

    @staticmethod
    def list_success(id: RequestId, prompts: List[Any]) -> JSONRPCResponse:
        """Create successful prompt list response

        Args:
            id: Request ID
            prompts: List of available prompts

        Returns:
            JSONRPCResponse object with prompt list
        """
        result = {"prompts": prompts}
        return Response.success(id, result)

    @staticmethod
    def get_success(
        id: RequestId,
        description: Optional[str] = None,
        messages: Optional[List[Any]] = None,
    ) -> JSONRPCResponse:
        """Create successful get prompt response

        Args:
            id: Request ID
            description: Optional prompt description
            messages: List of prompt messages

        Returns:
            JSONRPCResponse object with prompt details
        """
        result = {}
        if description is not None:
            result["description"] = description
        if messages is not None:
            result["messages"] = messages
        return Response.success(id, result)
