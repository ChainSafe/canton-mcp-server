#!/usr/bin/env python3
"""
Canton MCP Server - Model Context Protocol Implementation

Clean, framework-driven server with automatic tool registration,
payment integration (disabled by default), DCAP performance tracking,
and streaming support.
"""

import asyncio
import datetime
import json
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from canton_mcp_server import tools  # noqa: F401
from canton_mcp_server.core import RequestManager, get_registry
from canton_mcp_server.core.responses import (
    ErrorCodes,
    PromptResponse,
    ResourceResponse,
    Response,
)
from canton_mcp_server.core.types import JSONRPCRequest
from canton_mcp_server.handlers import (
    handle_cancelled,
    handle_initialize,
    handle_initialized,
    handle_ping,
    handle_prompts_list,
    handle_resources_list,
    handle_set_level,
    handle_tools_call,
    handle_tools_list,
)
from canton_mcp_server.payment_handler import (
    PaymentConfigurationError,
    PaymentHandler,
    PaymentRequiredError,
    PaymentSettlementError,
    PaymentVerificationError,
)
from canton_mcp_server.utils.conversion import convert_keys_to_snake_case

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)-5s | %(message)s")
logger = logging.getLogger(__name__)

# Reduce uvicorn access log noise (only show warnings/errors)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# Global instances
payment_handler = PaymentHandler()


