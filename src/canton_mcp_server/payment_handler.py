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

    def __init__(self, message: str, payment_requirements: List[PaymentRequirements]):
        error_data = PaymentErrorData(
            message=message,
            status_code=402,
            payment_requirements=[
                req.model_dump(by_alias=True) for req in payment_requirements
            ],
            error_code="PAYMENT_REQUIRED",
        )
        super().__init__(error_data)


class PaymentVerificationError(PaymentError):
    """Raised when payment verification fails"""

    def __init__(self, message: str, payment_requirements: List[PaymentRequirements]):
        error_data = PaymentErrorData(
            message=message,
            status_code=402,
            payment_requirements=[
                req.model_dump(by_alias=True) for req in payment_requirements
            ],
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
        self.enabled = get_env_bool("X402_ENABLED", False)
        self.wallet_address = get_env("X402_WALLET_ADDRESS", "")
        self.network = get_env("X402_NETWORK", "base-sepolia")
        self.internal_api_key = get_env("X402_INTERNAL_API_KEY", "")

        # Validate configuration if enabled
        if self.enabled:
            self._validate_configuration()
            logger.info(f"🔐 X402 payment protection enabled (network: {self.network})")
            logger.info(f"💰 Dynamic pricing enabled - wallet: {self.wallet_address}")

    def _validate_configuration(self):
        """Validate required x402 configuration"""
        if not self.wallet_address:
            raise ValueError(
                "X402_ENABLED=true but X402_WALLET_ADDRESS not configured. "
                "Please set X402_WALLET_ADDRESS in .env.mcp or disable x402 with X402_ENABLED=false"
            )
        if not self.network:
            raise ValueError(
                "X402_ENABLED=true but X402_NETWORK not configured. "
                "Please set X402_NETWORK (e.g., 'base', 'base-sepolia') in .env.mcp"
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

        Args:
            request: FastAPI request object
            tool_name: Name of the tool being called
            arguments: Tool arguments

        Returns:
            List of payment requirements

        Raises:
            PaymentConfigurationError: If price configuration fails
        """
        # Calculate price for this specific tool
        price_usd = self.get_tool_price(tool_name, arguments)

        # Convert to atomic amount
        try:
            max_amount_required, asset_address, eip712_domain = (
                process_price_to_atomic_amount(f"${price_usd}", self.network)
            )
        except Exception as e:
            logger.error(f"Error processing price for {tool_name}: {e}")
            raise PaymentConfigurationError(f"Price configuration error: {str(e)}")

        # Build payment requirements
        resource_url = str(request.url)
        return [
            PaymentRequirements(
                scheme="exact",
                network=cast(SupportedNetworks, self.network),
                asset=asset_address,
                max_amount_required=max_amount_required,
                resource=resource_url,
                description=f"MCP Tool: {tool_name}",
                mime_type="application/json",
                pay_to=self.wallet_address,
                max_timeout_seconds=60,
                output_schema={
                    "input": {"type": "http", "method": "POST", "discoverable": True},
                    "output": None,
                },
                extra=eip712_domain,
            )
        ]

    async def verify_payment(
        self, request: Request, tool_name: str, arguments: dict
    ) -> None:
        """
        Verify x402 payment for MCP tool call.

        Args:
            request: FastAPI request object
            tool_name: Name of the tool being called
            arguments: Tool arguments

        Raises:
            PaymentRequiredError: If payment is required but not provided
            PaymentVerificationError: If payment verification fails
            PaymentConfigurationError: If payment configuration is invalid
        """
        if not self.enabled or not self.wallet_address:
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

        # Build payment requirements
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

        # Verify payment
        try:
            payment_dict = json.loads(safe_base64_decode(payment_header))
            payment = PaymentPayload(**payment_dict)
            
            # Extract payer address from payment for DCAP tracking
            # x402 payment structure: { x402Version, scheme, network, payload: { signature, authorization: {...} } }
            # The payer address is in payload.authorization object (EIP-712 signed message)
            payer_address = None
            
            # Navigate to payload.authorization
            payload = payment_dict.get("payload", {})
            if isinstance(payload, dict):
                # Check authorization object (EIP-712 message)
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
            else:
                # Log more detail for debugging
                auth_keys = list(authorization.keys()) if isinstance(authorization, dict) else 'N/A'
                logger.warning(f"⚠️ Could not extract payer. Payload keys: {list(payload.keys()) if isinstance(payload, dict) else 'N/A'}, Authorization keys: {auth_keys}")
        except Exception as e:
            logger.warning(f"Invalid payment header: {e}")
            raise PaymentVerificationError(
                "Invalid payment header format", payment_requirements
            )

        # Find matching payment requirements
        selected_payment_requirements = find_matching_payment_requirements(
            payment_requirements, payment
        )

        if not selected_payment_requirements:
            logger.warning(f"No matching payment requirements for '{tool_name}'")
            raise PaymentVerificationError(
                "No matching payment requirements found", payment_requirements
            )

        # Verify with facilitator
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
        request.state.x402_verify_response = verify_response

    async def settle_payment(
        self, request: Request, tool_name: str, execution_successful: bool
    ) -> Optional[dict]:
        """
        Settle payment with retry logic.

        Args:
            request: FastAPI request object
            tool_name: Name of the tool that was called
            execution_successful: Whether tool execution succeeded

        Returns:
            Settlement response dict if successful, None otherwise
        """
        if not execution_successful or not hasattr(request.state, "x402_payment"):
            return None

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
