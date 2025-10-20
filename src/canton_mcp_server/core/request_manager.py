"""
Request Manager - Manages active requests.

Central registry for all active requests in the MCP server.
Provides a clean API for request lifecycle operations.
"""

import asyncio
import logging
from typing import Dict, Optional

from .types.models import BaseRequest

logger = logging.getLogger(__name__)


class RequestManager:
    """
    Manages all active requests (tools, prompts, resources, etc.).

    Singleton class - use RequestManager.instance() to get the shared instance.

    Provides the communication layer for request-scoped operations:
    - Registering and tracking requests
    - Cancellation signaling
    - Future: elicitation, progress coordination, etc.

    This is a framework component - tools don't interact with it directly.
    Works with any BaseRequest subclass (ToolRequest, PromptRequest, etc.)
    """

    _instance: Optional["RequestManager"] = None
    _lock_class = asyncio.Lock()

    def __new__(cls):
        """Singleton pattern - only one instance exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize only once."""
        if self._initialized:
            return

        self._requests: Dict[str, BaseRequest] = {}
        self._lock = asyncio.Lock()
        self._initialized = True

    @classmethod
    def instance(cls) -> "RequestManager":
        """
        Get the singleton instance of RequestManager.

        Returns:
            The shared RequestManager instance

        Example:
            ```python
            request_mgr = RequestManager.instance()
            await request_mgr.register_request(tool_request)
            ```
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def register_request(self, request: BaseRequest):
        """
        Register an existing request for tracking.

        Args:
            request: Request instance to register (ToolRequest, etc.)
        """
        async with self._lock:
            self._requests[request.request_id] = request
            logger.debug(f"Registered request: {request.request_id} ({request.method})")

    async def cancel_request(
        self, request_id: str, reason: Optional[str] = None
    ) -> bool:
        """
        Signal cancellation for a request.

        Per MCP spec:
        - Unknown/completed requests should be ignored gracefully
        - This is "fire and forget"

        Args:
            request_id: ID of request to cancel
            reason: Optional reason for cancellation

        Returns:
            True if request was found and cancelled, False if unknown
        """
        async with self._lock:
            if request_id not in self._requests:
                logger.debug(
                    f"Cancellation requested for unknown request: {request_id}"
                )
                return False

            request = self._requests[request_id]

            # Cancel the request
            request.cancel(reason)

            return True

    async def cleanup_request(self, request_id: str):
        """
        Remove request from tracking.

        Args:
            request_id: ID of request to clean up
        """
        async with self._lock:
            if request_id in self._requests:
                del self._requests[request_id]
                logger.debug(f"Cleaned up request: {request_id}")

