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
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from canton_mcp_server import tools  # noqa: F401
from canton_mcp_server.core import get_registry
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
    handle_set_level,
    handle_tools_call,
    handle_tools_list,
)
from canton_mcp_server.handlers.resource_handler import (
    handle_resources_list,
    handle_resources_read,
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

    # Connect to facilitator WebSocket if Canton payments enabled
    if payment_handler.canton_enabled and payment_handler.ws_client:
        try:
            connected = await payment_handler.ws_client.connect()
            if connected:
                logger.info("🔌 Connected to facilitator WebSocket")
            else:
                logger.warning("⚠️  Failed to connect to facilitator WebSocket, will retry in background")
        except Exception as e:
            logger.warning(f"⚠️  Error connecting to facilitator WebSocket: {e}")

    # Start DCAP semantic_discover broadcasting
    broadcast_task = None
    from canton_mcp_server.core.dcap import is_dcap_enabled, broadcast_all_tools
    from canton_mcp_server.env import get_env, get_env_int
    
    if is_dcap_enabled():
        server_url = get_env("DCAP_SERVER_URL", "")
        if server_url:
            # Broadcast on startup
            broadcast_all_tools(server_url, payment_handler)
            
            # Start periodic broadcasting
            interval_sec = get_env_int("DCAP_DISCOVER_INTERVAL_SEC", 300)  # Default: 5 minutes
            
            async def periodic_broadcast():
                """Background task to periodically broadcast tool capabilities"""
                while True:
                    try:
                        await asyncio.sleep(interval_sec)
                        broadcast_all_tools(server_url, payment_handler)
                    except asyncio.CancelledError:
                        logger.info("📡 DCAP periodic broadcast task cancelled")
                        break
                    except Exception as e:
                        logger.error(f"⚠️ DCAP periodic broadcast failed: {e}")
            
            broadcast_task = asyncio.create_task(periodic_broadcast())
            logger.info(f"📡 DCAP semantic_discover broadcasting enabled (interval: {interval_sec}s)")
        else:
            logger.warning("⚠️ DCAP enabled but DCAP_SERVER_URL not configured - skipping semantic_discover")

    yield

    # Shutdown
    logger.info("Shutting down...")
    
    # Disconnect WebSocket on shutdown
    if payment_handler.canton_enabled and payment_handler.ws_client:
        try:
            await payment_handler.ws_client.disconnect()
        except Exception as e:
            logger.warning(f"⚠️  Error disconnecting WebSocket: {e}")
    
    # Cancel broadcast task
    if broadcast_task:
        broadcast_task.cancel()
        try:
            await broadcast_task
        except asyncio.CancelledError:
            pass


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
    Handle tools/call with payment status check.

    Payment flow:
    - PHASE -1: Require party ID (security gate)
    - PHASE 0: Check balance threshold (for Canton) - blocks if >= $2.00
    - PHASE 1: Check payment status (if enabled) - for Canton, optimistic mode
    - PHASE 2: Execute tool (in tool_handler)
    - PHASE 3: Settle payment (in tool_handler) - for EVM only
    """
    params = mcp_request.params or {}
    tool_name = params.get("name")
    arguments = params.get("arguments", {})
    progress_token = params.get("_meta", {}).get("progress_token")

    if not tool_name:
        return error_response(mcp_request.id, ErrorCodes.INVALID_PARAMS, "Missing tool name")

    # =============================================================================
    # Party ID Requirement (PHASE -1: Security Gate - Always Required)
    # =============================================================================
    # Require X-Canton-Party-ID header - no defaults, no fallbacks
    # This prevents free access and ensures payment accountability
    if payment_handler.canton_enabled:
        party_id = request.headers.get("X-Canton-Party-ID", "")
        if not party_id:
            # Try query param as fallback (for URL-based clients)
            party_id = request.query_params.get("payerParty", "")
        
        if not party_id:
            # No party ID provided - reject request immediately
            return error_response(
                mcp_request.id,
                ErrorCodes.INVALID_REQUEST,
                "X-Canton-Party-ID header required. Provide your Canton party ID to use this service.",
            )

    # =============================================================================
    # Balance Threshold Check (PHASE 0: Fast Non-blocking Gate Check for Canton)
    # =============================================================================
    # Check balance with very short timeout - if it fails/hangs, serve optimistically
    # Only block if we successfully get balance >= $2.00 within 0.5 seconds
    if payment_handler.canton_enabled and payment_handler.ws_client:
        # Use party_id extracted above (already validated)
        
        if party_id:
            try:
                # Very fast balance check - 0.5 second max, then give up
                balance = await asyncio.wait_for(
                    payment_handler.ws_client.check_balance(party_id),
                    timeout=0.5  # 500ms max - if it takes longer, serve optimistically
                )
                if balance >= 2.0:
                    # Balance threshold exceeded - deny access with detailed message
                    return error_response(
                        mcp_request.id,
                        ErrorCodes.INVALID_REQUEST,
                        f"Access denied: You owe ${balance:.2f}. Please pay your balance before continuing.",
                    )
            except (asyncio.TimeoutError, Exception):
                # Any error or timeout - serve optimistically (don't log, too noisy)
                # Balance check failed/hung - continue with optimistic serving
                pass

    # =============================================================================
    # Payment Verification (PHASE 1: Check Status)
    # =============================================================================
    # Only verify payment if payment system is enabled (USDC or Canton)
    # Settlement happens later in tool_handler.py based on execution outcome

    if payment_handler.any_payment_enabled:
        try:
            # Verify payment for this tool call
            # For Canton: checks on-chain payment status
            # For EVM: uses x402 X-PAYMENT header verification
            await payment_handler.verify_payment(request, tool_name, arguments)
        except PaymentRequiredError as e:
            # Payment required but not provided (EVM only - x402 flow)
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
            # Payment verification failed - return MCP error (not 402 for Canton)
            logger.error(
                f"💰 Payment verification failed for '{tool_name}': {e.message}"
            )
            # For Canton payments, return standard MCP error (not 402)
            if payment_handler.canton_enabled:
                # Register pending payment with facilitator (async, non-blocking)
                # party_id already validated at start of function
                try:
                    
                    logger.info(f"🔍 Payment registration check: party_id={'SET' if party_id else 'MISSING'}, has_requirements={bool(e.payment_requirements)}")
                    
                    if party_id and e.payment_requirements:
                        # Find Canton payment requirement
                        canton_req = next(
                            (req for req in e.payment_requirements 
                             if isinstance(req, dict) and req.get("scheme") == "exact-canton"),
                            None
                        )
                        if canton_req:
                            # Broadcast payment-required via WebSocket (preferred)
                            if payment_handler.ws_client:
                                price_usd = payment_handler.get_tool_price(tool_name, arguments)
                                resource_url = str(request.url)
                                payee = canton_req.get("payTo", payment_handler.canton_payee_party)
                                
                                asyncio.create_task(
                                    payment_handler.ws_client.broadcast_payment_required(
                                        party=party_id,
                                        payee=payee,
                                        amount=price_usd,
                                        resource=resource_url,
                                        tool=tool_name,
                                    )
                                )
                            
                            # Also register via HTTP (fallback/backward compatibility)
                            import httpx
                            
                            async def register_pending_payment():
                                try:
                                    async with httpx.AsyncClient(timeout=5.0) as client:
                                        await client.post(
                                            f"{payment_handler.canton_facilitator_url}/pending-payments",
                                            json={
                                                "party": party_id,
                                                "payee": canton_req.get("payTo", ""),
                                                "amount": canton_req.get("maxAmountRequired", ""),
                                                "resource": canton_req.get("resource", ""),
                                            },
                                        )
                                    logger.info(f"📝 Registered pending payment for '{tool_name}' with facilitator (HTTP)")
                                except Exception as reg_error:
                                    logger.warning(f"Failed to register pending payment via HTTP: {reg_error}")
                            
                            # Fire and forget - don't block error response
                            asyncio.create_task(register_pending_payment())
                except Exception as reg_error:
                    logger.warning(f"Failed to register pending payment: {reg_error}")
                
                return error_response(
                    mcp_request.id,
                    ErrorCodes.INVALID_REQUEST,  # Use -32600 for payment required
                    e.message,
                )
            else:
                # For EVM, return x402 response
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
        
        # Broadcast payment-required after response is generated (optimistic mode)
        # Simplified: Always broadcast if Canton enabled, use default party
        if payment_handler.canton_enabled and payment_handler.ws_client:
            from canton_mcp_server.env import get_env
            party_id = (
                request.headers.get("X-Canton-Party-ID") or
                request.query_params.get("payerParty") or
                get_env("CANTON_DEFAULT_PAYER_PARTY", "")
            )
            
            if party_id:
                price_usd = payment_handler.get_tool_price(tool_name, arguments)
                if price_usd > 0.0:  # Only broadcast for paid tools
                    resource_url = str(request.url)
                    payee = payment_handler.canton_payee_party
                    
                    # Broadcast asynchronously (fire and forget)
                    asyncio.create_task(
                        payment_handler.ws_client.broadcast_payment_required(
                            party=party_id,
                            payee=payee,
                            amount=price_usd,
                            resource=resource_url,
                            tool=tool_name,
                        )
                    )
                    logger.info(f"📤 Broadcasted payment-required: {tool_name} - ${price_usd} from {party_id}")
            else:
                logger.warning(f"⚠️  No party_id found for payment broadcast (tool: {tool_name})")
        
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
        # Broadcast payment-required after response is generated (optimistic mode)
        # For Canton payments, broadcast via WebSocket after successful tool execution
        if payment_handler.canton_enabled and payment_handler.ws_client:
            party_id = request.headers.get("X-Canton-Party-ID", "")
            if not party_id:
                party_id = request.query_params.get("payerParty", "")
            if not party_id:
                from canton_mcp_server.env import get_env
                party_id = get_env("CANTON_DEFAULT_PAYER_PARTY", "")
            
            if party_id:
                price_usd = payment_handler.get_tool_price(tool_name, arguments)
                if price_usd > 0.0:  # Only broadcast for paid tools
                    resource_url = str(request.url)
                    payee = payment_handler.canton_payee_party
                    
                    # Broadcast asynchronously (fire and forget)
                    asyncio.create_task(
                        payment_handler.ws_client.broadcast_payment_required(
                            party=party_id,
                            payee=payee,
                            amount=price_usd,
                            resource=resource_url,
                            tool=tool_name,
                        )
                    )
                    logger.debug(f"📤 Broadcasted payment-required for '{tool_name}' (non-streaming mode)")
        
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
        
        elif method == "resources/read":
            uri = params.get("uri")
            if not uri:
                return error_response(mcp_request.id, ErrorCodes.INVALID_PARAMS, "Missing resource URI")
            
            try:
                result = handle_resources_read(uri)
                return JSONResponse(
                    content=ResourceResponse.read_success(
                        mcp_request.id, result.contents
                    ).to_camel_dict()
                )
            except ValueError as e:
                return error_response(mcp_request.id, ErrorCodes.INVALID_PARAMS, str(e))
            except Exception as e:
                logger.error(f"Resource read error: {e}")
                return error_response(mcp_request.id, ErrorCodes.INTERNAL_ERROR, "Failed to read resource")

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
        "terms_endpoint": "/terms",
        "transport": "streamable-http",
        "streaming_format": "sse",
        "description": "MCP server for Canton blockchain development with DAML validation",
    }


@app.get("/terms", response_class=PlainTextResponse)
async def terms_of_service():
    """Public plain-text Terms of Service for this MCP server."""
    path = Path(__file__).parent / "terms_of_service.txt"
    if not path.exists():
        return PlainTextResponse(
            "Terms of service not available.",
            status_code=404,
        )
    return PlainTextResponse(path.read_text(encoding="utf-8"))


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
