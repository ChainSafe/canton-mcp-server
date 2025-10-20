"""
Tool Response Classes

Tool-specific response functionality for MCP protocol.
"""

from typing import Any, Dict, List, Optional

from ..responses.base import ErrorCodes, Response
from ..types.mcp import (
    CallToolResult,
    ContentBlock,
    JSONRPCResponse,
    RequestId,
    TextContent,
)


class ToolResponse(Response):
    """Factory for tool-related JSON-RPC 2.0 responses

    Tool Result Types (per MCP specification):

    1. UNSTRUCTURED TOOLS (content only):
       - Use unstructured_result() for pure content (text, images, audio)
       - Use success() for mixed content with optional structured data

    2. STRUCTURED TOOLS (structured data + backward-compatible text):
       - Use structured_result() for primary structured responses
       - Automatically includes JSON serialization in text content for compatibility

    3. ERROR HANDLING:
       - Protocol errors: Use Response.error() for JSON-RPC errors
       - Tool execution errors: Use error() for tool execution failures

    Examples:

    # Unstructured tool (text only)
    ToolResponse.unstructured_result(id, [TextContent(text="Weather: 72°F")])

    # Structured tool (with backward compatibility)
    ToolResponse.structured_result(id, {"temp": 72, "unit": "F"}, "Weather: 72°F")

    # Mixed tool (content + structured data)
    ToolResponse.success(id, [TextContent(text="Summary")], {"detailed": "data"})
    """

    @staticmethod
    def success(
        id: RequestId,
        content: List[ContentBlock],
        structured_content: Optional[Dict[str, Any]] = None,
    ) -> JSONRPCResponse:
        """Create successful tool call response with proper MCP format

        Args:
            id: Request ID
            content: List of content blocks (text, images, etc.)
            structured_content: Optional structured data

        Returns:
            JSONRPCResponse object with CallToolResult
        """
        result = CallToolResult(
            content=content, is_error=False, structured_content=structured_content
        )
        return JSONRPCResponse(id=id, result=result)

    @staticmethod
    def error(
        id: RequestId,
        error_code: int = ErrorCodes.INTERNAL_ERROR,
        error_message: str = None,
    ) -> JSONRPCResponse:
        """Create tool execution error response (success with isError=true)

        According to MCP spec, tool execution errors should be returned as successful
        responses with isError=true so the LLM can see the error and self-correct.

        IMPORTANT: Error responses do NOT include structured_content to avoid
        schema validation issues (error structure doesn't match result schema).

        Args:
            id: Request ID
            error_code: Error code (defaults to INTERNAL_ERROR -32603 if not provided)
            error_message: Error message to display

        Returns:
            JSONRPCResponse object with error CallToolResult
        """
        if error_message is None:
            error_text = "Tool execution failed"
        else:
            error_text = f"Tool execution failed: {error_message}"
        content = [TextContent(text=error_text)]

        # Don't include structured_content for errors - prevents validation issues
        # Error info is already in the text content
        result = CallToolResult(content=content, is_error=True, structured_content=None)
        return JSONRPCResponse(id=id, result=result)

    @staticmethod
    def text_result(
        id: RequestId, text: str, structured_content: Optional[Dict[str, Any]] = None
    ) -> JSONRPCResponse:
        """Create a simple text result

        Args:
            id: Request ID
            text: Text content to return
            structured_content: Optional structured data

        Returns:
            JSONRPCResponse object with text content
        """
        content = [TextContent(text=text)]
        return ToolResponse.success(id, content, structured_content)

    @staticmethod
    def structured_result(
        id: RequestId,
        structured_data: Dict[str, Any],
        summary_text: Optional[str] = None,
    ) -> JSONRPCResponse:
        """Create a structured tool result with backward-compatible text content

        According to MCP spec, structured tools SHOULD also provide serialized JSON
        in a TextContent block for backward compatibility.

        Args:
            id: Request ID
            structured_data: The structured data to return
            summary_text: Optional human-readable summary. If None, JSON will be serialized

        Returns:
            JSONRPCResponse object with structured CallToolResult
        """
        import json

        # Create text content for backward compatibility
        if summary_text is None:
            summary_text = json.dumps(structured_data, indent=2)

        content = [TextContent(text=summary_text)]
        result = CallToolResult(
            content=content, is_error=False, structured_content=structured_data
        )
        return JSONRPCResponse(id=id, result=result)

    @staticmethod
    def unstructured_result(
        id: RequestId, content: List[ContentBlock]
    ) -> JSONRPCResponse:
        """Create an unstructured tool result (content only, no structured data)

        For tools that return only unstructured content like text, images, audio, etc.

        Args:
            id: Request ID
            content: List of content blocks

        Returns:
            JSONRPCResponse object with unstructured CallToolResult
        """
        result = CallToolResult(
            content=content, is_error=False, structured_content=None
        )
        return JSONRPCResponse(id=id, result=result)
