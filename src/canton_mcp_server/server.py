#!/usr/bin/env python3
"""
Canton MCP Server - Model Context Protocol Implementation

Clean, framework-driven server with automatic tool registration,
payment integration (disabled by default), DCAP performance tracking,
and streaming support.

## AUTHENTICATION ##
Uses cryptographic challenge-response with Ed25519 signatures.

Flow:
1. POST /auth/challenge {partyId, publicKey?} → {challenge, expiresIn}
2. Client signs challenge with private key
3. POST /auth/verify {partyId, challenge, signature} → {token}
4. POST /mcp with Authorization: Bearer <token>

See:
- /home/skynet/.claude/skills/canton-mcp-auth.md (complete guide)
- /home/skynet/canton/CHALLENGE_AUTH_SETUP.md (setup instructions)
- canton_mcp_server/auth.py (implementation)
"""

import asyncio
import base64
import datetime
import json
import logging
import sys
import uuid

from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

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
from canton_mcp_server.env import get_env
from canton_mcp_server.utils.conversion import convert_keys_to_snake_case
from canton_mcp_server.auth import (
    verify_canton_transaction,
    generate_jwt_token,
    verify_jwt_token,
    generate_challenge,
    verify_challenge_signature,
    get_stored_public_key,
    AuthError,
)
from canton_mcp_server.canton_billing import (
    get_balance as get_chain_balance,
    create_charge_receipt,
    create_credit_receipt,
    verify_transfer_on_chain,
    generate_topology_for_party,
    submit_signed_topology,
    submit_topology_via_billing_portal,
    is_party_registered,
    ensure_party_registered,
    CantonBillingError,
)

# Increase recursion limit for deep async call stacks (FastAPI + httpx + asyncio).
# Default 1000 is insufficient when response.json() is called from within nested
# async middleware. 3000 frames ≈ 150KB stack, well within safe limits.
sys.setrecursionlimit(3000)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)-5s | %(message)s")
logger = logging.getLogger(__name__)

# Reduce uvicorn access log noise (only show warnings/errors)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


# Filter out successful /health and /ready probe access logs. K8s polls these
# from multiple pods several times per second, which drowns real request logs
# in Loki. We keep errors (non-2xx) visible by only filtering INFO records.
class _ProbeLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.WARNING:
            return True
        msg = record.getMessage()
        return not (" /health " in msg or " /ready " in msg)


logging.getLogger("uvicorn.access").addFilter(_ProbeLogFilter())

# Global instances
payment_handler = PaymentHandler()


# =============================================================================
# Application Lifecycle
# =============================================================================


