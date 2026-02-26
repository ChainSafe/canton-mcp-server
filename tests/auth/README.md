# Challenge-Response Authentication Tests

Tests for the Canton MCP Server's Ed25519 challenge-response authentication system.

## Prerequisites

- MCP Server running on port 7284 (or set `MCP_SERVER` env var)
- Python 3 with PyNaCl installed
- A Canton party key file in `~/.canton/`

## Creating a Test Key

Generate a new test key pair:

```bash
python3 create-test-key.py test-user
```

This creates `~/.canton/test-user-key.json` with:
- `partyId`: Canton party ID with fingerprint
- `publicKey`: Base64-encoded Ed25519 public key
- `privateKey`: Base64-encoded Ed25519 private key
- `fingerprint`: SHA256 hash of public key (1220 prefix)

## Running Tests

### Quick Test (uses first key in ~/.canton/)

```bash
./test-challenge-auth.sh
```

### With Specific Party

```bash
export CANTON_PARTY_ID='alice::1220...'
export CANTON_KEY_FILE='~/.canton/alice-key.json'
./test-challenge-auth.sh
```

### With Custom Server URL

```bash
MCP_SERVER="http://localhost:5173" ./test-challenge-auth.sh
```

## Test Coverage

1. **Request Challenge** - Gets a random nonce from server
2. **Sign Challenge** - Signs nonce with Ed25519 private key
3. **Verify Signature** - Server verifies and returns JWT
4. **Use JWT** - Makes authenticated MCP request
5. **Invalid Signature** - Verifies bad signatures are rejected

## Authentication Flow

```
Client                          Server
  |                               |
  |-- POST /auth/challenge ------>|
  |   {partyId, publicKey?}       |
  |                               |
  |<-- {challenge} ---------------|
  |                               |
  |-- Sign challenge locally -----|
  |                               |
  |-- POST /auth/verify --------->|
  |   {partyId, challenge, sig}   |
  |                               |
  |<-- {token: "JWT..."} ---------|
  |                               |
  |-- POST /mcp ---------------->|
  |   Authorization: Bearer JWT   |
```

## Security Notes

- Challenges expire after 5 minutes
- Each challenge can only be used once
- Public key fingerprint must match party ID
- JWT tokens are valid for 1 hour