# =============================================================================
# Application Lifecycle
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic for the Canton MCP server"""
    # Startup
    logger.info("Starting Canton MCP Server...")

    # Log registered tools
    registry = get_registry()
    logger.info(f"✅ Registered {len(registry)} tools:")
    for tool in registry.list_tools():
        pricing = (
            "FREE"
            if tool.pricing.type.value == "free"
            else f"${tool.pricing.base_price}"
        )
        logger.info(f"   - {tool.name}: {tool.description[:60]}... ({pricing})")

    yield

    # Shutdown
    logger.info("Shutting down...")


# =============================================================================
# FastAPI Application Setup
# =============================================================================


app = FastAPI(
    title="Canton MCP Server",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-request-id", "x-stream-format"],
)


# =============================================================================
# Helper Functions
# =============================================================================


def success_response(request_id, result, status_code=200):
    """Helper to create success JSON response"""
    return JSONResponse(
        content=Response.success(request_id, result).to_camel_dict(),
        status_code=status_code,
    )


def error_response(request_id, error_code: int, message: str, status_code=200):
    """Helper to create error JSON response"""
    return JSONResponse(
        content=Response.error(request_id, error_code, message).to_camel_dict(),
        status_code=status_code,
    )


async def create_sse_stream(generator):
    """Convert message generator to SSE format"""
    try:
        async for message in generator:
            yield f'data: {json.dumps(message.to_camel_dict(), separators=(",", ":"))}\n\n'
            await asyncio.sleep(0.01)  # Ensure message is sent
    except Exception as e:
        logger.error(f"Streaming error: {e}")


async def collect_final_result(generator):
    """Collect final result from generator (non-streaming mode)"""
    final_response = None
    async for response in generator:
        # Keep the last response
        final_response = response
    return final_response


# =============================================================================
# Tool Call Handler (with Payment Integration)
# =============================================================================


async def handle_tool_call_request(mcp_request: JSONRPCRequest, request: Request):
    """
    Handle tools/call with x402 payment verification.

    Payment flow:
    - PHASE 1: Verify payment (if enabled)
    - PHASE 2: Execute tool (in tool_handler)
    - PHASE 3: Settle payment (in tool_handler)
    """
    params = mcp_request.params or {}
    tool_name = params.get("name")
    arguments = params.get("arguments", {})
    progress_token = params.get("_meta", {}).get("progress_token")

    if not tool_name:
        return error_response(mcp_request.id, ErrorCodes.INVALID_PARAMS, "Missing tool name")

    # =============================================================================
    # Payment Verification (PHASE 1: Verify)
    # =============================================================================
    # Only verify payment if payment system is enabled
    # Settlement happens later in tool_handler.py based on execution outcome

    if payment_handler.enabled:
        try:
            # Verify payment for this tool call
            await payment_handler.verify_payment(request, tool_name, arguments)
        except PaymentRequiredError as e:
            # Payment required but not provided - return x402 response
            logger.warning(
                f"💰 Payment required for '{tool_name}': {e.message}"
            )
            response_data = {
                "x402Version": 1,
                "accepts": e.payment_requirements or [],
                "error": e.message,
            }
            return JSONResponse(status_code=e.status_code, content=response_data)
        except PaymentVerificationError as e:
            # Payment verification failed - return x402 error response
            logger.error(
                f"💰 Payment verification failed for '{tool_name}': {e.message}"
            )
            response_data = {
                "x402Version": 1,
                "accepts": e.payment_requirements or [],
                "error": e.message,
                "errorCode": e.error_data.error_code,
            }
            return JSONResponse(status_code=e.status_code, content=response_data)
        except PaymentConfigurationError as e:
            # Payment configuration error - return 500 response
            logger.error(
                f"💰 Payment configuration error for '{tool_name}': {e.message}"
            )
            return error_response(
                mcp_request.id,
                ErrorCodes.INTERNAL_ERROR,
                f"Payment configuration error: {e.message}",
            )
        except PaymentSettlementError as e:
            # Payment settlement error - return 500 response (shouldn't happen in verify)
            logger.error(f"💰 Payment settlement error for '{tool_name}': {e.message}")
            return error_response(
                mcp_request.id,
                ErrorCodes.INTERNAL_ERROR,
                f"Payment settlement error: {e.message}",
            )

    # =============================================================================
    # Tool Execution (PHASE 2 & 3: Execute and Settle)
    # =============================================================================
    # Payment verified (or not required) - proceed with execution
    # Settlement will happen in tool_handler.py based on execution outcome

    tool_generator = handle_tools_call(
        request=request,
        tool_name=tool_name,
        arguments=arguments,
        request_id=mcp_request.id,
        payment_handler=payment_handler,
        progress_token=progress_token,
    )

    # Streaming mode: return SSE stream
    if progress_token is not None:
        logger.debug(f"Progress token: {progress_token}")
        return StreamingResponse(
            create_sse_stream(tool_generator),
            media_type="text/event-stream",
            headers={
                "X-Request-Id": str(mcp_request.id),
                "X-Stream-Format": "sse",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    # Non-streaming mode: collect and return final result
    final_response = await collect_final_result(tool_generator)
    if final_response:
        return JSONResponse(content=final_response.to_camel_dict())

    return error_response(
        mcp_request.id, ErrorCodes.INTERNAL_ERROR, "Tool execution produced no response"
    )


# =============================================================================
# MCP Protocol Endpoints
# =============================================================================


@app.post("/mcp")
async def handle_mcp_request(request: Request):
    """
    Main MCP endpoint - handles all JSON-RPC 2.0 requests.

    Supports both streaming (SSE) and non-streaming responses.
    """
    try:
        # Parse and normalize request
        body = await request.body()

        # Log request for debugging
        logger.debug(f"Request headers: {dict(request.headers)}")
        logger.debug(f"Request body: {body.decode('utf-8')}")
        data = json.loads(body)

        # Normalize request: convert camelCase → snake_case at boundary
        # Exclude signedPayload to preserve cryptographic signature validity
        data = convert_keys_to_snake_case(
            data, exclude_paths=["params.arguments.signed_payload"]
        )

        mcp_request = JSONRPCRequest(**data)

        # Generate request ID if not provided (normalize to support both str and int per JSON-RPC spec)
        if mcp_request.id is None:
            # Generate UUID string for requests without ID
            request_id = str(uuid.uuid4())
            mcp_request.id = request_id
        else:
            # Ensure request ID is a string
            request_id = str(mcp_request.id)

        # Validate Accept header (MCP spec requirement)
        accept_header = request.headers.get("accept", "")
        if not any(
            t in accept_header for t in ["application/json", "text/event-stream", "*/*"]
        ):
            return error_response(
                mcp_request.id, ErrorCodes.INVALID_REQUEST, "Invalid Accept header"
            )

        # Log request (tools/call at INFO, others at DEBUG)
        log_level = (
            logging.INFO if mcp_request.method == "tools/call" else logging.DEBUG
        )
        logger.log(log_level, f"MCP request: {mcp_request.method}")

        # Route to appropriate handler
        method = mcp_request.method
        params = mcp_request.params or {}

        # Protocol methods
        if method == "initialize":
            return success_response(mcp_request.id, await handle_initialize(params))

        elif method == "notifications/initialized":
            handle_initialized()
            return success_response(mcp_request.id, {}, status_code=202)

        elif method == "notifications/cancelled":
            # Extract requestId and reason from params
            request_id_to_cancel = params.get("request_id") or params.get("requestId")
            reason = params.get("reason")
            response = await handle_cancelled(request_id_to_cancel, reason)

            return success_response(request_id_to_cancel, response, status_code=202)

        elif method == "ping":
            return success_response(mcp_request.id, handle_ping())

        elif method == "logging/setLevel":
            level = params.get("level", "info") if params else "info"
            return success_response(mcp_request.id, handle_set_level(level))

        # Tools
        elif method == "tools/list":
            return success_response(mcp_request.id, handle_tools_list())

        elif method == "tools/call":
            return await handle_tool_call_request(mcp_request, request)

        # Resources
        elif method == "resources/list":
            result = handle_resources_list()
            return JSONResponse(
                content=ResourceResponse.list_success(
                    mcp_request.id, result.resources
                ).to_camel_dict()
            )

        # Prompts
        elif method == "prompts/list":
            result = handle_prompts_list()
            return JSONResponse(
                content=PromptResponse.list_success(
                    mcp_request.id, result.prompts
                ).to_camel_dict()
            )

        # Unknown method
        else:
            return error_response(
                mcp_request.id,
                ErrorCodes.METHOD_NOT_FOUND,
                f"Method not found: {method}",
            )

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {e}")
        return error_response(None, ErrorCodes.PARSE_ERROR, "Parse error")

    except Exception as e:
        logger.error(f"Request handling error: {e}")
        request_id = (
            getattr(mcp_request, "id", None) if "mcp_request" in locals() else None
        )
        return error_response(request_id, ErrorCodes.INTERNAL_ERROR, str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@app.get("/")
async def root():
    """Server information endpoint"""
    return {
        "name": "Canton MCP Server",
        "version": "0.1.0",
        "mcp_endpoint": "/mcp",
        "health_endpoint": "/health",
        "transport": "streamable-http",
        "streaming_format": "sse",
        "description": "MCP server for Canton blockchain development with DAML validation",
    }


# =============================================================================
# Application Entry Point
# =============================================================================


if __name__ == "__main__":
    import uvicorn

    print("\n" + "─" * 50)
    print("  Canton MCP Server v0.1 | http://localhost:7284/mcp")
    print("─" * 50 + "\n")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=7284,
        log_level="info",
        timeout_keep_alive=30 * 60,
        timeout_graceful_shutdown=30,
    )
