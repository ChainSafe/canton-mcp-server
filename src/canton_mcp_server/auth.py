"""
Cryptographic authentication for Canton MCP Server.

Supports two authentication methods:
1. Challenge-Response (RECOMMENDED): Cryptographic proof via Ed25519 signatures
2. Transaction-Based (DEPRECATED): Legacy authentication using Canton transactions

SECURITY: Challenge-response prevents impersonation attacks by requiring
cryptographic proof of private key ownership.

## DOCUMENTATION ##
- Complete guide: /home/skynet/.claude/skills/canton-mcp-auth.md
- Setup instructions: /home/skynet/canton/CHALLENGE_AUTH_SETUP.md
- Test script: /home/skynet/canton/test-challenge-auth.sh
- Client library: /home/skynet/canton/canton-mcp-client/src/auth.ts

## FLOW ##
1. generate_challenge(party_id, public_key?) → base64 nonce
2. Client signs nonce with Ed25519 private key
3. verify_challenge_signature(party_id, challenge, signature) → bool
4. generate_jwt_token(party_id, auth_method) → JWT
5. verify_jwt_token(token) → claims with party_id

## SECURITY PROPERTIES ##
✅ Cryptographic proof (only key owner can sign)
✅ No public information reuse (random nonces)
✅ Challenge expiry (5 minutes)
✅ Public key verification (against party ID fingerprint)
✅ One-time use (challenges deleted after verification)
✅ Standard JWT tokens (1-hour expiry)
"""

import os
import time
import base64
import hashlib
import secrets
import httpx
import jwt
from typing import Dict, Any, Optional, Set, Tuple
from datetime import datetime, timedelta


class AuthError(Exception):
    """Authentication error"""
    pass


# =============================================================================
# Challenge-Response Authentication (RECOMMENDED)
# =============================================================================

# Challenge store: {party_id: (challenge_bytes, expiry_timestamp)}
_challenge_store: Dict[str, Tuple[bytes, datetime]] = {}
_CHALLENGE_EXPIRY_SECONDS = 300  # 5 minutes

# Public key store: {party_id: public_key_bytes}
# TODO: Replace with database for production multi-instance deployments
_public_key_store: Dict[str, bytes] = {}


def verify_and_store_public_key(party_id: str, public_key_b64: str) -> bytes:
    """
    Verify public key matches party ID fingerprint and store it.

    Canton party IDs are formatted as: name::fingerprint
    Where fingerprint = '1220' + hex(SHA256(publicKey))

    Args:
        party_id: Canton party ID (e.g., "alice::122056ef...")
        public_key_b64: Base64-encoded public key (32 bytes for Ed25519)

    Returns:
        Public key bytes

    Raises:
        AuthError if fingerprint doesn't match
    """
    # Decode public key
    try:
        public_key_bytes = base64.b64decode(public_key_b64)
        if len(public_key_bytes) != 32:
            raise AuthError(
                f"Invalid public key length: expected 32 bytes, got {len(public_key_bytes)}"
            )
    except Exception as e:
        raise AuthError(f"Invalid public key encoding: {e}")

    # Extract fingerprint from party ID
    if "::" not in party_id:
        raise AuthError("Invalid party ID format: missing '::'")

    name, fingerprint = party_id.split("::", 1)

    # Verify fingerprint matches public key using Canton's algorithm:
    # Canton fingerprint = SHA256(hashPurpose_12 || rawPublicKey)
    # Where hashPurpose = 12 as 4-byte big-endian (0x0000000c)
    HASH_PURPOSE_PUBLIC_KEY_FINGERPRINT = 12
    hash_purpose = HASH_PURPOSE_PUBLIC_KEY_FINGERPRINT.to_bytes(4, byteorder='big')
    computed_hash = hashlib.sha256(hash_purpose + public_key_bytes).hexdigest()
    expected_fingerprint = "1220" + computed_hash  # '1220' is multihash prefix for SHA-256

    if fingerprint != expected_fingerprint:
        raise AuthError(
            f"Public key fingerprint mismatch. "
            f"Expected {expected_fingerprint}, got {fingerprint}. "
            f"This public key does not belong to party {party_id}"
        )

    # Store for future use
    _public_key_store[party_id] = public_key_bytes

    return public_key_bytes


