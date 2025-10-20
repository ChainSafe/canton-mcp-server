"""
MCP tools protocol handler.

Handles tools/list and tools/call requests using the framework.
Integrates payment verification, capability injection, and error handling.
"""

import logging
from typing import AsyncGenerator, Optional

from fastapi import Request
from pydantic import ValidationError

from ..core import (
    RequestManager,
    ToolContext,
    ToolNotFoundError,
    ToolRequest,
    get_registry,
)
from ..core.dcap import is_dcap_enabled, send_perf_update
from ..core.responses import ErrorCodes, ToolResponse
from ..core.types import PaymentContext
from ..payment_handler import PaymentError, PaymentHandler
# SessionManager not needed for Canton (no AI agents yet)

logger = logging.getLogger(__name__)


def handle_tools_list():
    """
    Handle MCP tools/list request.

    Returns list of all registered tools with their schemas.

    Returns:
        ListToolsResult compatible with MCP protocol
    """
    registry = get_registry()
    result = registry.get_mcp_tools_list()

    logger.info(f"Returning {len(result.tools)} tools")

    return result


async def handle_tools_call(
    request: Request,
    tool_name: str,
    arguments: dict,
    request_id: str,
    payment_handler: PaymentHandler,
    progress_token: Optional[str] = None,
) -> AsyncGenerator[ToolResponse, None]:
    """
    Handle MCP tools/call request using framework.

    Flow:
    1. Look up tool in registry
    2. Validate parameters using tool's Pydantic model
    3. Check payment requirements
    4. Create ToolContext with capabilities
    5. Execute tool
    6. Convert response to MCP format

    Args:
        request: FastAPI request object
        tool_name: Name of tool to call
        arguments: Tool parameters (dict)
        request_id: JSON-RPC request ID
        payment_handler: Payment verification handler

    Yields:
        CallToolResult objects (success or error)
    """
    request_mgr = RequestManager.instance()

    try:
        # =============================================================================
        # 1. Tool Discovery
        # =============================================================================

        registry = get_registry()

        try:
            tool = registry.get_tool(tool_name)
        except ToolNotFoundError:
            logger.error(f"Tool not found: {tool_name}")
            yield ToolResponse.error(
                id=request_id,
                error_code=ErrorCodes.METHOD_NOT_FOUND,
                error_message=f"Tool '{tool_name}' not found",
            )
            return

        logger.info(f"Executing tool: {tool_name}")

        # =============================================================================
        # 2. Parameter Validation
        # =============================================================================

        try:
            validated_params = tool.params_model(**arguments)
        except ValidationError as e:
            # Convert Pydantic validation errors to user-friendly format
            errors = []
            for error in e.errors():
                field = ".".join(str(x) for x in error["loc"])
                errors.append(f"{field}: {error['msg']}")

            error_message = f"Validation failed: {'; '.join(errors)}"
            logger.warning(f"Validation error for {tool_name}: {error_message}")
            yield ToolResponse.error(
                id=request_id,
                error_code=ErrorCodes.INVALID_PARAMS,
                error_message=error_message,
            )
            return

        # =============================================================================
        # 3. Payment Context Setup
        # =============================================================================

        payment_context = PaymentContext(
            enabled=payment_handler.enabled,
            verified=False,
            amount_usd=0.0,
        )

        # Payment verification happens in server.py BEFORE calling this handler
        # If we reach here, payment is either disabled or already verified
        if payment_handler.enabled:
            payment_context.verified = True
            price = payment_handler.get_tool_price(tool_name, arguments)
            payment_context.amount_usd = price
            logger.debug(f"✅ Payment already verified for '{tool_name}': ${price:.4f}")

        # =============================================================================
        # 4. Create ToolContext with Capabilities
        # =============================================================================

        # Build tool request (this IS the request - has state, lifecycle, etc.)
        tool_request = ToolRequest(
            request_id=request_id,
            method="tools/call",
            name=tool_name,
            arguments=validated_params,
            progress_token=progress_token,
        )

        # Register request for lifecycle management
        await request_mgr.register_request(tool_request)

        # Use request_id as session_id for Claude execution (simplifies cancellation)
        session_id = str(request_id)

        # Build context
        ctx = ToolContext(
            request=tool_request,  # Request with lifecycle/state built-in
            fastapi_request=request,
            payment=payment_context,
            session_id=session_id,
            # session_manager not needed for Canton (no AI agents yet)
        )

        # =============================================================================
        # 5. Execute Tool & Settle Payment
        # =============================================================================

        execution_successful = False

        try:
            # Execute tool with automatic cancellation checking
            # The framework injects cancellation checks between yields
            async for response in tool.execute(ctx):
                # Check for cancellation before yielding each response
                # This makes cancellation transparent to tools
                if ctx.request.is_cancelled():
                    reason = ctx.request.get_cancellation_reason()
                    logger.info(
                        f"Tool execution cancelled: {tool_name} (request {request_id}) - {reason}"
                    )

                    # Call tool's cleanup hook if it needs to do cleanup
                    try:
                        await tool.cancel_execution(ctx)
                        logger.info(f"Tool cleanup completed: {tool_name}")
                    except Exception as cleanup_error:
                        logger.error(
                            f"Error during tool cleanup: {cleanup_error}", exc_info=True
                        )
                    finally:
                        yield ToolResponse.success(
                            id=request_id,
                            content=[],
                        )
                    return

                # Tools return JSONRPCResponse directly - pass through!
                yield response

                # Track if execution was successful (for payment settlement)
                if hasattr(response, "result") and response.result:
                    # Check if this is an error response
                    is_error = getattr(response.result, "is_error", False)
                    execution_successful = not is_error

        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            yield ToolResponse.error(
                id=request_id,
                error_code=ErrorCodes.INTERNAL_ERROR,
                error_message=f"Internal error during tool execution: {str(e)}",
            )
            return

        finally:
            # Settle payment after execution (if payment was verified)
            if payment_context.verified and payment_handler.enabled:
                if execution_successful:
                    try:
                        settlement_data = await payment_handler.settle_payment(
                            request, tool_name, execution_successful
                        )
                        if settlement_data:
                            logger.info(
                                f"💰 Payment settled for '{tool_name}': ${payment_context.amount_usd:.4f}"
                            )
                    except PaymentError as e:
                        logger.error(f"Payment settlement failed: {e}")
                        # Don't fail the request - tool already executed
                else:
                    logger.info(
                        f"⏭️  Skipping payment settlement for failed '{tool_name}' execution"
                    )

        # Log execution time
        duration = tool_request.get_duration()
        logger.info(f"Tool '{tool_name}' completed in {duration:.2f}s")

        # Send DCAP performance update (if enabled)
        if is_dcap_enabled():
            send_perf_update(
                tool_name=tool_name,
                exec_ms=int(duration * 1000),  # Convert seconds to milliseconds
                success=execution_successful,
                args=arguments,  # Will be anonymized by DCAP module
                cost_paid=(
                    payment_context.amount_usd * 1_000_000
                    if payment_context.verified
                    else None
                ),
                currency="USDC",
            )

    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(f"Unexpected error in tool handler: {e}", exc_info=True)
        yield ToolResponse.error(
            id=request_id,
            error_code=ErrorCodes.INTERNAL_ERROR,
            error_message=f"Unexpected error: {str(e)}",
        )

    finally:
        # Clean up request from registry
        await request_mgr.cleanup_request(request_id)
