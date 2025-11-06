"""
x402 Payment Handler for MCP Server

Handles payment verification, settlement, and internal API key bypass.
"""

import asyncio
import base64
import hmac
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, cast

from fastapi import Request
from x402.common import (
    find_matching_payment_requirements,
    process_price_to_atomic_amount,
)
from x402.encoding import safe_base64_decode
from x402.facilitator import FacilitatorClient
from x402.types import PaymentPayload, PaymentRequirements, SupportedNetworks

from . import tools  # noqa: F401 - Import to trigger tool registration
from .core import get_registry
from .env import get_env, get_env_bool

logger = logging.getLogger(__name__)


# =============================================================================
# Payment Error Types
# =============================================================================


@dataclass
class PaymentErrorData:
    """Structured error data for payment errors"""

    message: str
    status_code: int
    payment_requirements: Optional[List[Dict[str, Any]]] = None
    error_code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class PaymentError(Exception):
    """Base exception for payment-related errors with structured data"""

    def __init__(self, error_data: PaymentErrorData):
        self.error_data = error_data
        super().__init__(error_data.message)

    @property
    def message(self) -> str:
        return self.error_data.message

    @property
    def status_code(self) -> int:
        return self.error_data.status_code

    @property
    def payment_requirements(self) -> Optional[List[Dict[str, Any]]]:
        return self.error_data.payment_requirements

    @property
    def error_code(self) -> Optional[str]:
        return self.error_data.error_code

    @property
    def details(self) -> Optional[Dict[str, Any]]:
        return self.error_data.details

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for JSON serialization"""
        return {
            "message": self.message,
            "status_code": self.status_code,
            "error_code": self.error_code,
            "payment_requirements": self.payment_requirements,
            "details": self.details,
        }


class PaymentRequiredError(PaymentError):
    """Raised when payment is required but not provided"""

    def __init__(self, message: str, payment_requirements: list):
        # Handle mixed list: PaymentRequirements objects and dicts (Canton)
        serialized_reqs = []
        for req in payment_requirements:
            if isinstance(req, dict):
                serialized_reqs.append(req)
            else:
                serialized_reqs.append(req.model_dump(by_alias=True))
        
        error_data = PaymentErrorData(
            message=message,
            status_code=402,
            payment_requirements=serialized_reqs,
            error_code="PAYMENT_REQUIRED",
        )
        super().__init__(error_data)


class PaymentVerificationError(PaymentError):
    """Raised when payment verification fails"""

    def __init__(self, message: str, payment_requirements: list):
        # Handle mixed list: PaymentRequirements objects and dicts (Canton)
        serialized_reqs = []
        for req in payment_requirements:
            if isinstance(req, dict):
                serialized_reqs.append(req)
            else:
                serialized_reqs.append(req.model_dump(by_alias=True))
        
        error_data = PaymentErrorData(
            message=message,
            status_code=402,
            payment_requirements=serialized_reqs,
            error_code="PAYMENT_VERIFICATION_FAILED",
        )
        super().__init__(error_data)


class PaymentConfigurationError(PaymentError):
    """Raised when payment configuration is invalid"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        error_data = PaymentErrorData(
            message=message,
            status_code=500,
            error_code="PAYMENT_CONFIGURATION_ERROR",
            details=details,
        )
        super().__init__(error_data)


