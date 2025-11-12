"""
Canton MCP Server Environment Configuration

Handles loading environment variables from .env.canton file or system environment.
Supports both local development and isolated deployment environments.
"""

import os
import sys
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

ENV_VALUES = {}

# Check if running in an isolated environment (e.g., AWS ECS, Kubernetes, etc.)
# where .env.canton file is not available
is_isolated_environment = (
    os.environ.get("IS_ISOLATED_ENVIRONMENT", "false").lower() == "true"
)

# Environment variable loading strategy:
# - Local development: Load from .env.canton file for convenience
# - Isolated environments: Use system environment variables only
if not is_isolated_environment:
    # Local development mode: Load environment variables from .env.canton file
    env_canton_path = Path(__file__).parent.parent.parent / ".env.canton"

    if env_canton_path.exists():
        load_dotenv(env_canton_path)
        ENV_VALUES = dotenv_values(env_canton_path)
    else:
        # Try to find .env.canton in current working directory
        cwd_env_path = Path.cwd() / ".env.canton"
        if cwd_env_path.exists():
            load_dotenv(cwd_env_path)
            ENV_VALUES = dotenv_values(cwd_env_path)
        else:
            print(
                "WARNING: .env.canton file not found. "
                "Canton MCP server will use system environment variables only. "
                f"Searched locations:\n  - {env_canton_path}\n  - {cwd_env_path}",
                file=sys.stderr,
            )
            ENV_VALUES = {}

else:
    # Isolated environment mode: Load all configuration from system environment variables
    # This is used in production deployments where .env.canton files are not accessible
    ENV_VALUES = {}

# MCP Server Configuration
ENV_VALUES["MCP_SERVER_URL"] = os.getenv("MCP_SERVER_URL", "http://localhost:7284")

# x402 Payment Configuration (USDC on Base Sepolia)
ENV_VALUES["X402_ENABLED"] = os.getenv("X402_ENABLED", "false")
ENV_VALUES["X402_WALLET_ADDRESS"] = os.getenv("X402_WALLET_ADDRESS", "")
ENV_VALUES["X402_WALLET_PRIVATE_KEY"] = os.getenv("X402_WALLET_PRIVATE_KEY", "")
ENV_VALUES["X402_NETWORK"] = os.getenv("X402_NETWORK", "base-sepolia")
ENV_VALUES["X402_TOKEN"] = os.getenv("X402_TOKEN", "USDC")

# DAML SDK Configuration
ENV_VALUES["DAML_SDK_VERSION"] = os.getenv("DAML_SDK_VERSION", "3.4.0-snapshot.20251013.0")

# Canton x402 Payment Configuration (Canton Coins on Canton Network)
ENV_VALUES["CANTON_ENABLED"] = os.getenv("CANTON_ENABLED", "false")
ENV_VALUES["CANTON_FACILITATOR_URL"] = os.getenv("CANTON_FACILITATOR_URL", "http://localhost:3000")
ENV_VALUES["CANTON_PAYEE_PARTY"] = os.getenv("CANTON_PAYEE_PARTY", "")
ENV_VALUES["CANTON_NETWORK"] = os.getenv("CANTON_NETWORK", "canton-local")

# Internal API Key for payment bypass (cron jobs, internal services)
ENV_VALUES["X402_INTERNAL_API_KEY"] = os.getenv("X402_INTERNAL_API_KEY", "")

# Pricing Configuration
ENV_VALUES["X402_PRICING_MODE"] = os.getenv("X402_PRICING_MODE", "dynamic")
ENV_VALUES["X402_MIN_PAYMENT"] = os.getenv("X402_MIN_PAYMENT", "0.001")
ENV_VALUES["X402_MAX_PAYMENT"] = os.getenv("X402_MAX_PAYMENT", "10.0")

