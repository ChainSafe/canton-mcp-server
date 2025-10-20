"""
Base Response Classes

Generic JSON-RPC 2.0 response functionality for MCP protocol.
"""

from typing import Any, Optional

from ..types.mcp import JSONRPCError, JSONRPCResponse, RequestId


class ErrorCodes:
    """Standard JSON-RPC error codes"""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    UNAVAILABLE_RESOURCES = -32604

    # Custom MCP error codes
    TOOL_EXECUTION_ERROR = -32000
    VALIDATION_ERROR = -32002
    TIMEOUT_ERROR = -32003
    API_ERROR = -32004
    STRATEGY_NOT_FOUND = -32005


class Response:
    """Base class for JSON-RPC 2.0 responses

    Provides generic success and error response functionality.
    """

    @staticmethod
    def success(id: RequestId, result: Any) -> JSONRPCResponse:
        """Create successful JSON-RPC response

        Args:
            id: Request ID
            result: Response result data

        Returns:
            JSONRPCResponse object
        """
        return JSONRPCResponse(id=id, result=result)

    @staticmethod
    def error(
        id: RequestId, code: int, message: str, data: Optional[Any] = None
    ) -> JSONRPCResponse:
        """Create error JSON-RPC response

        Args:
            id: Request ID
            code: Error code
            message: Error message
            data: Optional error data

        Returns:
            JSONRPCResponse object with error
        """
        error_obj = JSONRPCError(code=code, message=message, data=data)
        return JSONRPCResponse(id=id, error=error_obj)