def _warmup_semantic_search(registry):
    """Initialize semantic search eagerly at startup (runs in thread)."""
    try:
        tool = registry.get_tool("daml_reason")
        tool._ensure_semantic_search()
    except Exception as e:
        logger.warning(f"Semantic search warmup failed (non-blocking): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic for the Canton MCP server"""
    # Startup
    logger.info("Starting Canton MCP Server...")

    # Validate critical configuration before accepting requests
    from canton_mcp_server.startup_checks import validate_startup_config
    app.state.readiness = validate_startup_config()

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

    # Eagerly initialize semantic search in background (non-blocking)
    # Runs in a thread so it doesn't block the event loop or delay server startup
    async def _warmup_task():
        try:
            logger.info("🔍 Warming up semantic search (background)...")
            await asyncio.to_thread(_warmup_semantic_search, registry)
            logger.info("✅ Semantic search warmed up")
        except Exception as e:
            logger.warning(f"Semantic search warmup task failed: {e}")

    warmup_task = asyncio.create_task(_warmup_task())

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

    # Initialize FeaturedAppRight contract lookup for reward marker emission
    # Import lazily — this module imports canton_billing which pulls in httpx/orjson;
    # at Docker build time the __init__.py → server.py import chain runs during the
    # ChromaDB pre-index step where these aren't needed and may not resolve.
    try:
        from canton_mcp_server.featured_app_rewards import FEATURED_APP_REWARDS_ENABLED, init_featured_app_right
        if FEATURED_APP_REWARDS_ENABLED and payment_handler.canton_enabled:
            found = await init_featured_app_right()
            if found:
                logger.info("Featured app rewards enabled — activity markers will be emitted per tool call")
            else:
                logger.warning("Featured app rewards enabled but FeaturedAppRight not found — markers disabled")
    except Exception as e:
        logger.warning(f"FeaturedAppRight init failed (non-fatal): {e}")

    yield

    # Shutdown
    logger.info("Shutting down...")
    
    # Disconnect WebSocket on shutdown
    if payment_handler.canton_enabled and payment_handler.ws_client:
        try:
            await payment_handler.ws_client.disconnect()
        except Exception as e:
            logger.warning(f"⚠️  Error disconnecting WebSocket: {e}")
    
    # Cancel warmup task if still running
    if warmup_task and not warmup_task.done():
        warmup_task.cancel()
        try:
            await warmup_task
        except asyncio.CancelledError:
            pass

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
    # Get Authenticated Party (Already validated at main endpoint level)
    # =============================================================================
    # Party ID was extracted and validated in handle_mcp_request
    # Query parameter payerParty was already checked to match authenticated party
    party_id = getattr(request.state, "authenticated_party", "")

    # =============================================================================
    # Balance Threshold Check (PHASE 0: On-Chain Balance Check)
    # =============================================================================
    # Check balance from Canton ledger (queries ChargeReceipt + CreditReceipt contracts)
    # Block if balance is negative (user owes money)
    if payment_handler.canton_enabled and party_id:
        try:
            billing = await get_chain_balance(party_id)
            balance = billing.balance  # credits - charges
            total_calls = len(billing.charges)
            free_tier_calls = int(get_env("FREE_TIER_CALLS", "20"))

            logger.info(f"💰 On-chain balance: {balance:.2f} CC (credited: {billing.total_credited:.2f}, charged: {billing.total_charged:.2f}, calls: {total_calls}) for {party_id}")

            if total_calls < free_tier_calls:
                # Free tier - user still has free calls remaining
                remaining = free_tier_calls - total_calls
                logger.info(f"✅ Free tier: {remaining}/{free_tier_calls} free calls remaining for {party_id}")
            else:
                # Past free tier - require positive balance (allow overdraft up to threshold)
                min_balance = float(get_env("MIN_BALANCE_THRESHOLD", "-2.0"))
                if balance < min_balance:
                    # Balance too low - deny access with detailed message
                    billing_portal_url = get_env("BILLING_PORTAL_URL", "http://localhost:3050")
                    provider_wallet = get_env(
                        "CANTON_PAYEE_PARTY",
                        "app_provider_quickstart-skynet-1::1220de769fb9fa9505bb61fc6fc1e30507829f8179e140645f40e222bc7bcdac21d7"
                    )
                    owed = abs(balance) if balance < 0 else 0
                    logger.warning(f"🚫 Access denied for {party_id}: balance {balance:.2f} CC < minimum {min_balance:.2f} CC ({total_calls} calls, free tier exhausted)")

                    # Direct users to billing portal for self-service payment
                    error_msg = f"""Payment required: Your balance is {balance:.2f} CC (you owe {owed:.2f} CC). Free tier ({free_tier_calls} calls) exhausted.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOP UP YOUR ACCOUNT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
→ {billing_portal_url}/topup?party={quote(party_id, safe='')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OR TRANSFER CC DIRECTLY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Send Canton Coins to:
{provider_wallet}

Recommended amount: 5 CC

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

After top-up, return to Cursor and your tools will work again.
"""

                    return error_response(
                        mcp_request.id,
                        ErrorCodes.INVALID_REQUEST,
                        error_msg,
                    )
                else:
                    logger.info(f"✅ Paid tier: balance {balance:.2f} CC >= {min_balance:.2f} CC minimum ({total_calls} calls)")
        except CantonBillingError as e:
            logger.warning(f"❌ On-chain balance check failed for {party_id}: {e} - serving optimistically")
        except Exception as e:
            logger.warning(f"❌ Balance check error for {party_id}: {e} - serving optimistically")

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

        # Create ChargeReceipt for streaming mode
        # (recorded immediately since streaming starts now)
        receipt_skipped = False
        if payment_handler.canton_enabled and party_id:
            try:
                price_cc = payment_handler.get_tool_price(tool_name, arguments)
                # Pre-check: skip receipt if party is not registered (don't block tool)
                party_visible = is_party_registered(party_id) or await asyncio.create_task(ensure_party_registered(party_id))
                if not party_visible:
                    receipt_skipped = True
                    logger.warning(f"Skipping ChargeReceipt (streaming): party {party_id} not registered on any participant")
                else:
                    # Create ChargeReceipt for ALL calls (even free-tier $0) so the call counter tracks usage
                    async def create_charge():
                        try:
                            charge_contract_id = await create_charge_receipt(
                                user_party=party_id,
                                tool=tool_name,
                                amount=price_cc,
                                request_id=str(mcp_request.id),
                            )
                            logger.info(f"ChargeReceipt created (streaming): {charge_contract_id}")
                            # Emit FeaturedAppActivityMarker for reward tracking
                            try:
                                from canton_mcp_server.featured_app_rewards import FEATURED_APP_REWARDS_ENABLED, create_activity_marker
                                if FEATURED_APP_REWARDS_ENABLED:
                                    await create_activity_marker(request_id=str(mcp_request.id))
                            except ImportError:
                                pass
                        except Exception as e:
                            logger.critical(f"BILLING INTEGRITY: Failed to create ChargeReceipt for {party_id}/{tool_name}/{price_cc}CC: {e}")
                    asyncio.create_task(create_charge())
                    logger.info(f"Creating ChargeReceipt (streaming): {tool_name} - {price_cc} CC from {party_id}")
            except Exception as e:
                logger.error(f"Failed to create ChargeReceipt: {e}")

        # Broadcast payment-required after response is generated (optimistic mode)
        # Reuse party_id from security gate (no env fallback)
        if payment_handler.canton_enabled and payment_handler.ws_client and party_id:
            price_usd = payment_handler.get_tool_price(tool_name, arguments)
            if price_usd > 0.0:  # Only broadcast for paid tools
                resource_url = str(request.url)
                payee = payment_handler.canton_payee_party
                asyncio.create_task(
                    payment_handler.ws_client.broadcast_payment_required(
                        party=party_id,
                        payee=payee,
                        amount=price_usd,
                        resource=resource_url,
                        tool=tool_name,
                    )
                )
                logger.info(f"Broadcasted payment-required: {tool_name} - ${price_usd} from {party_id}")

        response_headers = {
            "X-Request-Id": str(mcp_request.id),
            "X-Stream-Format": "sse",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
        if receipt_skipped:
            response_headers["X-Registration-Hint"] = "party-not-registered"

        return StreamingResponse(
            create_sse_stream(tool_generator),
            media_type="text/event-stream",
            headers=response_headers,
        )

    # Non-streaming mode: collect and return final result
    final_response = await collect_final_result(tool_generator)
    if final_response:
        # Create ChargeReceipt on Canton ledger
        receipt_skipped_nonstream = False
        if payment_handler.canton_enabled and party_id:
            try:
                price_cc = payment_handler.get_tool_price(tool_name, arguments)
                # Pre-check: skip receipt if party is not registered (don't block tool)
                party_visible = is_party_registered(party_id) or await asyncio.create_task(ensure_party_registered(party_id))
                if not party_visible:
                    receipt_skipped_nonstream = True
                    logger.warning(f"Skipping ChargeReceipt: party {party_id} not registered on any participant")
                else:
                    # Create ChargeReceipt for ALL calls (even free-tier $0) so the call counter tracks usage
                    charge_contract_id = await create_charge_receipt(
                        user_party=party_id,
                        tool=tool_name,
                        amount=price_cc,
                        request_id=str(mcp_request.id),
                    )
                    logger.info(f"ChargeReceipt created on-chain: {tool_name} - {price_cc} CC from {party_id} (contract: {charge_contract_id})")
                    # Emit FeaturedAppActivityMarker for reward tracking (fire-and-forget)
                    try:
                        from canton_mcp_server.featured_app_rewards import FEATURED_APP_REWARDS_ENABLED, create_activity_marker
                        if FEATURED_APP_REWARDS_ENABLED:
                            asyncio.create_task(create_activity_marker(request_id=str(mcp_request.id)))
                    except ImportError:
                        pass
            except Exception as e:
                logger.critical(f"BILLING INTEGRITY: Failed to create ChargeReceipt for {party_id}/{tool_name}/{price_cc}CC: {e}")

        # Broadcast payment-required after response is generated (optimistic mode)
        # Reuse party_id from security gate (no env fallback)
        if payment_handler.canton_enabled and payment_handler.ws_client and party_id:
            price_usd = payment_handler.get_tool_price(tool_name, arguments)
            if price_usd > 0.0:  # Only broadcast for paid tools
                resource_url = str(request.url)
                payee = payment_handler.canton_payee_party
                asyncio.create_task(
                    payment_handler.ws_client.broadcast_payment_required(
                        party=party_id,
                        payee=payee,
                        amount=price_usd,
                        resource=resource_url,
                        tool=tool_name,
                    )
                )
                logger.debug(f"Broadcasted payment-required for '{tool_name}' (non-streaming mode)")

        response_dict = final_response.to_camel_dict()
        if receipt_skipped_nonstream:
            response_dict["_meta"] = response_dict.get("_meta", {})
            response_dict["_meta"]["registrationHint"] = "party-not-registered"
        return JSONResponse(content=response_dict)

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

        # =============================================================================
        # JWT Authentication & Party Validation (Applies to all authenticated methods)
        # =============================================================================
        # Methods that bypass authentication (public protocol methods)
        PUBLIC_METHODS = {"initialize", "notifications/initialized", "ping"}

        # If Canton payment is enabled and this isn't a public method, require auth
        if payment_handler.canton_enabled and mcp_request.method not in PUBLIC_METHODS:
            auth_header = request.headers.get("Authorization")

            if not auth_header or not auth_header.startswith("Bearer "):
                billing_portal_url = get_env("BILLING_PORTAL_URL", "http://localhost:3050")
                return error_response(
                    mcp_request.id,
                    ErrorCodes.INVALID_REQUEST,
                    "Authentication required.\n\n"
                    f"Visit {billing_portal_url}/mcp-setup to set up your Cursor MCP connection.\n\n"
                    "The setup page will help you:\n"
                    "- Generate your Canton party key\n"
                    "- Authenticate with the MCP server\n"
                    "- Get your mcp.json configuration",
                )

            token = auth_header.replace("Bearer ", "")

            try:
                claims = verify_jwt_token(token)
                party_id = claims["sub"]
                logger.info(f"🔐 Authenticated request from party: {party_id}")

                # SECURITY: Validate that payerParty parameter matches authenticated party
                # This prevents authenticated user from billing a different party's account
                query_party_id = request.query_params.get("payerParty", "")
                if query_party_id and query_party_id != party_id:
                    logger.error(
                        f"🚨 SECURITY: Party ID mismatch! "
                        f"Authenticated as '{party_id}' but trying to bill '{query_party_id}'"
                    )
                    return error_response(
                        mcp_request.id,
                        ErrorCodes.INVALID_REQUEST,
                        f"Security violation: payerParty parameter ({query_party_id}) must match authenticated party ({party_id})",
                    )

                # Store authenticated party in request state for payment_handler to use
                # This ensures payment_handler always uses the authenticated party
                request.state.authenticated_party = party_id

            except AuthError as e:
                return error_response(
                    mcp_request.id,
                    ErrorCodes.INVALID_REQUEST,
                    f"Authentication failed: {str(e)}",
                )

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
    """Liveness probe — is the process alive?"""
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@app.get("/ready")
async def readiness_check():
    """Readiness probe — are critical dependencies functional?"""
    checks = {}
    all_ok = True

    # Check 1: ChromaDB
    try:
        registry = get_registry()
        tool = registry.get_tool("daml_reason")
        if tool and tool._semantic_search is not None:
            stats = tool._semantic_search.get_stats()
            count = stats.get("indexed_count", 0)
            checks["chromadb"] = {"status": "ok", "indexed_count": count}
            if count == 0:
                checks["chromadb"]["status"] = "degraded"
                all_ok = False
        else:
            checks["chromadb"] = {"status": "initializing"}
    except Exception as e:
        checks["chromadb"] = {"status": "error", "error": str(e)[:200]}
        all_ok = False

    # Check 2: LLM model (validated at startup)
    readiness = getattr(app.state, "readiness", {})
    if readiness.get("llm_model_valid") is not None:
        checks["llm"] = {
            "status": "ok" if readiness["llm_model_valid"] else "error",
            "model": readiness.get("llm_model_name", "unknown"),
        }
        if not readiness["llm_model_valid"]:
            all_ok = False

    status_code = 200 if all_ok else 503
    return JSONResponse(
        content={
            "status": "ready" if all_ok else "not_ready",
            "checks": checks,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
        status_code=status_code,
    )


# Topology transaction store: {party_id: [{topology_tx, hash}, ...]}
_pending_topology: dict = {}

@app.post("/auth/challenge")
async def request_auth_challenge(request: Request):
    """
    Request an authentication challenge (RECOMMENDED METHOD).

    Request: {
        "partyId": "alice::1220...",
        "publicKey": "base64-encoded-public-key" (optional, required for first auth)
    }
    Response: {
        "challenge": "base64-encoded-nonce",
        "expiresIn": 300,
        "requiresPublicKey": false,
        "topologyHashes": ["hash1", ...] (if party needs on-chain registration)
    }
    """
    try:
        body = await request.json()
        party_id = body.get("partyId")
        public_key = body.get("publicKey")

        if not party_id:
            return JSONResponse(
                status_code=400, content={"error": "partyId is required"}
            )

        # Import public key store check
        from canton_mcp_server.auth import _public_key_store

        # Check if we have a public key for this party
        has_public_key = party_id in _public_key_store

        if not has_public_key and not public_key:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Public key required for first-time authentication",
                    "requiresPublicKey": True,
                    "message": "Provide your public key in the 'publicKey' field (base64-encoded)",
                },
            )

        try:
            challenge = generate_challenge(party_id, public_key)

            response_data = {
                "challenge": challenge,
                "expiresIn": 300,
                "requiresPublicKey": False,
                "message": "Sign this challenge with your Canton party's private key",
            }

            # If Canton billing enabled, generate topology for party registration
            if payment_handler.canton_enabled and not is_party_registered(party_id):
                pk_b64 = public_key or (
                    base64.b64encode(_public_key_store[party_id]).decode()
                    if party_id in _public_key_store else None
                )
                if pk_b64:
                    try:
                        result = await generate_topology_for_party(party_id, pk_b64)
                        if result:
                            # Store full result for submission during verify
                            _pending_topology[party_id] = result
                            # Extract topology_txs from dict (gRPC flow) or use as list (Validator flow)
                            if isinstance(result, dict):
                                topology_txs = result["topology_txs"]
                            else:
                                topology_txs = result
                            # Return hashes for client to sign
                            response_data["topologyHashes"] = [
                                tx["hash"] for tx in topology_txs
                            ]
                            response_data["message"] = (
                                "Sign this challenge AND each topologyHash with your private key"
                            )
                            logger.info(
                                f"Party {party_id} needs registration: "
                                f"{len(topology_txs)} topology txs to sign"
                            )
                    except Exception as e:
                        logger.warning(f"Topology generation failed: {e}")
                        response_data["topologyError"] = str(e)

            return JSONResponse(content=response_data)
        except AuthError as e:
            return JSONResponse(status_code=400, content={"error": str(e)})

    except Exception as e:
        logger.error(f"Challenge generation error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/auth/verify")
async def verify_auth_signature(request: Request):
    """
    Verify signed challenge and issue JWT token (RECOMMENDED METHOD).

    Request: {
        "partyId": "alice::1220...",
        "challenge": "base64-challenge",
        "signature": "base64-signature",
        "topologySignatures": ["hex-sig1", ...] (optional, for party registration)
    }
    Response: {
        "token": "eyJhbGc...",
        "partyRegistered": true/false (if topology was submitted)
    }
    """
    try:
        body = await request.json()
        party_id = body.get("partyId")
        challenge = body.get("challenge")
        signature = body.get("signature")
        topology_signatures = body.get("topologySignatures", [])

        if not all([party_id, challenge, signature]):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "partyId, challenge, and signature are required"
                },
            )

        # Verify signature
        try:
            await verify_challenge_signature(party_id, challenge, signature)
        except AuthError as e:
            return JSONResponse(
                status_code=401,
                content={"error": f"Authentication failed: {str(e)}"},
            )

        # Submit signed topology transactions if provided
        party_registered = False
        registration_needed = False

        if (
            payment_handler.canton_enabled
            and topology_signatures
            and party_id in _pending_topology
        ):
            try:
                pending = _pending_topology.pop(party_id)
                public_key_bytes = get_stored_public_key(party_id)
                public_key_b64 = base64.b64encode(public_key_bytes).decode()

                if isinstance(pending, dict):
                    # Canton 3.4 gRPC flow via billing portal
                    topology_txs = pending["topology_txs"]
                    key_fingerprint = pending.get("key_fingerprint", "")
                    if len(topology_signatures) == len(topology_txs):
                        signed_txs = [
                            {
                                "topology_tx": tx["topology_tx"],
                                "signed_hash": sig,
                            }
                            for tx, sig in zip(topology_txs, topology_signatures)
                        ]
                        # Use the hash from the first tx as originalHash
                        original_hash = topology_txs[0].get("hash", "") if topology_txs else ""
                        party_registered = await submit_topology_via_billing_portal(
                            party_id, public_key_b64, signed_txs,
                            key_fingerprint, original_hash,
                        )
                        if party_registered:
                            logger.info(f"Party registered on-chain via billing portal: {party_id}")
                    else:
                        logger.warning(
                            f"Topology signature count mismatch: "
                            f"expected {len(topology_txs)}, got {len(topology_signatures)}"
                        )
                else:
                    # Validator API flow (list of topology txs)
                    topology_txs = pending
                    if len(topology_signatures) == len(topology_txs):
                        signed_txs = [
                            {
                                "topology_tx": tx["topology_tx"],
                                "signed_hash": sig,
                            }
                            for tx, sig in zip(topology_txs, topology_signatures)
                        ]
                        party_registered = await submit_signed_topology(
                            party_id, public_key_b64, signed_txs
                        )
                        if party_registered:
                            logger.info(f"Party registered on-chain: {party_id}")
                    else:
                        logger.warning(
                            f"Topology signature count mismatch: "
                            f"expected {len(topology_txs)}, got {len(topology_signatures)}"
                        )
            except Exception as e:
                logger.warning(f"Party registration failed (non-blocking): {e}")

        # Check registration status: if party is not registered and didn't just
        # register, check if it's visible to the ledger (handles parties on other
        # participants like mainnet-beta). If truly unregistered, tell the client.
        if payment_handler.canton_enabled and not party_registered:
            if not is_party_registered(party_id):
                # Check via ledger probe (catches parties on other participants)
                ledger_visible = await ensure_party_registered(party_id)
                if not ledger_visible:
                    registration_needed = True
                    logger.warning(f"Party {party_id} not registered on any participant")

        # If registration is needed and the client didn't provide topology
        # signatures, return the topology hashes so they can sign and retry
        if registration_needed and not topology_signatures:
            # Re-generate topology hashes for the client to sign
            from canton_mcp_server.auth import _public_key_store
            pk_b64 = (
                base64.b64encode(_public_key_store[party_id]).decode()
                if party_id in _public_key_store else None
            )
            topology_hashes = []
            if pk_b64:
                try:
                    result = await generate_topology_for_party(party_id, pk_b64)
                    if result:
                        _pending_topology[party_id] = result
                        if isinstance(result, dict):
                            topology_hashes = [tx["hash"] for tx in result["topology_txs"]]
                        else:
                            topology_hashes = [tx["hash"] for tx in result]
                except Exception as e:
                    logger.warning(f"Topology generation for registration failed: {e}")

            if topology_hashes:
                logger.info(
                    f"Party {party_id} needs registration — returning topology hashes "
                    f"instead of JWT ({len(topology_hashes)} txs to sign)"
                )
                return JSONResponse(content={
                    "registrationRequired": True,
                    "topologyHashes": topology_hashes,
                    "message": "Party not registered. Sign each topologyHash with your private key "
                               "and retry /auth/verify with topologySignatures.",
                })
            else:
                # Could not generate topology — block JWT issuance
                logger.warning(
                    f"Party {party_id} not registered and topology generation failed — "
                    f"cannot issue JWT"
                )
                return JSONResponse(content={
                    "registrationRequired": True,
                    "topologyHashes": [],
                    "message": "Party not registered and topology generation failed. "
                               "Re-authenticate via /auth/challenge with your publicKey.",
                })

        # If topology signatures were provided but registration failed, block JWT
        if (
            payment_handler.canton_enabled
            and topology_signatures
            and not party_registered
            and not is_party_registered(party_id)
        ):
            logger.warning(
                f"Party {party_id} topology submission failed — cannot issue JWT"
            )
            return JSONResponse(content={
                "registrationRequired": True,
                "topologyHashes": [],
                "message": "Party registration failed. Please retry /auth/challenge to get fresh topology hashes.",
            })

        # Generate JWT token
        token = generate_jwt_token(party_id, f"challenge-{challenge[:16]}")

        logger.info(
            f"✅ Authentication successful for {party_id} via signature verification"
        )

        response_data = {"token": token}
        if topology_signatures:
            response_data["partyRegistered"] = party_registered

        return JSONResponse(content=response_data)

    except Exception as e:
        logger.error(f"Authentication error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/auth/verify-payment")