# Payment Processing
ENV_VALUES["X402_VERIFICATION_TIMEOUT"] = os.getenv("X402_VERIFICATION_TIMEOUT", "30")
ENV_VALUES["X402_SETTLEMENT_TIMEOUT"] = os.getenv("X402_SETTLEMENT_TIMEOUT", "60")

# DCAP (Distributed Claude Agent Protocol) Configuration
ENV_VALUES["DCAP_ENABLED"] = os.getenv("DCAP_ENABLED", "true")
ENV_VALUES["DCAP_MULTICAST_IP"] = os.getenv(
    "DCAP_MULTICAST_IP", ""
)  # Must be explicitly configured
ENV_VALUES["DCAP_PORT"] = os.getenv("DCAP_PORT", "10191")
ENV_VALUES["DCAP_SERVER_ID"] = os.getenv("DCAP_SERVER_ID", "canton-mcp")
ENV_VALUES["DCAP_SERVER_NAME"] = os.getenv("DCAP_SERVER_NAME", "Canton MCP Server")
# DCAP v2.4 - Fallback values when caller/payer cannot be determined from request
# In production, these should be extracted from X-Caller-ID header and x402 payment
ENV_VALUES["DCAP_DEFAULT_CALLER"] = os.getenv("DCAP_DEFAULT_CALLER", "unknown-client")
ENV_VALUES["DCAP_DEFAULT_PAYER"] = os.getenv("DCAP_DEFAULT_PAYER", "0x0000000000000000000000000000000000000000")

# LLM Enrichment Configuration
ENV_VALUES["ENABLE_LLM_ENRICHMENT"] = os.getenv("ENABLE_LLM_ENRICHMENT", "false")
ENV_VALUES["ANTHROPIC_API_KEY"] = os.getenv("ANTHROPIC_API_KEY", "")
ENV_VALUES["LLM_ENRICHMENT_MODEL"] = os.getenv("LLM_ENRICHMENT_MODEL", "claude-3-5-haiku-20241022")
ENV_VALUES["LLM_ENRICHMENT_BATCH_SIZE"] = os.getenv("LLM_ENRICHMENT_BATCH_SIZE", "20")
ENV_VALUES["LLM_ENRICHMENT_MAX_TOKENS"] = os.getenv("LLM_ENRICHMENT_MAX_TOKENS", "500")

# LLM Authorization Extraction Configuration (PRIMARY METHOD)
# When enabled, LLM is the primary method for authorization extraction
# When disabled, falls back to regex patterns (degraded mode)
ENV_VALUES["ENABLE_LLM_AUTH_EXTRACTION"] = os.getenv("ENABLE_LLM_AUTH_EXTRACTION", "true")
ENV_VALUES["LLM_AUTH_CONFIDENCE_THRESHOLD"] = os.getenv("LLM_AUTH_CONFIDENCE_THRESHOLD", "0.7")


def get_env(key: str, default: str = "") -> str:
    """
    Get environment variable value.

    Args:
        key: Environment variable key
        default: Default value if key not found

    Returns:
        Environment variable value or default
    """
    return ENV_VALUES.get(key, default)


def get_env_bool(key: str, default: bool = False) -> bool:
    """
    Get environment variable as boolean.

    Args:
        key: Environment variable key
        default: Default value if key not found

    Returns:
        Boolean value
    """
    value = ENV_VALUES.get(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")


def get_env_int(key: str, default: int = 0) -> int:
    """
    Get environment variable as integer.

    Args:
        key: Environment variable key
        default: Default value if key not found

    Returns:
        Integer value
    """
    try:
        return int(ENV_VALUES.get(key, default))
    except (ValueError, TypeError):
        return default


def get_env_float(key: str, default: float = 0.0) -> float:
    """
    Get environment variable as float.

    Args:
        key: Environment variable key
        default: Default value if key not found

    Returns:
        Float value
    """
    try:
        return float(ENV_VALUES.get(key, default))
    except (ValueError, TypeError):
        return default

