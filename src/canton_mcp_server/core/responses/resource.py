"""
Resource Response Classes

Resource-specific response functionality for MCP protocol.
"""

from typing import Any, List

from ..responses.base import Response
from ..types.mcp import JSONRPCResponse, RequestId


class ResourceResponse(Response):
    """Factory for resource-related JSON-RPC 2.0 responses

    Handles responses for resource operations like:
    - Listing available resources
    - Reading resource contents
    - Resource subscription updates

    Examples:

    # Resource list response
    ResourceResponse.list_success(id, resources)

    # Resource read response
    ResourceResponse.read_success(id, contents)

    # Resource error
    ResourceResponse.error(id, -1, "Resource not found")
    """

    @staticmethod
    def list_success(id: RequestId, resources: List[Any]) -> JSONRPCResponse:
        """Create successful resource list response

        Args:
            id: Request ID
            resources: List of available resources

        Returns:
            JSONRPCResponse object with resource list
        """
        result = {"resources": resources}
        return Response.success(id, result)

    @staticmethod
    def read_success(id: RequestId, contents: List[Any]) -> JSONRPCResponse:
        """Create successful resource read response

        Args:
            id: Request ID
            contents: List of resource contents

        Returns:
            JSONRPCResponse object with resource contents
        """
        result = {"contents": contents}
        return Response.success(id, result)

    @staticmethod
    def subscribe_success(id: RequestId) -> JSONRPCResponse:
        """Create successful resource subscription response

        Args:
            id: Request ID

        Returns:
            JSONRPCResponse object confirming subscription
        """
        result = {}
        return Response.success(id, result)

    @staticmethod
    def unsubscribe_success(id: RequestId) -> JSONRPCResponse:
        """Create successful resource unsubscription response

        Args:
            id: Request ID

        Returns:
            JSONRPCResponse object confirming unsubscription
        """
        result = {}
        return Response.success(id, result)
