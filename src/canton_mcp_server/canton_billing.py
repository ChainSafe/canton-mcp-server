"""
Canton On-Chain Billing

Creates ChargeReceipt contracts on Canton ledger after tool execution.
Queries ChargeReceipts to compute balance.

Uses OAuth2 client credentials flow to authenticate with Canton JSON API.
Uses submit-and-wait for write operations (provider is a local party with keys
managed by the Canton participant).
"""

import asyncio
import base64
import json as json_module
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set

import httpx
import orjson

from canton_mcp_server.env import get_env, get_env_bool

logger = logging.getLogger(__name__)

# Canton 3.4 gRPC flow via billing portal
USE_CANTON_34_FLOW = get_env_bool("USE_CANTON_34_FLOW", False)
BILLING_PORTAL_URL = get_env("BILLING_PORTAL_URL", "http://localhost:3050")

# Environment configuration
CANTON_LEDGER_URL = get_env("CANTON_LEDGER_URL", "http://localhost:3975")
CANTON_OAUTH_TOKEN_URL = os.getenv(
    "CANTON_OAUTH_TOKEN_URL",
    "http://localhost:8082/realms/AppProvider/protocol/openid-connect/token"
)
CANTON_OAUTH_CLIENT_ID = os.getenv("CANTON_OAUTH_CLIENT_ID", "app-provider-validator")
CANTON_OAUTH_CLIENT_SECRET = os.getenv("CANTON_OAUTH_CLIENT_SECRET", "")
CANTON_OAUTH_AUDIENCE = os.getenv("CANTON_OAUTH_AUDIENCE", "")
CANTON_PROVIDER_PARTY = os.getenv("CANTON_PROVIDER_PARTY", "")
# Canton user ID (UUID) - different from OAuth client ID
# This is the user ID registered in Canton's User Management service
CANTON_USER_ID = os.getenv("CANTON_USER_ID", "")
BILLING_PACKAGE_ID = os.getenv(
    "BILLING_PACKAGE_ID",
    "1cdb79cf535e8fdd0b1ae677ddf7a534f6d343a1a8811b88cf19e00ffbcef2c0"
)

# Self-signed JWT mode for localnet (Canton uses unsafe-jwt-hmac-256)
CANTON_LEDGER_AUTH_MODE = os.getenv("CANTON_LEDGER_AUTH_MODE", "oauth")
CANTON_LEDGER_JWT_SECRET = os.getenv("CANTON_LEDGER_JWT_SECRET", "")

# Token cache
_token_cache: dict = {"token": None, "expires_at": 0}

# ChargeManager contract cache
_charge_manager_cache: dict = {"contract_id": None, "timestamp": 0}
CACHE_TTL = 5 * 60  # 5 minutes

# Validator API configuration (for external party registration)
VALIDATOR_API_URL = os.getenv("VALIDATOR_API_URL", "http://localhost:3903/api/validator")
VALIDATOR_OAUTH_TOKEN_URL = os.getenv("VALIDATOR_OAUTH_TOKEN_URL", "")
VALIDATOR_OAUTH_CLIENT_ID = os.getenv("VALIDATOR_OAUTH_CLIENT_ID", "")
VALIDATOR_OAUTH_CLIENT_SECRET = os.getenv("VALIDATOR_OAUTH_CLIENT_SECRET", "")
VALIDATOR_OAUTH_AUDIENCE = os.getenv("VALIDATOR_OAUTH_AUDIENCE", "")

# Validator OAuth token cache (separate from ledger API token)
_validator_token_cache: dict = {"token": None, "expires_at": 0}

# Persistent cache of parties already registered on-chain
_REGISTERED_PARTIES_FILE = os.getenv(
    "REGISTERED_PARTIES_FILE", "/app/data/registered_parties.json"
)
_registered_parties: Set[str] = set()


def _load_registered_parties() -> None:
    """Load registered parties from disk on startup."""
    global _registered_parties
    try:
        path = Path(_REGISTERED_PARTIES_FILE)
        if path.exists():
            data = json_module.loads(path.read_text())
            _registered_parties = set(data.get("parties", []))
            logger.info(f"Loaded {len(_registered_parties)} registered parties from {path}")
    except Exception as e:
        logger.warning(f"Failed to load registered parties from disk: {e}")


def _save_registered_parties() -> None:
    """Persist registered parties to disk."""
    try:
        path = Path(_REGISTERED_PARTIES_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json_module.dumps({"parties": sorted(_registered_parties)}))
    except Exception as e:
        logger.warning(f"Failed to save registered parties to disk: {e}")


def _add_registered_party(party_id: str) -> None:
    """Add a party to the registered set and persist."""
    _registered_parties.add(party_id)
    _save_registered_parties()


# Load on module import
_load_registered_parties()


@dataclass
class ChargeRecord:
    """A charge record from the ledger"""
    contract_id: str
    user_party: str
    tool: str
    amount: float
    request_id: str
    created_at: str
    description: Optional[str] = None


@dataclass
class CreditRecord:
    """A credit record from the ledger"""
    contract_id: str
    user_party: str
    amount: float
    transfer_id: str
    created_at: str
    description: Optional[str] = None


@dataclass
class BalanceResult:
    """Balance computation result"""
    total_charged: float
    total_credited: float
    charges: list[ChargeRecord]
    credits: list[CreditRecord]
    balance: float  # Positive = has credit, Negative = owes money


class CantonBillingError(Exception):
    """Base exception for billing errors"""
    pass


class OAuthError(CantonBillingError):
    """OAuth authentication error"""
    pass


class LedgerError(CantonBillingError):
    """Canton ledger API error"""
    pass