class PaymentSettlementError(PaymentError):
    """Raised when payment settlement fails"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        error_data = PaymentErrorData(
            message=message,
            status_code=500,
            error_code="PAYMENT_SETTLEMENT_FAILED",
            details=details,
        )
        super().__init__(error_data)


# =============================================================================
# Payment Handler
# =============================================================================


class PaymentHandler:
    """Handles x402 payment verification and settlement"""

    def __init__(self):
        """Initialize payment handler with configuration"""
        # USDC/EVM payment configuration
        self.enabled = get_env_bool("X402_ENABLED", False)
        self.wallet_address = get_env("X402_WALLET_ADDRESS", "")
        self.network = get_env("X402_NETWORK", "base-sepolia")
        self.internal_api_key = get_env("X402_INTERNAL_API_KEY", "")

        # Canton payment configuration
        self.canton_enabled = get_env_bool("CANTON_ENABLED", False)
        self.canton_facilitator_url = get_env("CANTON_FACILITATOR_URL", "http://localhost:3000")
        self.canton_payee_party = get_env("CANTON_PAYEE_PARTY", "")
        self.canton_network = get_env("CANTON_NETWORK", "canton-local")

        # Validate configurations if enabled
        if self.enabled:
            self._validate_configuration()
            logger.info(f"🔐 X402 payment protection enabled (network: {self.network})")
            logger.info(f"💰 Dynamic pricing enabled - wallet: {self.wallet_address}")
        
        if self.canton_enabled:
            self._validate_canton_configuration()
            logger.info(f"🔐 Canton payment enabled (network: {self.canton_network})")
            logger.info(f"💰 Canton payee party: {self.canton_payee_party}")

    def _validate_configuration(self):
        """Validate required x402 configuration"""
        if not self.wallet_address:
            raise ValueError(
                "X402_ENABLED=true but X402_WALLET_ADDRESS not configured. "
                "Please set X402_WALLET_ADDRESS in .env.canton or disable x402 with X402_ENABLED=false"
            )
        if not self.network:
            raise ValueError(
                "X402_ENABLED=true but X402_NETWORK not configured. "
                "Please set X402_NETWORK (e.g., 'base', 'base-sepolia') in .env.canton"
            )

    def _validate_canton_configuration(self):
        """Validate required Canton payment configuration"""
        if not self.canton_payee_party:
            raise ValueError(
                "CANTON_ENABLED=true but CANTON_PAYEE_PARTY not configured. "
                "Please set CANTON_PAYEE_PARTY in .env.canton or disable Canton with CANTON_ENABLED=false"
            )
        if not self.canton_facilitator_url:
            raise ValueError(
                "CANTON_ENABLED=true but CANTON_FACILITATOR_URL not configured. "
                "Please set CANTON_FACILITATOR_URL in .env.canton"
            )
        if not self.canton_network:
            raise ValueError(
                "CANTON_ENABLED=true but CANTON_NETWORK not configured. "
                "Please set CANTON_NETWORK (e.g., 'canton-local', 'canton-testnet') in .env.canton"
            )

    def get_tool_price(self, tool_name: str, arguments: dict) -> float:
        """
        Get price for a tool call by looking it up in the tool registry.

        Uses Tool.pricing as the single source of truth for all pricing.

        Args:
            tool_name: Name of the tool being called
            arguments: Tool arguments (used for dynamic pricing)

        Returns:
            Price in USD

        Example:
            >>> handler.get_tool_price("get_all_strategies", {})
            0.0
            >>> handler.get_tool_price("run_backtest", {...})
            0.0475
        """
        try:
            registry = get_registry()
            tool = registry.get_tool(tool_name)

            # Validate arguments with tool's params model
            validated_params = tool.params_model(**arguments)

            # Use Tool.pricing.calculate_price() - single source of truth!
            calculated_price = tool.pricing.calculate_price(validated_params)

            logger.debug(f"Tool '{tool_name}' price: ${calculated_price:.4f}")
            return calculated_price

        except Exception as e:
            # Tool not found in registry or validation failed
            logger.warning(
                f"Could not get price for '{tool_name}': {e}, defaulting to $0.01"
            )
            return 0.01

    def _check_internal_api_key(self, request: Request) -> bool:
        """
        Check if request has valid internal API key for payment bypass.

        Args:
            request: FastAPI request object

        Returns:
            True if valid internal key present, False otherwise
        """
        internal_key = request.headers.get("X-Internal-API-Key", "")
        if (
            internal_key
            and self.internal_api_key
            and len(self.internal_api_key) > 0
            and hmac.compare_digest(internal_key, self.internal_api_key)
        ):
            return True
        return False

    def _build_payment_requirements(
        self, request: Request, tool_name: str, arguments: dict
    ) -> list[PaymentRequirements]:
        """
        Build payment requirements for a tool call.
        Returns list with USDC and/or Canton payment options based on configuration.

        Args:
            request: FastAPI request object
            tool_name: Name of the tool being called
            arguments: Tool arguments

        Returns:
            List of payment requirements (USDC and/or Canton options)

        Raises:
            PaymentConfigurationError: If price configuration fails
        """
        # Calculate price for this specific tool
        price_usd = self.get_tool_price(tool_name, arguments)
        resource_url = str(request.url)
        requirements = []

        # Option 1: USDC on Base Sepolia (EVM)
        if self.enabled and self.wallet_address:
            try:
                max_amount_required, asset_address, eip712_domain = (
                    process_price_to_atomic_amount(f"${price_usd}", self.network)
                )
                requirements.append(
                    PaymentRequirements(
                        scheme="exact",
                        network=cast(SupportedNetworks, self.network),
                        asset=asset_address,
                        max_amount_required=max_amount_required,
                        resource=resource_url,
                        description=f"MCP Tool: {tool_name} (USDC)",
                        mime_type="application/json",
                        pay_to=self.wallet_address,
                        max_timeout_seconds=60,
                        output_schema={
                            "input": {"type": "http", "method": "POST", "discoverable": True},
                            "output": None,
                        },
                        extra=eip712_domain,
                    )
                )
            except Exception as e:
                logger.error(f"Error building USDC payment requirements for {tool_name}: {e}")
                raise PaymentConfigurationError(f"USDC price configuration error: {str(e)}")

        # Option 2: Canton Coins on Canton Network
        if self.canton_enabled and self.canton_payee_party:
            try:
                # Direct USD-to-CC mapping (1:1 for ad-hoc stability)
                # Note: Use dict instead of PaymentRequirements to avoid EVM-specific validation
                canton_requirement = {
                    "scheme": "exact-canton",
                    "network": self.canton_network,
                    "asset": "CC",  # Canton Coin
                    "maxAmountRequired": str(price_usd),
                    "resource": resource_url,
                    "description": f"MCP Tool: {tool_name} (Canton Coin)",
                    "mimeType": "application/json",
                    "payTo": self.canton_payee_party,
                    "maxTimeoutSeconds": 60,
                    "outputSchema": {
                        "input": {"type": "http", "method": "POST", "discoverable": True},
                        "output": None,
                    },
                    "extra": {
                        "facilitatorUrl": self.canton_facilitator_url,
                        "paymentType": "canton-daml-contract",
                    },
                }
                requirements.append(canton_requirement)
            except Exception as e:
                logger.error(f"Error building Canton payment requirements for {tool_name}: {e}")
                raise PaymentConfigurationError(f"Canton price configuration error: {str(e)}")

        return requirements

    async def verify_payment(
        self, request: Request, tool_name: str, arguments: dict
    ) -> None:
        """
        Verify x402 payment for MCP tool call.
        Routes to appropriate facilitator based on payment scheme.

        Args:
            request: FastAPI request object
            tool_name: Name of the tool being called
            arguments: Tool arguments

        Raises:
            PaymentRequiredError: If payment is required but not provided
            PaymentVerificationError: If payment verification fails
            PaymentConfigurationError: If payment configuration is invalid
        """
        # Skip if no payment methods enabled
        if not self.enabled and not self.canton_enabled:
            return

        # Check for internal API key bypass
        if self._check_internal_api_key(request):
            logger.debug(
                f"🔓 Internal API key verified - bypassing payment for '{tool_name}'"
            )
            return

        # Check if tool price is $0 - skip payment for free tools
        price_usd = self.get_tool_price(tool_name, arguments)
        if price_usd == 0.0:
            logger.debug(f"💸 Tool '{tool_name}' is free ($0.00) - skipping payment")
            return

        # Build payment requirements (may include both USDC and Canton options)
        payment_requirements = self._build_payment_requirements(
            request, tool_name, arguments
        )

        # Check for payment header
        payment_header = request.headers.get("X-PAYMENT", "")

        if not payment_header:
            logger.info(
                f"💰 Payment required for '{tool_name}': ${self.get_tool_price(tool_name, arguments):.4f}"
            )
            raise PaymentRequiredError(
                "No X-PAYMENT header provided", payment_requirements
            )

        # Parse payment payload - check scheme first to avoid EVM validation on Canton payments
        try:
            payment_dict = json.loads(safe_base64_decode(payment_header))
            payment_scheme = payment_dict.get("scheme", "")
            
            if payment_scheme == "exact-canton":
                # Canton payment - don't parse with PaymentPayload (EVM-specific model)
                # Pass raw dict to Canton handler
                await self._verify_canton_payment(request, payment_dict, payment_requirements, tool_name, arguments)
            else:
                # EVM payment - parse with PaymentPayload model
                payment = PaymentPayload(**payment_dict)
                await self._verify_evm_payment(request, payment, payment_requirements, tool_name, arguments)
                
        except Exception as e:
            logger.warning(f"Invalid payment header: {e}")
            raise PaymentVerificationError(
                "Invalid payment header format", payment_requirements
            )

    async def _verify_canton_payment(
        self, request: Request, payment_dict: dict, payment_requirements: list,
        tool_name: str, arguments: dict
    ) -> None:
        """Verify Canton payment via Canton facilitator
        
        Args:
            request: FastAPI request
            payment_dict: Raw payment dictionary (not PaymentPayload model)
            payment_requirements: List of payment requirements
            tool_name: Tool name
            arguments: Tool arguments
        """
        import httpx
        
        # Find matching Canton requirements (dict format, not PaymentRequirements)
        canton_reqs = [r for r in payment_requirements if (isinstance(r, dict) and r.get("scheme") == "exact-canton")]
        if not canton_reqs:
            raise PaymentVerificationError(
                "No Canton payment option available", payment_requirements
            )
        
        selected_req = canton_reqs[0]
        
        # Extract payer from Canton payment payload (already have payment_dict)
        payload = payment_dict.get("payload", {})
        payer_address = None
        
        if isinstance(payload, dict):
            command = payload.get("command", {})
            if isinstance(command, dict):
                payer_address = command.get("payer")
        
        if payer_address:
            request.state.x402_payer_address = payer_address
            logger.info(f"✅ Extracted Canton payer: {payer_address}")
        
        # Call Canton facilitator /verify endpoint
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Use the raw payment_dict instead of trying to serialize PaymentPayload model
                # Canton payments don't follow EVM PaymentPayload structure
                response = await client.post(
                    f"{self.canton_facilitator_url}/verify",
                    json={
                        "paymentPayload": payment_dict,  # Use raw dict, not model_dump()
                        "paymentRequirements": selected_req  # Already a dict
                    }
                )
                
                if response.status_code != 200:
                    logger.error(f"Canton facilitator error: HTTP {response.status_code}")
                    raise PaymentVerificationError(
                        f"Canton facilitator error: {response.status_code}", 
                        payment_requirements
                    )
                
                verify_result = response.json()
                
                if not verify_result.get("isValid"):
                    error_reason = verify_result.get("invalidReason", "Unknown error")
                    logger.warning(
                        f"Canton payment verification failed for '{tool_name}': {error_reason}"
                    )
                    raise PaymentVerificationError(
                        f"Invalid Canton payment: {error_reason}", 
                        payment_requirements
                    )
        except httpx.RequestError as e:
            logger.error(f"Canton facilitator connection error: {e}")
            raise PaymentVerificationError(
                f"Canton facilitator unavailable: {str(e)}", 
                payment_requirements
            )
        
        # Payment verified - store for settlement
        logger.info(
            f"✅ Canton payment verified for '{tool_name}': ${self.get_tool_price(tool_name, arguments):.4f}"
        )
        request.state.x402_payment = payment_dict  # Store raw dict, not PaymentPayload
        request.state.x402_requirements = selected_req
        request.state.x402_facilitator_type = "canton"

    async def _verify_evm_payment(
        self, request: Request, payment: PaymentPayload, payment_requirements: list, 
        tool_name: str, arguments: dict
    ) -> None:
        """Verify USDC/EVM payment via existing FacilitatorClient"""
        
        # Extract payer address from payment for DCAP tracking
        payment_dict = json.loads(safe_base64_decode(request.headers.get("X-PAYMENT", "")))
        payer_address = None
        
        # Navigate to payload.authorization (EIP-712 message)
        payload = payment_dict.get("payload", {})
        if isinstance(payload, dict):
            authorization = payload.get("authorization", {})
            if isinstance(authorization, dict):
                payer_address = (
                    authorization.get("from") or 
                    authorization.get("payer") or
                    authorization.get("sender") or
                    authorization.get("walletAddress") or
                    authorization.get("address")
                )
            
            # Fallback: check payload level
            if not payer_address:
                payer_address = (
                    payload.get("from") or 
                    payload.get("payer") or
                    payload.get("sender") or
                    payload.get("walletAddress")
                )
        
        # Final fallback: check top level
        if not payer_address:
            payer_address = (
                payment_dict.get("from") or 
                payment_dict.get("payer") or
                payment_dict.get("sender") or
                payment_dict.get("walletAddress")
            )
        
        if payer_address:
            request.state.x402_payer_address = payer_address
            logger.info(f"✅ Extracted payer address: {payer_address}")

        # Find matching payment requirements
        selected_payment_requirements = find_matching_payment_requirements(
            payment_requirements, payment
        )

        if not selected_payment_requirements:
            logger.warning(f"No matching payment requirements for '{tool_name}'")
            raise PaymentVerificationError(
                "No matching payment requirements found", payment_requirements
            )

        # Verify with EVM facilitator
        facilitator = FacilitatorClient(None)  # Uses default config
        verify_response = await facilitator.verify(
            payment, selected_payment_requirements
        )

        if not verify_response.is_valid:
            error_reason = verify_response.invalid_reason or "Unknown error"
            logger.warning(
                f"Payment verification failed for '{tool_name}': {error_reason}"
            )
            raise PaymentVerificationError(
                f"Invalid payment: {error_reason}", payment_requirements
            )

        # Payment verified - store for settlement after successful execution
        logger.info(
            f"✅ Payment verified for '{tool_name}': ${self.get_tool_price(tool_name, arguments):.4f}"
        )
        request.state.x402_payment = payment
        request.state.x402_requirements = selected_payment_requirements
        request.state.x402_facilitator = facilitator
        request.state.x402_facilitator_type = "evm"
        request.state.x402_verify_response = verify_response

    async def settle_payment(
        self, request: Request, tool_name: str, execution_successful: bool
    ) -> Optional[dict]:
        """
        Settle payment - routes to correct facilitator based on facilitator_type.

        Args:
            request: FastAPI request object
            tool_name: Name of the tool that was called
            execution_successful: Whether tool execution succeeded

        Returns:
            Settlement response dict if successful, None otherwise
        """
        if not execution_successful or not hasattr(request.state, "x402_payment"):
            return None

        facilitator_type = getattr(request.state, "x402_facilitator_type", "evm")
        
        if facilitator_type == "canton":
            return await self._settle_canton_payment(request, tool_name)
        else:
            return await self._settle_evm_payment(request, tool_name)

    async def _settle_evm_payment(
        self, request: Request, tool_name: str
    ) -> Optional[dict]:
        """Settle USDC/EVM payment via existing FacilitatorClient"""
        facilitator = request.state.x402_facilitator
        payment = request.state.x402_payment
        requirements = request.state.x402_requirements

        # Settlement retry configuration
        max_retries = 3
        retry_delay = 1  # seconds

        for attempt in range(max_retries):
            try:
                settle_response = await facilitator.settle(payment, requirements)

                if settle_response.success:
                    # Log settlement - only show attempt number if it's a retry
                    if attempt > 0:
                        logger.info(
                            f"💵 Payment settled for '{tool_name}' (attempt {attempt + 1}/{max_retries})"
                        )
                    else:
                        logger.info(f"💵 Payment settled for '{tool_name}'")
                    # Return settlement data for response header
                    return {
                        "success": settle_response.success,
                        "errorReason": settle_response.error_reason,
                        "transaction": settle_response.transaction,
                        "network": settle_response.network or self.network,
                        "payer": settle_response.payer,
                    }
                else:
                    error_msg = (
                        settle_response.error_reason or "Unknown settlement error"
                    )
                    logger.warning(
                        f"Payment settlement failed (attempt {attempt + 1}/{max_retries}): {error_msg}"
                    )

                    # Retry with exponential backoff
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2**attempt)
                        logger.info(f"Retrying settlement in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        # Final attempt failed - log for manual review
                        logger.error(
                            f"❌ Settlement failed after {max_retries} attempts for '{tool_name}': {error_msg}"
                        )
                        logger.error(
                            f"Manual review required - Payment: {payment.model_dump()}"
                        )

            except Exception as e:
                logger.error(
                    f"Settlement exception (attempt {attempt + 1}/{max_retries}): {e}"
                )
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2**attempt)
                    logger.info(f"Retrying after exception in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"❌ Settlement failed with exception after {max_retries} attempts"
                    )

        return None

    async def _settle_canton_payment(
        self, request: Request, tool_name: str
    ) -> Optional[dict]:
        """Settle Canton payment via Canton facilitator with retry logic"""
        import httpx
        
        payment = request.state.x402_payment
        requirements = request.state.x402_requirements
        
        # Re-extract payment_dict from request header for Canton
        payment_dict = json.loads(safe_base64_decode(request.headers.get("X-PAYMENT", "")))
        
        max_retries = 3
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        f"{self.canton_facilitator_url}/settle",
                        json={
                            "paymentPayload": payment_dict,  # Use raw dict, not model_dump()
                            "paymentRequirements": requirements  # Already a dict
                        }
                    )
                    
                    if response.status_code != 200:
                        logger.warning(
                            f"Canton settlement HTTP error (attempt {attempt + 1}/{max_retries}): {response.status_code}"
                        )
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (2**attempt)
                            logger.info(f"Retrying Canton settlement in {wait_time}s...")
                            await asyncio.sleep(wait_time)
                        continue
                    
                    settle_result = response.json()
                    
                    if settle_result.get("success"):
                        # Log settlement - only show attempt number if it's a retry
                        if attempt > 0:
                            logger.info(
                                f"💵 Canton payment settled for '{tool_name}' (attempt {attempt + 1}/{max_retries})"
                            )
                        else:
                            logger.info(f"💵 Canton payment settled for '{tool_name}'")
                        
                        return {
                            "success": True,
                            "transaction": settle_result.get("transaction"),
                            "network": settle_result.get("network", self.canton_network),
                            "payer": settle_result.get("payer"),
                        }
                    else:
                        error_msg = settle_result.get("errorReason", "Unknown settlement error")
                        logger.warning(
                            f"Canton settlement failed (attempt {attempt + 1}/{max_retries}): {error_msg}"
                        )
                        
                        # Retry with exponential backoff
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (2**attempt)
                            logger.info(f"Retrying Canton settlement in {wait_time}s...")
                            await asyncio.sleep(wait_time)
                        else:
                            # Final attempt failed - log for manual review
                            logger.error(
                                f"❌ Canton settlement failed after {max_retries} attempts for '{tool_name}': {error_msg}"
                            )
                            logger.error(
                                f"Manual review required - Payment: {payment_dict}"
                            )
                            
            except httpx.RequestError as e:
                logger.error(
                    f"Canton settlement connection error (attempt {attempt + 1}/{max_retries}): {e}"
                )
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2**attempt)
                    logger.info(f"Retrying after exception in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"❌ Canton settlement failed with exception after {max_retries} attempts"
                    )
            except Exception as e:
                logger.error(
                    f"Canton settlement unexpected error (attempt {attempt + 1}/{max_retries}): {e}"
                )
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2**attempt)
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"❌ Canton settlement failed after {max_retries} attempts")
        
        return None

    def create_payment_response_header(
        self, settlement_data: Optional[dict]
    ) -> Optional[Tuple[str, str]]:
        """
        Create X-Payment-Response header from settlement data.

        Args:
            settlement_data: Settlement response dict

        Returns:
            Tuple of (header_name, header_value) or None
        """
        if not settlement_data:
            return None

        try:
            payment_response_json = json.dumps(settlement_data)
            payment_response_b64 = base64.b64encode(
                payment_response_json.encode("utf-8")
            ).decode("utf-8")
            logger.debug(
                f"Created X-Payment-Response header: tx={settlement_data.get('transaction')}"
            )
            return ("X-Payment-Response", payment_response_b64)
        except Exception as e:
            logger.warning(f"Error creating payment response header: {e}")
            return None
