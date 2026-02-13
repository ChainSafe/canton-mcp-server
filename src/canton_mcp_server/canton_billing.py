"""
Canton On-Chain Billing

Creates ChargeReceipt contracts on Canton ledger after tool execution.
Queries ChargeReceipts to compute balance.

Uses OAuth2 client credentials flow to authenticate with Canton JSON API.
Uses submit-and-wait for write operations (provider is a local party with keys
managed by the Canton participant).
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Environment configuration
CANTON_LEDGER_URL = os.getenv("CANTON_LEDGER_URL", "http://localhost:3975")
CANTON_OAUTH_TOKEN_URL = os.getenv(
    "CANTON_OAUTH_TOKEN_URL",
    "http://localhost:8082/realms/AppProvider/protocol/openid-connect/token"
)
CANTON_OAUTH_CLIENT_ID = os.getenv("CANTON_OAUTH_CLIENT_ID", "app-provider-validator")
CANTON_OAUTH_CLIENT_SECRET = os.getenv("CANTON_OAUTH_CLIENT_SECRET", "")
CANTON_PROVIDER_PARTY = os.getenv("CANTON_PROVIDER_PARTY", "")
# Canton user ID (UUID) - different from OAuth client ID
# This is the user ID registered in Canton's User Management service
CANTON_USER_ID = os.getenv("CANTON_USER_ID", "")
BILLING_PACKAGE_ID = os.getenv(
    "BILLING_PACKAGE_ID",
    "1cdb79cf535e8fdd0b1ae677ddf7a534f6d343a1a8811b88cf19e00ffbcef2c0"
)

# Token cache
_token_cache: dict = {"token": None, "expires_at": 0}

# ChargeManager contract cache
_charge_manager_cache: dict = {"contract_id": None, "timestamp": 0}
CACHE_TTL = 5 * 60  # 5 minutes


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


async def get_oauth_token() -> str:
    """
    Get OAuth2 access token for Canton JSON API.

    Uses client_credentials flow with Keycloak.
    Tokens are cached until near expiry.
    """
    global _token_cache

    # Check cache
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    if not CANTON_OAUTH_CLIENT_SECRET:
        raise OAuthError("CANTON_OAUTH_CLIENT_SECRET not configured")

    logger.info(f"Fetching OAuth token from {CANTON_OAUTH_TOKEN_URL}")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                CANTON_OAUTH_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": CANTON_OAUTH_CLIENT_ID,
                    "client_secret": CANTON_OAUTH_CLIENT_SECRET,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                error_text = response.text
                logger.error(f"OAuth token request failed: {response.status_code} {error_text}")
                raise OAuthError(f"Failed to get OAuth token: {response.status_code} {error_text}")

            data = response.json()
            token = data["access_token"]
            expires_in = data.get("expires_in", 3600)

            _token_cache = {
                "token": token,
                "expires_at": time.time() + expires_in,
            }

            logger.info(f"OAuth token obtained, expires in {expires_in}s")
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
                logger.error(f"Ledger 403 Forbidden: {response.text}")
                raise LedgerError(f"Access denied to Canton API: {response.text}")

            if response.status_code not in (200, 201):
                logger.error(f"Ledger error {response.status_code}: {response.text}")
                raise LedgerError(f"Ledger API error: {response.status_code} {response.text}")

            return response.json()

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

    except LedgerError:
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

    except LedgerError:
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

    try:
        token = await get_oauth_token()

        # Query transaction by ID
        url = f"{CANTON_LEDGER_URL}/v2/updates/transaction-by-id"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
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

            if response.status_code == 404:
                logger.warning(f"Transaction not found: {transfer_id}")
                return {
                    "verified": False,
                    "error": "Transaction not found on ledger",
                    "transaction_id": transfer_id,
                }

            if response.status_code != 200:
                logger.error(f"Ledger query failed: {response.status_code} {response.text}")
                raise LedgerError(f"Failed to query transaction: {response.status_code}")

            tx_data = response.json()
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
        token = await get_oauth_token()

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