async def _get_validator_oauth_token() -> str:
    """
    Get OAuth2 access token for Validator Admin API.

    Uses client_credentials flow. Tokens are cached until near expiry.
    Uses separate credentials from the ledger API token.
    """
    global _validator_token_cache

    # Check cache
    if _validator_token_cache["token"] and time.time() < _validator_token_cache["expires_at"] - 60:
        return _validator_token_cache["token"]

    if not VALIDATOR_OAUTH_TOKEN_URL or not VALIDATOR_OAUTH_CLIENT_SECRET:
        raise OAuthError("Validator OAuth not configured (VALIDATOR_OAUTH_TOKEN_URL / VALIDATOR_OAUTH_CLIENT_SECRET)")

    logger.info(f"Fetching Validator OAuth token from {VALIDATOR_OAUTH_TOKEN_URL}")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_data = {
                "grant_type": "client_credentials",
                "client_id": VALIDATOR_OAUTH_CLIENT_ID,
                "client_secret": VALIDATOR_OAUTH_CLIENT_SECRET,
            }
            if VALIDATOR_OAUTH_AUDIENCE:
                token_data["audience"] = VALIDATOR_OAUTH_AUDIENCE

            response = await client.post(
                VALIDATOR_OAUTH_TOKEN_URL,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                error_text = response.text
                logger.error(f"Validator OAuth token request failed: {response.status_code} {error_text}")
                raise OAuthError(f"Failed to get Validator OAuth token: {response.status_code} {error_text}")

            data = orjson.loads(response.content)
            token = data["access_token"]
            expires_in = data.get("expires_in", 3600)

            _validator_token_cache = {
                "token": token,
                "expires_at": time.time() + expires_in,
            }

            logger.info(f"Validator OAuth token obtained, expires in {expires_in}s")
            return token

    except httpx.RequestError as e:
        raise OAuthError(f"Validator OAuth request failed: {e}")


async def generate_topology_via_billing_portal(
    party_id: str, public_key_b64: str
) -> Optional[dict]:
    """
    Generate topology transactions via the billing portal's Canton 3.4 gRPC flow.

    Delegates to the billing portal which has the full gRPC client implementation
    (protos, grpcio, DER encoding, Canton hashing).

    Args:
        party_id: Full Canton party ID (e.g., "test-limit::1220...")
        public_key_b64: Base64-encoded Ed25519 public key

    Returns:
        Dict with {topology_txs, key_fingerprint, flow} or None if already registered
    """
    if party_id in _registered_parties:
        return None

    logger.info(f"Generating topology via billing portal for party: {party_id}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{BILLING_PORTAL_URL}/api/register-party/generate",
                json={
                    "partyId": party_id,
                    "publicKey": public_key_b64,
                },
            )

        if response.status_code != 200:
            error_text = response.text
            if any(s in error_text for s in [
                "already exists", "ALREADY_EXISTS",
                "already registered",
            ]):
                _add_registered_party(party_id)
                logger.info(f"Party already registered (billing portal): {party_id}")
                return None
            raise CantonBillingError(
                f"Billing portal generate failed: {response.status_code} {error_text}"
            )

        data = orjson.loads(response.content)
        topology_txs = data.get("topologyTxs", [])
        if not topology_txs:
            _add_registered_party(party_id)
            logger.info(f"Party already registered (no txs returned): {party_id}")
            return None

        logger.info(
            f"Billing portal generated {len(topology_txs)} topology txs for {party_id} "
            f"(flow: {data.get('flow', 'unknown')})"
        )
        return {
            "topology_txs": topology_txs,
            "key_fingerprint": data.get("keyFingerprint", ""),
            "flow": data.get("flow", "canton34"),
        }

    except CantonBillingError:
        raise
    except Exception as e:
        raise CantonBillingError(f"Billing portal topology generation error: {e}")


async def submit_topology_via_billing_portal(
    party_id: str,
    public_key_b64: str,
    signed_topology_txs: list,
    key_fingerprint: str,
    original_hash: str,
) -> bool:
    """
    Submit signed topology transactions via the billing portal's Canton 3.4 gRPC flow.

    Args:
        party_id: Full Canton party ID
        public_key_b64: Base64-encoded Ed25519 public key
        signed_topology_txs: List of {topology_tx, signed_hash} dicts
        key_fingerprint: Key fingerprint from the generate step
        original_hash: Original hash from the generate step

    Returns:
        True if party registered successfully
    """
    logger.info(f"Submitting {len(signed_topology_txs)} signed topology txs via billing portal for {party_id}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{BILLING_PORTAL_URL}/api/register-party/submit",
                json={
                    "signedTopologyTxs": signed_topology_txs,
                    "publicKey": public_key_b64,
                    "keyFingerprint": key_fingerprint,
                    "originalHash": original_hash,
                    "partyId": party_id,
                },
            )

        if response.status_code == 200:
            data = orjson.loads(response.content)
            if data.get("success"):
                _add_registered_party(party_id)
                logger.info(f"Party registered via billing portal gRPC: {party_id}")
                return True
            logger.warning(f"Billing portal submit returned success=false: {data}")
            return False

        error_text = response.text
        if any(s in error_text for s in [
            "already exists", "ALREADY_EXISTS",
            "already registered",
        ]):
            _add_registered_party(party_id)
            logger.info(f"Party already registered (billing portal submit): {party_id}")
            return True

        raise CantonBillingError(
            f"Billing portal submit failed: {response.status_code} {error_text}"
        )

    except CantonBillingError:
        raise
    except Exception as e:
        raise CantonBillingError(f"Billing portal topology submit error: {e}")


async def generate_topology_for_party(
    party_id: str, public_key_b64: str
):
    """
    Generate topology transactions for external party registration.

    When USE_CANTON_34_FLOW is enabled, delegates to the billing portal which
    uses Canton 3.4 gRPC. Otherwise, calls the Validator Admin API directly.

    Args:
        party_id: Full Canton party ID (e.g., "test-limit::1220...")
        public_key_b64: Base64-encoded Ed25519 public key

    Returns:
        - Canton 3.4 flow: dict with {topology_txs, key_fingerprint, flow} or None
        - Validator flow: list of {topology_tx, hash} dicts or None
    """
    if USE_CANTON_34_FLOW:
        return await generate_topology_via_billing_portal(party_id, public_key_b64)

    if party_id in _registered_parties:
        return None

    party_hint = party_id.split("::")[0] if "::" in party_id else party_id
    public_key_hex = base64.b64decode(public_key_b64).hex()

    logger.info(f"Generating topology for party: {party_id} (hint: {party_hint})")

    try:
        token = await _get_validator_oauth_token()

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{VALIDATOR_API_URL}/v0/admin/external-party/topology/generate",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "party_hint": party_hint,
                    "public_key": public_key_hex,
                },
            )

        if response.status_code != 200:
            error_text = response.text
            # "already exists" or "TOPOLOGY_SERIAL_MISMATCH" means party is registered
            if any(s in error_text for s in [
                "already exists", "ALREADY_EXISTS",
                "TOPOLOGY_SERIAL_MISMATCH", "serial_mismatch",
            ]):
                _add_registered_party(party_id)
                logger.info(f"Party already registered: {party_id}")
                return None
            raise CantonBillingError(
                f"Topology generate failed: {response.status_code} {error_text}"
            )

        data = orjson.loads(response.content)
        topology_txs = data.get("topology_txs", [])
        logger.info(f"Generated {len(topology_txs)} topology transactions for {party_id}")
        return topology_txs

    except (OAuthError, CantonBillingError):
        raise
    except Exception as e:
        raise CantonBillingError(f"Topology generation error: {e}")


