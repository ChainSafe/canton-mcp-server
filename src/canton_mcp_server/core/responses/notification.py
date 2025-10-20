"""
MCP Notification Handler

Factory-based approach for MCP notifications following the official MCP specification.
Notifications are one-way messages with no response expected.
Returns typed notification objects.
"""

from typing import Any, Optional

from ..types.mcp import (
    CancelledNotification,
    InitializedNotification,
    LoggingMessageNotification,
    ProgressNotification,
    PromptListChangedNotification,
    ResourceListChangedNotification,
    ToolListChangedNotification,
)


class NotificationResponse:
    """Factory for MCP notifications following official MCP specification

    Returns typed notification objects that match the MCP schema.
    All methods return JSONRPCNotification objects.
    """

    @staticmethod
    def progress(
        progress_token: str,
        progress: int,
        total: Optional[int] = None,
        message: Optional[str] = None,
        meta: Optional[dict] = None,
    ) -> ProgressNotification:
        """Create progress notification following MCP specification

        Args:
            progress_token: Token identifying the operation
            progress: Current progress value
            total: Total progress value (optional)
            message: Optional progress message
            meta: Optional metadata dict (will be set as _meta field per MCP spec)

        Returns:
            ProgressNotification object
        """
        params = {"progressToken": progress_token, "progress": progress}

        if total is not None:
            params["total"] = total

        if message is not None:
            params["message"] = message

        if meta is not None:
            params["_meta"] = meta

        return ProgressNotification(params=params)

    @staticmethod
    def initialized() -> InitializedNotification:
        """Create initialized notification following MCP specification

        Used to signal that initialization is complete.

        Returns:
            InitializedNotification object
        """
        return InitializedNotification()

    @staticmethod
    def cancelled(
        request_id: str, reason: Optional[str] = None
    ) -> CancelledNotification:
        """Create cancellation notification following MCP specification

        Args:
            request_id: ID of the request being cancelled
            reason: Optional reason for cancellation

        Returns:
            CancelledNotification object
        """
        params = {"requestId": request_id}
        if reason is not None:
            params["reason"] = reason

        return CancelledNotification(params=params)

    @staticmethod
    def tools_list_changed() -> ToolListChangedNotification:
        """Create tools list changed notification following MCP specification

        Used when the list of available tools has changed.

        Returns:
            ToolListChangedNotification object
        """
        return ToolListChangedNotification()

    @staticmethod
    def resources_list_changed() -> ResourceListChangedNotification:
        """Create resources list changed notification following MCP specification

        Used when the list of available resources has changed.

        Returns:
            ResourceListChangedNotification object
        """
        return ResourceListChangedNotification()

    @staticmethod
    def prompts_list_changed() -> PromptListChangedNotification:
        """Create prompts list changed notification following MCP specification

        Used when the list of available prompts has changed.

        Returns:
            PromptListChangedNotification object
        """
        return PromptListChangedNotification()

    @staticmethod
    def message(
        level: str, logger: str, data: Any, message: Optional[str] = None
    ) -> LoggingMessageNotification:
        """Create logging message notification following MCP specification

        Args:
            level: Log level (debug, info, warning, error)
            logger: Logger name
            data: Log data
            message: Optional log message

        Returns:
            LoggingMessageNotification object
        """
        params = {"level": level, "logger": logger, "data": data}
        if message:
            params["message"] = message

        return LoggingMessageNotification(params=params)