def get_stored_public_key(party_id: str) -> bytes:
    """Get previously verified public key for party."""
    if party_id not in _public_key_store:
        raise AuthError(
            f"No public key on file for party {party_id}. "
            "Please provide your public key for first-time authentication."
        )
    return _public_key_store[party_id]


def generate_challenge(party_id: str, public_key_b64: Optional[str] = None) -> str:
    """
    Generate a random challenge (nonce) for party to sign.

    Args:
        party_id: Canton party ID
        public_key_b64: Optional public key for first-time authentication

    Returns:
        Base64-encoded challenge bytes
    """
    # If public key provided, verify and store it
    if public_key_b64:
        verify_and_store_public_key(party_id, public_key_b64)

    # Generate 32-byte random challenge
    challenge_bytes = secrets.token_bytes(32)

    # Store with expiry
    expiry = datetime.utcnow() + timedelta(seconds=_CHALLENGE_EXPIRY_SECONDS)
    _challenge_store[party_id] = (challenge_bytes, expiry)

    # Clean up expired challenges
    now = datetime.utcnow()
    expired_parties = [
        pid for pid, (_, exp) in _challenge_store.items() if exp < now
    ]
    for pid in expired_parties:
        del _challenge_store[pid]

    return base64.b64encode(challenge_bytes).decode("ascii")


async def verify_challenge_signature(
    party_id: str, challenge_b64: str, signature_b64: str
) -> bool:
    """
    Verify that the signature was created by the party's private key.

    Args:
        party_id: Canton party ID
        challenge_b64: Base64-encoded challenge that was signed
        signature_b64: Base64-encoded Ed25519 signature (64 bytes)

    Returns:
        True if signature is valid

    Raises:
        AuthError if verification fails
    """
    # Import here to avoid dependency issues if PyNaCl not installed
    try:
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError
    except ImportError:
        raise AuthError(
            "PyNaCl not installed. Install with: pip install pynacl>=1.5.0"
        )

    # 1. Check challenge exists and hasn't expired
    if party_id not in _challenge_store:
        raise AuthError("No challenge found for this party. Request a challenge first.")

    stored_challenge, expiry = _challenge_store[party_id]

    if datetime.utcnow() > expiry:
        del _challenge_store[party_id]
        raise AuthError("Challenge expired. Request a new challenge.")

    # 2. Verify challenge matches
    challenge_bytes = base64.b64decode(challenge_b64)
    if challenge_bytes != stored_challenge:
        raise AuthError("Challenge mismatch")

    # 3. Decode signature
    try:
        signature_bytes = base64.b64decode(signature_b64)
        if len(signature_bytes) != 64:
            raise AuthError(
                f"Invalid signature length: expected 64 bytes, got {len(signature_bytes)}"
            )
    except Exception as e:
        raise AuthError(f"Invalid signature encoding: {e}")

    # 4. Get party's stored public key
    try:
        public_key_bytes = get_stored_public_key(party_id)
    except AuthError:
        # Should not happen if challenge was issued correctly
        raise AuthError(
            "No public key on file. Request a new challenge with your public key."
        )

    # 5. Verify signature using Ed25519
    try:
        verify_key = VerifyKey(public_key_bytes)
        verify_key.verify(challenge_bytes, signature_bytes)

        # Signature valid - remove challenge (one-time use)
        del _challenge_store[party_id]

        return True

    except BadSignatureError:
        raise AuthError("Invalid signature: signature verification failed")
    except Exception as e:
        raise AuthError(f"Signature verification error: {e}")


# =============================================================================
# Transaction-Based Authentication (DEPRECATED - For Backward Compatibility)
# =============================================================================

# In-memory store of used transaction IDs for replay prevention
# TODO: Replace with Redis or database for production multi-instance deployments
_used_transaction_ids: Set[str] = set()
_MAX_USED_TXS = 10000  # Limit memory usage

# Maximum age for authentication transactions (10 minutes)
_AUTH_TX_MAX_AGE_SECONDS = 600