async def submit_signed_topology(
    party_id: str,
    public_key_b64: str,
    signed_topology_txs: list,
) -> bool:
    """
    Submit signed topology transactions to register the party.

    Args:
        party_id: Full Canton party ID
        public_key_b64: Base64-encoded Ed25519 public key
        signed_topology_txs: List of {topology_tx, signed_hash} dicts

    Returns:
        True if party registered successfully
    """
    public_key_hex = base64.b64decode(public_key_b64).hex()

    logger.info(f"Submitting {len(signed_topology_txs)} signed topology txs for {party_id}")

    try:
        token = await _get_validator_oauth_token()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{VALIDATOR_API_URL}/v0/admin/external-party/topology/submit",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "signed_topology_txs": signed_topology_txs,
                    "public_key": public_key_hex,
                },
            )

        if response.status_code == 200:
            _add_registered_party(party_id)
            logger.info(f"Party registered on-chain: {party_id}")
            return True

        error_text = response.text
        if any(s in error_text for s in [
            "already exists", "ALREADY_EXISTS",
            "TOPOLOGY_SERIAL_MISMATCH", "serial_mismatch",
        ]):
            _add_registered_party(party_id)
            logger.info(f"Party already registered: {party_id}")
            return True

        raise CantonBillingError(
            f"Topology submit failed: {response.status_code} {error_text}"
        )

    except (OAuthError, CantonBillingError):
        raise
    except Exception as e:
        raise CantonBillingError(f"Topology submit error: {e}")


def is_party_registered(party_id: str) -> bool:
    """Check if party is in the registered cache."""
    return party_id in _registered_parties


async def ensure_party_registered(party_id: str) -> bool:
    """
    Ensure a party is visible to the participant (registered in topology).

    Two-step check:
    1. Billing portal's /api/register-party/check (ListPartyToParticipant gRPC)
       — finds parties mapped to OUR participant
    2. Ledger probe query (filtersByParty with the party)
       — finds parties on ANY participant in the synchronizer (e.g. mainnet-beta
         hosted on a different participant but visible via the global domain)

    Args:
        party_id: Canton party ID to check

    Returns:
        True if party is confirmed visible to the ledger, False otherwise
    """
    if party_id in _registered_parties:
        return True

    # Provider party is always registered
    if party_id == CANTON_PROVIDER_PARTY:
        _add_registered_party(party_id)
        return True

    logger.info(f"Checking party registration: {party_id}")

    # Step 1: Check billing portal (ListPartyToParticipant on our participant)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{BILLING_PORTAL_URL}/api/register-party/check",
                json={"partyId": party_id},
            )

        if response.status_code == 200:
            data = orjson.loads(response.content)
            if data.get("exists"):
                _add_registered_party(party_id)
                logger.info(f"Party confirmed registered (topology): {party_id}")
                return True
    except Exception as e:
        logger.warning(f"Party topology check failed: {e}")

    # Step 2: Ledger probe — query active contracts with the party in filtersByParty.
    # If the ledger doesn't reject the party, it's known on the synchronizer
    # (even if hosted on a different participant).
    try:
        offset = await get_ledger_offset()
        await _make_ledger_request(
            "POST",
            "/v2/state/active-contracts",
            {
                "filter": {
                    "filtersByParty": {
                        party_id: {
                            "filters": []
                        }
                    }
                },
                "activeAtOffset": offset,
            }
        )
        # If we get here without error, the ledger knows this party
        _add_registered_party(party_id)
        logger.info(f"Party confirmed registered (ledger probe): {party_id}")
        return True
    except (LedgerError, CantonBillingError) as e:
        error_str = str(e)
        if "unknownInformees" in error_str or "UNKNOWN_INFORMEES" in error_str:
            logger.warning(f"Party truly unknown to ledger: {party_id}")
            return False
        # Other ledger errors (network, auth) — don't conclude party is unregistered
        logger.warning(f"Ledger probe inconclusive for {party_id}: {e}")
        return False
    except Exception as e:
        logger.warning(f"Ledger probe failed for {party_id}: {e}")
        return False