async def authenticate_with_payment(request: Request):
    """
    Authenticate using a Canton transaction ID (DEPRECATED).

    ⚠️  DEPRECATED: Use /auth/challenge + /auth/verify instead.
    This method is insecure as transaction IDs are public on the ledger.

    Request: {
        "transactionId": "canton-transaction-id",
        "partyId": "user::1220..."
    }
    Response: {
        "token": "eyJhbGc...",
        "warning": "This authentication method is deprecated..."
    }
    """
    try:
        body = await request.json()
        transaction_id = body.get("transactionId")
        party_id = body.get("partyId")

        if not transaction_id or not party_id:
            return JSONResponse(
                status_code=400,
                content={"error": "transactionId and partyId are required"},
            )

        # Verify transaction exists on Canton ledger and was signed by party
        facilitator_url = get_env(
            "CANTON_FACILITATOR_URL", "http://localhost:3000"
        )

        try:
            await verify_canton_transaction(
                transaction_id, party_id, facilitator_url
            )
        except AuthError as e:
            return JSONResponse(
                status_code=401,
                content={"error": f"Authentication failed: {str(e)}"},
            )

        # Generate JWT token
        token = generate_jwt_token(party_id, f"transaction-{transaction_id}")

        logger.warning(
            f"⚠️  DEPRECATED: Transaction-based auth used for {party_id}. "
            "Recommend using /auth/challenge + /auth/verify instead."
        )

        return JSONResponse(
            content={
                "token": token,
                "warning": "This authentication method is deprecated and will be removed. "
                "Please migrate to /auth/challenge + /auth/verify for secure authentication.",
            }
        )

    except Exception as e:
        logger.error(f"Authentication error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})




@app.post("/billing/credit")
async def create_billing_credit(request: Request):
    """
    Create a CreditReceipt on-chain when user tops up.

    SECURITY: Requires either:
    1. Valid BILLING_API_KEY header (for trusted callers like billing portal)
    2. Valid on-chain transfer verification (transferId must exist and match)

    Request: {
        "userParty": "user::1220...",
        "amount": 5.0,
        "transferId": "canton-transaction-id",
        "description": "Optional description"
    }
    Response: {
        "success": true,
        "contractId": "00...",
        "balance": 3.0
    }
    """
    import hmac

    try:
        body = await request.json()
        user_party = body.get("userParty") or body.get("user_party")
        amount = body.get("amount")
        transfer_id = body.get("transferId") or body.get("transfer_id")
        description = body.get("description")

        if not user_party:
            return JSONResponse(
                status_code=400,
                content={"error": "userParty is required"}
            )

        if amount is None or amount <= 0:
            return JSONResponse(
                status_code=400,
                content={"error": "amount must be a positive number"}
            )

        if not transfer_id:
            return JSONResponse(
                status_code=400,
                content={"error": "transferId is required"}
            )

        # =============================================================================
        # SECURITY: Two authentication methods
        # =============================================================================
        api_key = request.headers.get("X-Billing-API-Key", "")
        expected_key = get_env("BILLING_API_KEY", "")
        authorized = False

        # Debug: log API key auth state (redacted)
        logger.info(
            f"💳 Credit auth check: api_key_present={bool(api_key)} "
            f"(len={len(api_key)}), expected_key_present={bool(expected_key)} "
            f"(len={len(expected_key)})"
        )

        # Option 1: Valid API key (for billing portal)
        if expected_key and api_key:
            if hmac.compare_digest(api_key, expected_key):
                authorized = True
                logger.info(f"💳 Credit request authorized via API key for {user_party}")
            else:
                logger.warning(
                    f"💳 API key mismatch: received_prefix={api_key[:8]}... "
                    f"expected_prefix={expected_key[:8]}..."
                )

        # Option 2: Verify transfer exists on Canton ledger
        if not authorized:
            logger.info(f"🔍 Verifying transfer on-chain: {transfer_id}")
            try:
                verification = await verify_transfer_on_chain(
                    transfer_id=transfer_id,
                    user_party=user_party,
                    expected_amount=float(amount),
                )

                if verification.get("verified"):
                    authorized = True
                    logger.info(f"💳 Credit request authorized via on-chain verification for {user_party}")
                else:
                    error_msg = verification.get("error", "Transfer verification failed")
                    logger.warning(f"🚫 Transfer verification failed: {error_msg}")
                    return JSONResponse(
                        status_code=401,
                        content={
                            "error": "Unauthorized: Transfer verification failed",
                            "details": error_msg,
                            "transferId": transfer_id,
                        }
                    )
            except CantonBillingError as e:
                logger.warning(f"🚫 Transfer verification error: {e}")
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": "Unauthorized: Unable to verify transfer",
                        "details": str(e),
                        "transferId": transfer_id,
                    }
                )

        if not authorized:
            logger.warning(f"🚫 Unauthorized credit attempt for {user_party}")
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized: Invalid API key or unverified transfer",
                    "hint": "Provide valid X-Billing-API-Key header or a verifiable transferId",
                }
            )

        # =============================================================================
        # Create CreditReceipt (includes duplicate prevention)
        # =============================================================================
        contract_id = await create_credit_receipt(
            user_party=user_party,
            amount=float(amount),
            transfer_id=transfer_id,
            description=description or "Top-up via billing portal",
        )

        # Get updated balance
        billing = await get_chain_balance(user_party)

        logger.info(f"💳 CreditReceipt created: {contract_id} for {user_party} - {amount} CC")

        return JSONResponse(content={
            "success": True,
            "contractId": contract_id,
            "amount": amount,
            "balance": billing.balance,
            "totalCredited": billing.total_credited,
            "totalCharged": billing.total_charged,
        })

    except CantonBillingError as e:
        logger.error(f"Failed to create credit: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to create credit receipt: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Credit creation error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@app.get("/billing/balance/{party_id:path}")
async def get_billing_balance(party_id: str):
    """
    Get the current balance for a user.

    Response: {
        "balance": 3.0,
        "totalCredited": 5.0,
        "totalCharged": 2.0,
        "chargeCount": 10,
        "creditCount": 1
    }
    """
    try:
        billing = await get_chain_balance(party_id)

        return JSONResponse(content={
            "balance": billing.balance,
            "totalCredited": billing.total_credited,
            "totalCharged": billing.total_charged,
            "chargeCount": len(billing.charges),
            "creditCount": len(billing.credits),
        })

    except CantonBillingError as e:
        logger.error(f"Failed to get balance: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to get balance: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Balance query error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


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
        "description": "MCP server for Canton blockchain development with DAML validation and on-chain billing",
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

    mcp_server_url = get_env("MCP_SERVER_URL", "http://localhost:7284")
    print("\n" + "─" * 50)
    print(f"  Canton MCP Server v0.1 | {mcp_server_url}/mcp")
    print("─" * 50 + "\n")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=7284,
        log_level="info",
        timeout_keep_alive=30 * 60,
        timeout_graceful_shutdown=30,
    )