async def verify_canton_transaction(
    transaction_id: str,
    party_id: str,
    facilitator_url: str
) -> bool:
    """
    Verify a Canton transaction exists on-chain and was signed by the party.

    Includes replay prevention:
    - Each transaction can only be used ONCE for authentication
    - Transaction must be recent (within last 10 minutes)

    Args:
        transaction_id: Canton transaction ID from ledger
        party_id: Party ID that should be the payer
        facilitator_url: Facilitator base URL

    Returns:
        True if transaction is valid and party is the payer

    Raises:
        AuthError if verification fails or transaction already used
    """
    # Check replay prevention FIRST (before expensive ledger query)
    if transaction_id in _used_transaction_ids:
        raise AuthError(
            "Transaction already used for authentication. "
            "Each transaction can only authenticate once. "
            "Please make a fresh payment to authenticate again."
        )

    try:
        # Call facilitator's check-payment-status endpoint
        # This queries the Canton ledger and validates the transaction
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{facilitator_url}/check-payment-status",
                params={
                    "transactionId": transaction_id,
                    "party": party_id
                }
            )

            if response.status_code == 404:
                raise AuthError("Transaction not found on Canton ledger")

            if response.status_code != 200:
                raise AuthError(f"Facilitator error: {response.status_code}")

            data = response.json()

            # Check if transaction was found and verified
            if not data.get("hasPaid"):
                raise AuthError("Transaction not verified or party mismatch")

            # Check transaction age (if timestamp provided by facilitator)
            tx_timestamp = data.get("recordTime")
            if tx_timestamp:
                try:
                    tx_time = datetime.fromisoformat(tx_timestamp.replace('Z', '+00:00'))
                    age_seconds = (datetime.now(tx_time.tzinfo) - tx_time).total_seconds()

                    if age_seconds > _AUTH_TX_MAX_AGE_SECONDS:
                        raise AuthError(
                            f"Transaction too old ({int(age_seconds)}s ago). "
                            f"For authentication, transaction must be within last {_AUTH_TX_MAX_AGE_SECONDS}s. "
                            "Please make a fresh payment."
                        )
                except (ValueError, TypeError) as e:
                    # If timestamp parsing fails, log but don't block (backward compatibility)
                    import logging
                    logging.warning(f"Failed to parse transaction timestamp: {e}")

            # Mark transaction as used (replay prevention)
            _used_transaction_ids.add(transaction_id)

            # Limit memory usage by removing old entries
            if len(_used_transaction_ids) > _MAX_USED_TXS:
                # Remove oldest 10% of entries (simple FIFO)
                to_remove = list(_used_transaction_ids)[:_MAX_USED_TXS // 10]
                for tx_id in to_remove:
                    _used_transaction_ids.discard(tx_id)

            return True

    except httpx.RequestError as e:
        raise AuthError(f"Failed to query Canton ledger: {e}")


def generate_jwt_token(party_id: str, auth_method: str) -> str:
    """
    Generate JWT token after successful authentication.

    Args:
        party_id: Verified Canton party ID
        auth_method: Authentication method used (e.g., "challenge-response", "transaction-<txid>")

    Returns:
        JWT token string
    """
    jwt_secret = os.getenv("JWT_SECRET")
    if not jwt_secret:
        raise AuthError("JWT_SECRET not configured")

    now = int(time.time())
    payload = {
        "sub": party_id,
        "iat": now,
        "exp": now + 3600,  # 1 hour expiry
        "iss": "canton-mcp-server",
        "aud": "canton-mcp",
        "auth_method": auth_method,
        "verified_at": now,
    }

    return jwt.encode(payload, jwt_secret, algorithm="HS256")


def verify_jwt_token(token: str) -> Dict[str, Any]:
    """
    Verify and decode JWT token.

    Returns:
        Decoded claims including party_id in "sub" field

    Raises:
        AuthError if token invalid or expired
    """
    jwt_secret = os.getenv("JWT_SECRET")
    if not jwt_secret:
        raise AuthError("JWT_SECRET not configured")

    try:
        claims = jwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256"],
            audience="canton-mcp",
            issuer="canton-mcp-server"
        )
        return claims
    except jwt.ExpiredSignatureError:
        raise AuthError("Token expired - please authenticate again")
    except jwt.InvalidTokenError as e:
        raise AuthError(f"Invalid token: {e}")


def extract_party_from_jwt(token: str) -> str:
    """
    Extract party ID from JWT token.

    Returns:
        Canton party ID from "sub" claim
    """
    claims = verify_jwt_token(token)
    return claims["sub"]