async def get_oauth_token() -> str:
    """
    Get OAuth2 access token for Canton JSON API.

    Supports two modes:
    - "self-signed": Generate HS256 JWT locally (for localnet with unsafe-jwt-hmac-256)
    - "oauth" (default): client_credentials flow with Keycloak/Auth0

    Tokens are cached until near expiry.
    """
    global _token_cache

    # Check cache
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    # Self-signed JWT for localnet (Canton uses unsafe-jwt-hmac-256)
    if CANTON_LEDGER_AUTH_MODE == "self-signed":
        import jwt

        if not CANTON_LEDGER_JWT_SECRET:
            raise OAuthError("CANTON_LEDGER_JWT_SECRET not configured for self-signed mode")

        now = int(time.time())
        expires_in = 300  # 5 minutes
        payload = {
            "sub": CANTON_USER_ID or "ledger-api-user",
            "aud": CANTON_OAUTH_AUDIENCE or "https://canton.network.global",
            "iat": now,
            "exp": now + expires_in,
        }
        token = jwt.encode(payload, CANTON_LEDGER_JWT_SECRET, algorithm="HS256")
        _token_cache = {"token": token, "expires_at": now + expires_in}
        logger.info(f"Self-signed JWT generated (sub={payload['sub']}, aud={payload['aud']}, expires_in={expires_in}s)")
        return token

    if not CANTON_OAUTH_CLIENT_SECRET:
        raise OAuthError("CANTON_OAUTH_CLIENT_SECRET not configured")

    logger.info(f"Fetching OAuth token from {CANTON_OAUTH_TOKEN_URL} (audience={CANTON_OAUTH_AUDIENCE!r})")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_data = {
                    "grant_type": "client_credentials",
                    "client_id": CANTON_OAUTH_CLIENT_ID,
                    "client_secret": CANTON_OAUTH_CLIENT_SECRET,
                }
            if CANTON_OAUTH_AUDIENCE:
                token_data["audience"] = CANTON_OAUTH_AUDIENCE

            response = await client.post(
                CANTON_OAUTH_TOKEN_URL,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                error_text = response.text
                logger.error(f"OAuth token request failed: {response.status_code} {error_text}")
                raise OAuthError(f"Failed to get OAuth token: {response.status_code} {error_text}")

            data = orjson.loads(response.content)
            token = data["access_token"]
            expires_in = data.get("expires_in", 3600)

            _token_cache = {
                "token": token,
                "expires_at": time.time() + expires_in,
            }

            logger.info(f"OAuth token obtained, expires in {expires_in}s (aud={CANTON_OAUTH_AUDIENCE}, user={CANTON_USER_ID})")
            return token

    except httpx.RequestError as e:
        raise OAuthError(f"OAuth request failed: {e}")


async def _make_ledger_request(
    method: str,
    endpoint: str,
    data: Optional[dict] = None,
) -> dict:
    """
    Make authenticated request to Canton JSON API v2.

    Args:
        method: HTTP method (GET, POST)
        endpoint: API endpoint (e.g., /v2/state/active-contracts)
        data: Request body for POST

    Returns:
        JSON response data
    """
    token = await get_oauth_token()
    url = f"{CANTON_LEDGER_URL}{endpoint}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "GET":
                response = await client.get(url, headers=headers)
            else:
                response = await client.post(url, headers=headers, json=data)

            if response.status_code == 401:
                # Token expired, clear cache and retry
                _token_cache["token"] = None
                token = await get_oauth_token()
                headers["Authorization"] = f"Bearer {token}"

                if method == "GET":
                    response = await client.get(url, headers=headers)
                else:
                    response = await client.post(url, headers=headers, json=data)

            if response.status_code == 403:
                # 403 can mean stale/bad token — clear cache and retry once
                logger.warning(f"Ledger 403 Forbidden (retrying with fresh token): {response.text}")
                _token_cache["token"] = None
                token = await get_oauth_token()
                headers["Authorization"] = f"Bearer {token}"

                if method == "GET":
                    response = await client.get(url, headers=headers)
                else:
                    response = await client.post(url, headers=headers, json=data)

                if response.status_code in (200, 201):
                    return orjson.loads(response.content)

                logger.error(f"Ledger 403 Forbidden after token refresh: {response.text}")
                raise LedgerError(f"Access denied to Canton API: {response.text}")

            if response.status_code not in (200, 201):
                logger.error(f"Ledger error {response.status_code}: {response.text}")
                raise LedgerError(f"Ledger API error: {response.status_code} {response.text}")

            return orjson.loads(response.content)

    except httpx.RequestError as e:
        raise LedgerError(f"Ledger request failed: {e}")


async def get_ledger_offset() -> int:
    """Get current ledger offset for queries."""
    data = await _make_ledger_request("GET", "/v2/state/ledger-end")
    return data.get("offset", 0)


async def get_or_create_charge_manager() -> str:
    """
    Get or create the ChargeManager contract for the provider.

    ChargeManager is a singleton contract that authorizes charge creation.

    Returns:
        Contract ID of the ChargeManager
    """
    global _charge_manager_cache

    # Check cache
    if _charge_manager_cache["contract_id"] and time.time() - _charge_manager_cache["timestamp"] < CACHE_TTL:
        return _charge_manager_cache["contract_id"]

    if not CANTON_PROVIDER_PARTY:
        raise CantonBillingError("CANTON_PROVIDER_PARTY not configured")

    logger.info("Looking for existing ChargeManager contract...")

    # Query for existing ChargeManager
    template_id = f"{BILLING_PACKAGE_ID}:MCP.Billing:ChargeManager"

    try:
        # Get current ledger offset
        offset = await get_ledger_offset()

        data = await _make_ledger_request(
            "POST",
            "/v2/state/active-contracts",
            {
                "filter": {
                    "filtersByParty": {
                        CANTON_PROVIDER_PARTY: {
                            "filters": [{
                                "templateFilter": {
                                    "templateId": template_id
                                }
                            }]
                        }
                    }
                },
                "activeAtOffset": offset
            }
        )

        # Handle different response formats (list or dict with activeContracts)
        contracts = data if isinstance(data, list) else data.get("activeContracts", [])

        if contracts:
            # Handle different response formats
            first = contracts[0]
            contract_id = (
                first.get("contractId") or
                first.get("createdEvent", {}).get("contractId") or
                first.get("contractEntry", {}).get("activeContract", {}).get("createdEvent", {}).get("contractId") or
                first.get("contractEntry", {}).get("JsActiveContract", {}).get("createdEvent", {}).get("contractId")
            )
            if not contract_id:
                logger.error(f"Cannot find contractId in response: {first}")
                raise LedgerError("No contractId found in ChargeManager query response")
            logger.info(f"Found existing ChargeManager: {contract_id}")
            _charge_manager_cache = {
                "contract_id": contract_id,
                "timestamp": time.time(),
            }
            return contract_id

        # No ChargeManager exists, create one using submit-and-wait-for-transaction
        logger.info("Creating new ChargeManager contract...")

        create_data = await _make_ledger_request(
            "POST",
            "/v2/commands/submit-and-wait-for-transaction",
            {
                "commands": {
                    "userId": CANTON_USER_ID,
                    "commandId": f"create-charge-manager-{int(time.time())}",
                    "actAs": [CANTON_PROVIDER_PARTY],
                    "readAs": [CANTON_PROVIDER_PARTY],
                    "commands": [{
                        "CreateCommand": {
                            "templateId": template_id,
                            "createArguments": {
                                "provider": CANTON_PROVIDER_PARTY
                            }
                        }
                    }]
                }
            }
        )

        # Extract contract ID from transaction response
        events = create_data.get("transaction", {}).get("events", [])
        if not events:
            raise LedgerError("No events returned from ChargeManager creation")

        # Canton 3.4 uses "CreatedEvent" (uppercase) in JSON response
        created_event = events[0].get("CreatedEvent") or events[0].get("createdEvent", {})
        contract_id = created_event.get("contractId")
        if not contract_id:
            raise LedgerError("No contractId in ChargeManager creation response")

        logger.info(f"Created ChargeManager: {contract_id}")
        _charge_manager_cache = {
            "contract_id": contract_id,
            "timestamp": time.time(),
        }
        return contract_id

    except LedgerError:
        raise
    except Exception as e:
        logger.error(f"Failed to get/create ChargeManager: {e}")
        raise CantonBillingError(f"ChargeManager error: {e}")


async def create_charge_receipt(
    user_party: str,
    tool: str,
    amount: float,
    request_id: str,
    description: Optional[str] = None,
) -> str:
    """
    Create a ChargeReceipt contract on Canton ledger.

    Args:
        user_party: Canton party ID of the user being charged
        tool: Tool name
        amount: Charge amount in CC
        request_id: Unique request ID for idempotency
        description: Optional description

    Returns:
        Contract ID of the created ChargeReceipt
    """
    if not CANTON_PROVIDER_PARTY:
        raise CantonBillingError("CANTON_PROVIDER_PARTY not configured")

    template_id = f"{BILLING_PACKAGE_ID}:MCP.Billing:ChargeReceipt"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    logger.info(f"Creating ChargeReceipt: user={user_party} tool={tool} amount={amount}")

    try:
        # Create ChargeReceipt using submit-and-wait-for-transaction (provider is a local party)
        data = await _make_ledger_request(
            "POST",
            "/v2/commands/submit-and-wait-for-transaction",
            {
                "commands": {
                    "userId": CANTON_USER_ID,
                    "commandId": f"charge-{request_id}",
                    "actAs": [CANTON_PROVIDER_PARTY],
                    "readAs": [CANTON_PROVIDER_PARTY],
                    "commands": [{
                        "CreateCommand": {
                            "templateId": template_id,
                            "createArguments": {
                                "provider": CANTON_PROVIDER_PARTY,
                                "user": user_party,
                                "tool": tool,
                                "amount": str(amount),
                                "requestId": request_id,
                                "description": description or f"MCP tool: {tool}",
                                "timestamp": now,
                            }
                        }
                    }]
                }
            }
        )

        # Extract ChargeReceipt contract ID from transaction response
        events = data.get("transaction", {}).get("events", [])

        for event in events:
            # Canton 3.4 uses "CreatedEvent" (uppercase) in JSON response
            created = event.get("CreatedEvent") or event.get("createdEvent", {})
            template = created.get("templateId", "")
            if template.endswith(":ChargeReceipt"):
                contract_id = created.get("contractId")
                logger.info(f"ChargeReceipt created: {contract_id}")
                return contract_id

        # If no ChargeReceipt found, check for any created contract (fallback)
        for event in events:
            created = event.get("CreatedEvent") or event.get("createdEvent", {})
            if created.get("contractId"):
                logger.info(f"Contract created: {created.get('contractId')}")
                return created.get("contractId")

        raise LedgerError("No ChargeReceipt created in response")

    except (LedgerError, CantonBillingError) as e:
        error_str = str(e)
        # If UNKNOWN_INFORMEES, try auto-registration and retry once
        if "unknownInformees" in error_str or "UNKNOWN_INFORMEES" in error_str:
            logger.warning(f"UNKNOWN_INFORMEES for {user_party} - attempting auto-registration")
            registered = await ensure_party_registered(user_party)
            if registered:
                logger.info(f"Party {user_party} confirmed registered, retrying ChargeReceipt")
                try:
                    data = await _make_ledger_request(
                        "POST",
                        "/v2/commands/submit-and-wait-for-transaction",
                        {
                            "commands": {
                                "userId": CANTON_USER_ID,
                                "commandId": f"charge-{request_id}-retry",
                                "actAs": [CANTON_PROVIDER_PARTY],
                                "readAs": [CANTON_PROVIDER_PARTY],
                                "commands": [{
                                    "CreateCommand": {
                                        "templateId": template_id,
                                        "createArguments": {
                                            "provider": CANTON_PROVIDER_PARTY,
                                            "user": user_party,
                                            "tool": tool,
                                            "amount": str(amount),
                                            "requestId": request_id,
                                            "description": description or f"MCP tool: {tool}",
                                            "timestamp": now,
                                        }
                                    }
                                }]
                            }
                        }
                    )
                    events = data.get("transaction", {}).get("events", [])
                    for event in events:
                        created = event.get("CreatedEvent") or event.get("createdEvent", {})
                        template = created.get("templateId", "")
                        if template.endswith(":ChargeReceipt"):
                            contract_id = created.get("contractId")
                            logger.info(f"ChargeReceipt created (after auto-registration): {contract_id}")
                            return contract_id
                    for event in events:
                        created = event.get("CreatedEvent") or event.get("createdEvent", {})
                        if created.get("contractId"):
                            return created.get("contractId")
                except Exception as retry_err:
                    logger.error(f"ChargeReceipt retry after auto-registration failed: {retry_err}")
            else:
                logger.warning(f"Party {user_party} not registered - ChargeReceipt skipped")
        raise
    except Exception as e:
        logger.error(f"Failed to create ChargeReceipt: {e}")
        raise CantonBillingError(f"ChargeReceipt creation error: {e}")


async def query_charges(user_party: str) -> list[ChargeRecord]:
    """
    Query all ChargeReceipt contracts for a user.

    Args:
        user_party: Canton party ID of the user

    Returns:
        List of ChargeRecord objects
    """
    if not CANTON_PROVIDER_PARTY:
        raise CantonBillingError("CANTON_PROVIDER_PARTY not configured")

    template_id = f"{BILLING_PACKAGE_ID}:MCP.Billing:ChargeReceipt"

    logger.info(f"Querying charges for user: {user_party}")

    try:
        # Get current ledger offset
        offset = await get_ledger_offset()

        data = await _make_ledger_request(
            "POST",
            "/v2/state/active-contracts",
            {
                "filter": {
                    "filtersByParty": {
                        CANTON_PROVIDER_PARTY: {
                            "filters": [{
                                "templateFilter": {
                                    "templateId": template_id
                                }
                            }]
                        }
                    }
                },
                "activeAtOffset": offset
            }
        )

        # Handle response format: array of contract entries
        contracts = data if isinstance(data, list) else data.get("activeContracts", [])
        charges = []

        for contract in contracts:
            # Canton 3.4 format: contractEntry.JsActiveContract.createdEvent
            entry = contract.get("contractEntry", {})
            active_contract = entry.get("JsActiveContract") or entry.get("activeContract", {})
            created_event = active_contract.get("createdEvent", {})

            # Note: Canton 3.4 uses "createArgument" (singular), not "createArguments"
            payload = created_event.get("createArgument") or created_event.get("createArguments", {})
            contract_id = created_event.get("contractId", "")
            template_id = created_event.get("templateId", "")

            # Skip non-ChargeReceipt contracts
            if not template_id.endswith(":ChargeReceipt"):
                continue

            # Filter by user party
            if payload.get("user") != user_party:
                continue

            charges.append(ChargeRecord(
                contract_id=contract_id,
                user_party=payload.get("user", ""),
                tool=payload.get("tool", ""),
                amount=float(payload.get("amount", "0")),
                request_id=payload.get("requestId", ""),
                created_at=created_event.get("createdAt", ""),
                description=payload.get("description"),
            ))

        logger.info(f"Found {len(charges)} charges for {user_party}")
        return charges

    except LedgerError:
        raise
    except Exception as e:
        logger.error(f"Failed to query charges: {e}")
        raise CantonBillingError(f"Charge query error: {e}")


async def create_credit_receipt(
    user_party: str,
    amount: float,
    transfer_id: str,
    description: Optional[str] = None,
) -> str:
    """
    Create a CreditReceipt contract on Canton ledger.

    Includes duplicate prevention - if a CreditReceipt already exists
    for this transfer_id, returns the existing contract ID instead
    of creating a duplicate.

    Args:
        user_party: Canton party ID of the user being credited
        amount: Credit amount in CC
        transfer_id: Reference to the transfer (e.g., Canton transaction ID)
        description: Optional description

    Returns:
        Contract ID of the created (or existing) CreditReceipt
    """
    if not CANTON_PROVIDER_PARTY:
        raise CantonBillingError("CANTON_PROVIDER_PARTY not configured")

    # Check for existing credit with same transferId (duplicate prevention)
    existing = await query_credit_by_transfer_id(transfer_id)
    if existing:
        logger.warning(f"Duplicate credit attempt detected for transferId: {transfer_id}")
        logger.info(f"Returning existing CreditReceipt: {existing.contract_id}")
        return existing.contract_id

    template_id = f"{BILLING_PACKAGE_ID}:MCP.Billing:CreditReceipt"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    logger.info(f"Creating CreditReceipt: user={user_party} amount={amount}")

    try:
        # Create CreditReceipt using submit-and-wait-for-transaction
        data = await _make_ledger_request(
            "POST",
            "/v2/commands/submit-and-wait-for-transaction",
            {
                "commands": {
                    "userId": CANTON_USER_ID,
                    "commandId": f"credit-{transfer_id}",
                    "actAs": [CANTON_PROVIDER_PARTY],
                    "readAs": [CANTON_PROVIDER_PARTY],
                    "commands": [{
                        "CreateCommand": {
                            "templateId": template_id,
                            "createArguments": {
                                "provider": CANTON_PROVIDER_PARTY,
                                "user": user_party,
                                "amount": str(amount),
                                "transferId": transfer_id,
                                "description": description or f"Top-up: {amount} CC",
                                "timestamp": now,
                            }
                        }
                    }]
                }
            }
        )

        # Extract CreditReceipt contract ID from transaction response
        events = data.get("transaction", {}).get("events", [])

        for event in events:
            # Canton 3.4 uses "CreatedEvent" (uppercase) in JSON response
            created = event.get("CreatedEvent") or event.get("createdEvent", {})
            template = created.get("templateId", "")
            if template.endswith(":CreditReceipt"):
                contract_id = created.get("contractId")
                logger.info(f"CreditReceipt created: {contract_id}")
                return contract_id

        # If no CreditReceipt found, check for any created contract (fallback)
        for event in events:
            created = event.get("CreatedEvent") or event.get("createdEvent", {})
            if created.get("contractId"):
                logger.info(f"Contract created: {created.get('contractId')}")
                return created.get("contractId")

        raise LedgerError("No CreditReceipt created in response")

    except (LedgerError, CantonBillingError) as e:
        error_str = str(e)
        # If UNKNOWN_INFORMEES, try auto-registration and retry once
        if "unknownInformees" in error_str or "UNKNOWN_INFORMEES" in error_str:
            logger.warning(f"UNKNOWN_INFORMEES for {user_party} - attempting auto-registration")
            registered = await ensure_party_registered(user_party)
            if registered:
                logger.info(f"Party {user_party} confirmed registered, retrying CreditReceipt")
                try:
                    data = await _make_ledger_request(
                        "POST",
                        "/v2/commands/submit-and-wait-for-transaction",
                        {
                            "commands": {
                                "userId": CANTON_USER_ID,
                                "commandId": f"credit-{transfer_id}-retry",
                                "actAs": [CANTON_PROVIDER_PARTY],
                                "readAs": [CANTON_PROVIDER_PARTY],
                                "commands": [{
                                    "CreateCommand": {
                                        "templateId": template_id,
                                        "createArguments": {
                                            "provider": CANTON_PROVIDER_PARTY,
                                            "user": user_party,
                                            "amount": str(amount),
                                            "transferId": transfer_id,
                                            "description": description or f"Top-up: {amount} CC",
                                            "timestamp": now,
                                        }
                                    }
                                }]
                            }
                        }
                    )
                    events = data.get("transaction", {}).get("events", [])
                    for event in events:
                        created = event.get("CreatedEvent") or event.get("createdEvent", {})
                        template = created.get("templateId", "")
                        if template.endswith(":CreditReceipt"):
                            contract_id = created.get("contractId")
                            logger.info(f"CreditReceipt created (after auto-registration): {contract_id}")
                            return contract_id
                    for event in events:
                        created = event.get("CreatedEvent") or event.get("createdEvent", {})
                        if created.get("contractId"):
                            return created.get("contractId")
                except Exception as retry_err:
                    logger.error(f"CreditReceipt retry after auto-registration failed: {retry_err}")
            else:
                logger.warning(f"Party {user_party} not registered - CreditReceipt creation failed")
        raise
    except Exception as e:
        logger.error(f"Failed to create CreditReceipt: {e}")
        raise CantonBillingError(f"CreditReceipt creation error: {e}")


async def query_credits(user_party: str) -> list[CreditRecord]:
    """
    Query all CreditReceipt contracts for a user.

    Args:
        user_party: Canton party ID of the user

    Returns:
        List of CreditRecord objects
    """
    if not CANTON_PROVIDER_PARTY:
        raise CantonBillingError("CANTON_PROVIDER_PARTY not configured")

    template_id = f"{BILLING_PACKAGE_ID}:MCP.Billing:CreditReceipt"

    logger.info(f"Querying credits for user: {user_party}")

    try:
        # Get current ledger offset
        offset = await get_ledger_offset()

        data = await _make_ledger_request(
            "POST",
            "/v2/state/active-contracts",
            {
                "filter": {
                    "filtersByParty": {
                        CANTON_PROVIDER_PARTY: {
                            "filters": [{
                                "templateFilter": {
                                    "templateId": template_id
                                }
                            }]
                        }
                    }
                },
                "activeAtOffset": offset
            }
        )

        # Handle response format: array of contract entries
        contracts = data if isinstance(data, list) else data.get("activeContracts", [])
        credits = []

        for contract in contracts:
            # Canton 3.4 format: contractEntry.JsActiveContract.createdEvent
            entry = contract.get("contractEntry", {})
            active_contract = entry.get("JsActiveContract") or entry.get("activeContract", {})
            created_event = active_contract.get("createdEvent", {})

            # Note: Canton 3.4 uses "createArgument" (singular), not "createArguments"
            payload = created_event.get("createArgument") or created_event.get("createArguments", {})
            contract_id = created_event.get("contractId", "")
            template_id = created_event.get("templateId", "")

            # Skip non-CreditReceipt contracts
            if not template_id.endswith(":CreditReceipt"):
                continue

            # Filter by user party
            if payload.get("user") != user_party:
                continue

            credits.append(CreditRecord(
                contract_id=contract_id,
                user_party=payload.get("user", ""),
                amount=float(payload.get("amount", "0")),
                transfer_id=payload.get("transferId", ""),
                created_at=created_event.get("createdAt", ""),
                description=payload.get("description"),
            ))

        logger.info(f"Found {len(credits)} credits for {user_party}")
        return credits

    except LedgerError:
        raise
    except Exception as e:
        logger.error(f"Failed to query credits: {e}")
        raise CantonBillingError(f"Credit query error: {e}")


async def get_balance(user_party: str) -> BalanceResult:
    """
    Get balance for a user from on-chain data.

    Balance is calculated as: total_credits - total_charges
    Positive balance = user has credit
    Negative balance = user owes money

    Args:
        user_party: Canton party ID

    Returns:
        BalanceResult with total charged, credited, and balance
    """
    # Query both charges and credits in parallel
    charges, credits = await asyncio.gather(
        query_charges(user_party),
        query_credits(user_party),
    )

    total_charged = sum(c.amount for c in charges)
    total_credited = sum(c.amount for c in credits)
    balance = total_credited - total_charged

    logger.info(f"Balance for {user_party}: {balance:.2f} CC (credited: {total_credited:.2f}, charged: {total_charged:.2f})")

    return BalanceResult(
        total_charged=total_charged,
        total_credited=total_credited,
        charges=charges,
        credits=credits,
        balance=balance,
    )


async def query_credit_by_transfer_id(transfer_id: str) -> Optional[CreditRecord]:
    """
    Query for an existing CreditReceipt by transfer_id.

    Used to prevent duplicate credits for the same transfer.

    Args:
        transfer_id: The transfer ID to search for

    Returns:
        CreditRecord if found, None otherwise
    """
    if not CANTON_PROVIDER_PARTY:
        raise CantonBillingError("CANTON_PROVIDER_PARTY not configured")

    template_id = f"{BILLING_PACKAGE_ID}:MCP.Billing:CreditReceipt"

    logger.info(f"Checking for existing credit with transferId: {transfer_id}")

    try:
        # Get current ledger offset
        offset = await get_ledger_offset()

        data = await _make_ledger_request(
            "POST",
            "/v2/state/active-contracts",
            {
                "filter": {
                    "filtersByParty": {
                        CANTON_PROVIDER_PARTY: {
                            "filters": [{
                                "templateFilter": {
                                    "templateId": template_id
                                }
                            }]
                        }
                    }
                },
                "activeAtOffset": offset
            }
        )

        # Handle response format: array of contract entries
        contracts = data if isinstance(data, list) else data.get("activeContracts", [])

        for contract in contracts:
            # Canton 3.4 format: contractEntry.JsActiveContract.createdEvent
            entry = contract.get("contractEntry", {})
            active_contract = entry.get("JsActiveContract") or entry.get("activeContract", {})
            created_event = active_contract.get("createdEvent", {})

            payload = created_event.get("createArgument") or created_event.get("createArguments", {})
            contract_id = created_event.get("contractId", "")
            template_id_check = created_event.get("templateId", "")

            # Skip non-CreditReceipt contracts
            if not template_id_check.endswith(":CreditReceipt"):
                continue

            # Check if transferId matches
            if payload.get("transferId") == transfer_id:
                logger.info(f"Found existing CreditReceipt for transferId {transfer_id}: {contract_id}")
                return CreditRecord(
                    contract_id=contract_id,
                    user_party=payload.get("user", ""),
                    amount=float(payload.get("amount", "0")),
                    transfer_id=payload.get("transferId", ""),
                    created_at=created_event.get("createdAt", ""),
                    description=payload.get("description"),
                )

        logger.info(f"No existing credit found for transferId: {transfer_id}")
        return None

    except LedgerError:
        raise
    except Exception as e:
        logger.error(f"Failed to query credit by transferId: {e}")
        raise CantonBillingError(f"Credit query error: {e}")


async def verify_transfer_on_chain(
    transfer_id: str,
    user_party: str,
    expected_amount: float,
    payee_party: Optional[str] = None,
) -> dict:
    """
    Verify a transfer exists on Canton ledger.

    Queries for TransferPreapproval_Send events to verify the transfer
    was actually executed on-chain.

    Args:
        transfer_id: Canton transaction/update ID
        user_party: Expected payer party ID
        expected_amount: Expected transfer amount
        payee_party: Optional expected payee party (uses CANTON_PROVIDER_PARTY if not specified)

    Returns:
        Dict with verification result:
        {
            "verified": bool,
            "transaction_id": str,
            "amount": float,
            "payer": str,
            "payee": str,
            "timestamp": str,
            "error": str (if not verified)
        }

    Raises:
        CantonBillingError: If ledger query fails
    """
    if not payee_party:
        payee_party = CANTON_PROVIDER_PARTY

    if not payee_party:
        raise CantonBillingError("CANTON_PROVIDER_PARTY not configured and no payee specified")

    logger.info(f"Verifying transfer on-chain: txId={transfer_id}, payer={user_party}, amount={expected_amount}")

    max_retries = 3
    retry_delay = 2.0  # seconds

    try:
        token = await get_oauth_token()

        # Query transaction by ID
        url = f"{CANTON_LEDGER_URL}/v2/updates/transaction-by-id"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = None
            for attempt in range(max_retries + 1):
                response = await client.post(
                    url,
                    headers=headers,
                    json={
                        "updateId": transfer_id,
                        "transactionFormat": {
                            "eventFormat": {
                                "filtersByParty": {
                                    user_party: {"cumulative": []},
                                    payee_party: {"cumulative": []},
                                },
                                "verbose": True,
                            },
                            "transactionShape": "TRANSACTION_SHAPE_LEDGER_EFFECTS",
                        },
                    },
                )

                if response.status_code == 404 and attempt < max_retries:
                    logger.warning(
                        f"Transaction not found (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {retry_delay}s: {transfer_id}"
                    )
                    await asyncio.sleep(retry_delay)
                    continue
                break

            if response.status_code == 404:
                logger.warning(f"Transaction not found after {max_retries + 1} attempts: {transfer_id}")
                return {
                    "verified": False,
                    "error": "Transaction not found on ledger",
                    "transaction_id": transfer_id,
                }

            if response.status_code != 200:
                logger.error(f"Ledger query failed: {response.status_code} {response.text}")
                raise LedgerError(f"Failed to query transaction: {response.status_code}")

            tx_data = orjson.loads(response.content)
            transaction = tx_data.get("transaction")

            if not transaction:
                logger.warning(f"No transaction data in response for: {transfer_id}")
                return {
                    "verified": False,
                    "error": "Transaction not found in response",
                    "transaction_id": transfer_id,
                }

            # Look for TransferPreapproval_Send event
            events = transaction.get("events", [])
            logger.info(f"Found {len(events)} events in transaction {transfer_id}")

            for event in events:
                # Canton uses "ExercisedEvent" (uppercase) in JSON response
                exercised_event = event.get("ExercisedEvent") or event.get("exercisedEvent")
                if not exercised_event:
                    continue

                template_id = exercised_event.get("templateId", "")
                choice = exercised_event.get("choice", "")

                if "TransferPreapproval" in template_id and choice in ("Send", "TransferPreapproval_Send"):
                    args = exercised_event.get("choiceArgument", {})
                    witness_parties = exercised_event.get("witnessParties", [])

                    event_amount_str = args.get("amount", "0")
                    event_amount = float(event_amount_str) if event_amount_str else 0.0

                    logger.info(f"Found TransferPreapproval_Send: amount={event_amount}, witnesses={witness_parties}")

                    # Verify amount matches (allow small floating point tolerance)
                    amount_matches = abs(event_amount - expected_amount) < 0.0001

                    # Verify payee is in witness parties
                    payee_matches = payee_party in witness_parties

                    # Verify payer is in witness parties
                    payer_matches = user_party in witness_parties

                    if amount_matches and payee_matches and payer_matches:
                        logger.info(f"✅ Transfer verified: {transfer_id}")
                        return {
                            "verified": True,
                            "transaction_id": transfer_id,
                            "amount": event_amount,
                            "payer": user_party,
                            "payee": payee_party,
                            "timestamp": transaction.get("effectiveAt", ""),
                        }
                    else:
                        logger.warning(
                            f"Transfer verification mismatch: "
                            f"amount_ok={amount_matches}, payee_ok={payee_matches}, payer_ok={payer_matches}"
                        )

            # No matching transfer found
            logger.warning(f"No matching TransferPreapproval_Send found in transaction {transfer_id}")
            return {
                "verified": False,
                "error": "No matching transfer found in transaction",
                "transaction_id": transfer_id,
            }

    except LedgerError:
        raise
    except Exception as e:
        logger.error(f"Failed to verify transfer: {e}")
        raise CantonBillingError(f"Transfer verification error: {e}")


async def test_connection() -> dict:
    """
    Test Canton ledger connection.

    Returns:
        Dict with connection status
    """
    try:
        await get_oauth_token()  # Verify OAuth credentials work

        # Test connectivity by getting ledger offset
        offset = await get_ledger_offset()

        return {
            "status": "connected",
            "ledger_url": CANTON_LEDGER_URL,
            "provider_party": CANTON_PROVIDER_PARTY,
            "package_id": BILLING_PACKAGE_ID,
            "ledger_offset": offset,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "ledger_url": CANTON_LEDGER_URL,
        }
