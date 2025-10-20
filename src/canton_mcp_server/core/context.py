"""
Tool execution context.

This module defines ToolContext, which is passed to every tool execution.
It provides access to validated parameters, payment info, and helper
methods for progress, logging, and responses.
"""

import logging
from typing import Generic, List, Optional

from fastapi import Request

from .responses import NotificationResponse, ToolResponse
from .types import (
    PaymentContext,
    ToolRequest,
    TParams,
    TResult,
)
from .types.mcp import AudioContent, ContentBlock, ImageContent, TextContent

logger = logging.getLogger(__name__)


class ToolContext(Generic[TParams, TResult]):
    """
    Execution context for a tool call.

    Provides everything a tool needs to execute:
    - Validated input parameters (typed!)
    - Payment information
    - Methods to send progress/logs
    - Helper methods for responses

    Generic over:
    - TParams: Input parameter type (Pydantic model)
    - TResult: Expected result type (Pydantic model) - provides type safety for responses

    Example:
        ```python
        async def execute(self, ctx: ToolContext[MyParams, MyResult]):
            # Access typed params
            name = ctx.params.strategy_name

            # Send progress
            yield ctx.progress(50, 100, "Working...")

            # Send logs
            yield ctx.log("info", "Processing data")

            # Return success with typed result
            result = MyResult(items=42, status="done")
            yield ctx.structured(result)
        ```
    """

    def __init__(
        self,
        request: ToolRequest[TParams],
        fastapi_request: Request,
        payment: PaymentContext,
        session_id: str,
        # Infrastructure for AI agent tools
        session_manager: Optional[object] = None,
    ):
        """
        Initialize tool context.

        Args:
            request: Typed tool request with validated params
            fastapi_request: Underlying FastAPI request
            payment: Payment context with verification status
            session_id: Unique session identifier
            session_manager: Optional session manager for AI agent execution
        """
        # Input data
        self.request = request
        self.params = request.arguments  # Shortcut for convenience

        # Infrastructure
        self.payment = payment
        self.session_id = session_id
        self._fastapi_request = fastapi_request
        self._session_manager = session_manager

        # Request metadata
        self._request_id = request.request_id
        self._progress_token = request.progress_token

    # =============================================================================
    # Output Methods - How tools send responses
    # =============================================================================

    def progress(self, progress: int, total: int = None, message: str = None):
        """
        Create progress notification.

        Tools should yield this to send progress updates to the client.

        Args:
            progress: Current progress value (integer)
            total: Total progress value (optional, for percentage calculation)
            message: Optional progress message

        Returns:
            ProgressNotification that can be yielded

        Example:
            ```python
            yield ctx.progress(5, 10, "Processing 5/10...")
            yield ctx.progress(50, 100, "50% complete")
            ```
        """
        if not self._progress_token:
            logger.warning(
                "Progress notification requested but no progress token available"
            )
            return None

        return NotificationResponse.progress(
            progress_token=self._progress_token,
            progress=progress,
            total=total,
            message=message,
        )

    def log(self, level: str, message: str, data: dict = None):
        """
        Create log message notification.

        Tools should yield this to send log messages to the client.

        Args:
            level: Log level ("debug", "info", "warning", "error")
            message: Log message
            data: Optional structured log data

        Returns:
            LoggingMessageNotification that can be yielded

        Example:
            ```python
            yield ctx.log("info", "Processing started", {"items": 42})
            ```
        """
        # Log locally too
        log_method = getattr(logger, level.lower(), logger.info)
        log_method(f"[{self.request.name}] {message}")

        # Create notification for client
        return NotificationResponse.message(
            level=level.lower(),
            logger=self.request.name,
            data=data or {},
            message=message,
        )

    # =============================================================================
    # Generic Success Response
    # =============================================================================

    def success(
        self,
        content: List[ContentBlock] = None,
        data: dict = None,
        text: str = None,
    ):
        """
        Generic success response - most flexible method.

        Supports unstructured content, structured data, or both.

        Args:
            content: List of content blocks (text, image, audio, etc.)
            data: Structured response data (dict)
            text: Convenience shortcut for single text content block

        Returns:
            JSONRPCResponse ready to send

        Examples:
            ```python
            # Simple text (convenience)
            yield ctx.success(text="Done!")

            # Structured data only
            yield ctx.success(data={"items": 42, "status": "done"})

            # Mixed: content + structured
            yield ctx.success(
                content=[TextContent(text="Processed 42 items")],
                data={"items": 42, "status": "done"}
            )

            # Multiple content blocks
            yield ctx.success(content=[
                TextContent(text="Results:"),
                ImageContent(data=base64_img, mime_type="image/png")
            ])
            ```
        """
        # Build content blocks
        if text and not content:
            # Convenience: text param creates a text block
            content = [TextContent(text=text)]

        if content and data:
            # Both: unstructured + structured
            return ToolResponse.success(
                id=self.request.request_id,
                content=content,
                structured_content=data,
            )
        elif data:
            # Structured only (with JSON text for compatibility)
            return ToolResponse.structured_result(
                id=self.request.request_id,
                structured_data=data,
            )
        elif content:
            # Unstructured only
            return ToolResponse.unstructured_result(
                id=self.request.request_id,
                content=content,
            )
        else:
            # Nothing provided - empty success
            return ToolResponse.text_result(id=self.request.request_id, text="Success")

    # =============================================================================
    # Structured Response
    # =============================================================================

    def structured(self, result: TResult, summary_text: str = None):
        """
        Structured response with type-safe result.

        Use this when your tool returns typed structured data (Pydantic model).
        Provides IDE autocomplete and type checking.

        Args:
            result: Typed result object (Pydantic model or dict)
            summary_text: Optional human-readable summary

        Returns:
            JSONRPCResponse ready to send

        Example:
            ```python
            result = MyResult(items=42, status="done")
            yield ctx.structured(
                result,
                summary_text="Processed 42 items successfully"
            )
            ```
        """
        # Convert Pydantic model to dict if needed
        # Use by_alias=True to get camelCase field names for MCP protocol
        data = result.model_dump(by_alias=True) if hasattr(result, "model_dump") else result

        return ToolResponse.structured_result(
            id=self.request.request_id,
            structured_data=data,
            summary_text=summary_text,
        )

    # =============================================================================
    # Unstructured Responses (Content-Only)
    # =============================================================================

    def unstructured(self, content: List[ContentBlock]):
        """
        Unstructured response (content blocks only).

        Use this for pure content responses without structured data.

        Args:
            content: List of content blocks

        Returns:
            JSONRPCResponse ready to send

        Example:
            ```python
            yield ctx.unstructured([
                TextContent(text="Analysis complete"),
                ImageContent(data=chart_base64, mime_type="image/png")
            ])
            ```
        """
        return ToolResponse.unstructured_result(
            id=self.request.request_id,
            content=content,
        )

    # =============================================================================
    # Convenience Methods for Specific Content Types
    # =============================================================================

    def text(self, message: str):
        """
        Text-only response (convenience method).

        Args:
            message: Text message

        Returns:
            JSONRPCResponse ready to send

        Example:
            ```python
            yield ctx.text("Processing complete!")
            ```
        """
        return ToolResponse.text_result(id=self.request.request_id, text=message)

    def image(self, data: str, mime_type: str, alt_text: str = None):
        """
        Image response (convenience method).

        Args:
            data: Base64-encoded image data
            mime_type: MIME type (e.g., "image/png", "image/jpeg")
            alt_text: Optional alt text for accessibility

        Returns:
            JSONRPCResponse ready to send

        Example:
            ```python
            yield ctx.image(
                data=base64_chart,
                mime_type="image/png",
                alt_text="Performance chart"
            )
            ```
        """
        content = [ImageContent(data=data, mime_type=mime_type)]
        if alt_text:
            # Add alt text as annotations if needed
            content.insert(0, TextContent(text=alt_text))

        return ToolResponse.unstructured_result(
            id=self.request.request_id,
            content=content,
        )

    def audio(self, data: str, mime_type: str):
        """
        Audio response (convenience method).

        Args:
            data: Base64-encoded audio data
            mime_type: MIME type (e.g., "audio/mp3", "audio/wav")

        Returns:
            JSONRPCResponse ready to send

        Example:
            ```python
            yield ctx.audio(
                data=base64_audio,
                mime_type="audio/mp3"
            )
            ```
        """
        return ToolResponse.unstructured_result(
            id=self.request.request_id,
            content=[AudioContent(data=data, mime_type=mime_type)],
        )

    def error(self, code: int, message: str):
        """
        Build error response.

        Args:
            code: Error code (use ErrorCodes constants)
            message: Human-readable error message

        Returns:
            JSONRPCResponse with error

        Example:
            ```python
            from .responses import ErrorCodes

            yield ctx.error(ErrorCodes.INVALID_PARAMS, "Missing required field")
            yield ctx.error(ErrorCodes.INTERNAL_ERROR, "Database connection failed")
            ```
        """
        return ToolResponse.error(
            id=self.request.request_id,
            error_code=code,
            error_message=message,
        )

    # =============================================================================
    # AI Agent Execution - For reasoning tools
    # =============================================================================

    @property
    def session_manager(self):
        """
        Get session manager for AI agent execution.

        Returns:
            SessionManager instance

        Raises:
            RuntimeError: If session manager not available
        """
        if not self._session_manager:
            raise RuntimeError(
                "❌ Session manager not available\n"
                "   This tool requires AI agent execution capabilities.\n"
                "   The session manager is required for reasoning tools."
            )

        return self._session_manager

    @property
    def can_execute_agent(self) -> bool:
        """
        Check if AI agent execution is available.

        Returns:
            True if agent execution can be used, False otherwise
        """
        return self._session_manager is not None

    async def execute_agent(self, agent_type: str, prompt: str):
        """
        Execute an AI agent task with streaming results.

        This is a convenience method for reasoning tools that need to
        execute AI agents (backtesting, optimization, idea generation, etc.).

        Automatically handles session cleanup after execution completes.

        Args:
            agent_type: Type of agent (e.g., 'backtester', 'optimizer')
            prompt: Prompt for the agent

        Yields:
            Messages from the agent execution (progress, logs, results)

        Raises:
            RuntimeError: If session manager not available

        Example:
            ```python
            async def execute(self, ctx):
                # Execute AI agent with streaming
                async for message in ctx.execute_agent('backtester', prompt):
                    yield message
                # Session cleanup happens automatically!
            ```
        """
        if not self.can_execute_agent:
            raise RuntimeError(
                "AI agent execution not available. Session manager required."
            )

        try:
            # Execute task and forward all messages
            async for message in self.session_manager.execute_task(
                agent_type,
                prompt,
                self._request_id,
                self._progress_token,
            ):
                yield message
        finally:
            # Automatic session cleanup (session_id == request_id)
            # This prevents session/API key slot orphaning
            # Runs when generator completes, errors, or is closed
            session_id = str(self._request_id)
            try:
                logger.info(f"🔄 Cleaning up session {session_id}")
                await self.session_manager.cleanup_session(session_id)
                logger.info(f"✅ Cleaned up session {session_id}")
            except Exception as cleanup_error:
                logger.warning(
                    f"⚠️  Session cleanup error for {session_id}: {cleanup_error}"
                )
