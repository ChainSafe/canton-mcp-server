# DevNet Migration Guide

This guide explains how to migrate the Canton MCP Server from localnet (cn-quickstart) to DevNet (ChainSafe).

## Key Differences: Localnet vs DevNet

| Component | Localnet (cn-quickstart) | DevNet (ChainSafe) |
|-----------|-------------------------|-------------------|
| **OAuth2** | Keycloak @ `localhost:8082` | Auth0 @ `dev-2j3m40ajwym1zzaq.eu.auth0.com` |
| **Ledger API** | `http://localhost:3975` | `https://canton-ledger-api-http-dev1.01.chainsafe.dev/api/json-api` |
| **Validator API** | `http://localhost:3903` | `https://wallet-validator-dev1.01.chainsafe.dev/api/validator` |
| **DSO Party** | Local DSO (quickstart) | `DSO::1220be58c29e65de40bf273be1dc2b266d43a9a002ea5b18955aeef7aac881bb471a` |
| **Network ID** | `canton-local` | `canton-devnet` |
| **Authentication** | Service account + OAuth2 client credentials | Auth0 OAuth2 client credentials |

## Step-by-Step Migration

### 1. Get DevNet Credentials

You need Auth0 OAuth2 credentials to access ChainSafe DevNet:

**Contact ChainSafe** to get:
- `CANTON_OAUTH_CLIENT_ID` - Your Auth0 client ID
- `CANTON_OAUTH_CLIENT_SECRET` - Your Auth0 client secret
- `CANTON_USER_ID` - Your Canton user ID (may be same as client ID)

**Or** if you have existing DevNet access:
- Check your Auth0 account for existing applications
- Use credentials from your ChainSafe DevNet account

### 2. Register Your Party on DevNet

You need a party on DevNet to receive payments. Options:

#### Option A: Via Canton Wallet (Recommended)
1. Go to ChainSafe Canton Wallet (DevNet instance)
2. Create an account or login
3. Your party ID will be shown in the wallet UI
4. Format: `your-party-name::1220<fingerprint>`

#### Option B: Via Validator API
```bash
# Using the validator API to create an external party
curl -X POST https://wallet-validator-dev1.01.chainsafe.dev/api/validator/v0/parties \
  -H "Authorization: Bearer <auth0-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "partyHint": "damlcopilot-receiver",
    "displayName": "DAML Copilot Receiver"
  }'
```

#### Option C: Programmatically
See `/home/skynet/canton/canton-x402-facilitator/scripts/create-external-party.ts` for example code.

### 3. Deploy Your DAR to DevNet

If you're using on-chain billing with `ChargeReceipt` contracts:

```bash
# 1. Build your DAR
cd /path/to/your/daml/project
daml build

# 2. Upload to DevNet (need to implement this)
# Use Canton Console or participant admin API
# This will give you the BILLING_PACKAGE_ID
```

**Note**: Package upload on DevNet may require coordination with ChainSafe or use of their deployment tools.

### 4. Update Environment Variables

Copy the template:
```bash
cd /home/skynet/canton/canton-mcp-server
cp .env.canton.devnet .env.canton
```

Update these values in `.env.canton`:

#### Required Changes:
1. **OAuth2 Credentials** (from Step 1):
   ```bash
   CANTON_OAUTH_CLIENT_ID=your-auth0-client-id
   CANTON_OAUTH_CLIENT_SECRET=your-auth0-client-secret
   CANTON_USER_ID=your-canton-user-id
   ```

2. **Your Party IDs** (from Step 2):
   ```bash
   CANTON_PAYEE_PARTY=your-party::1220...
   CANTON_PROVIDER_PARTY=your-party::1220...
   ```

3. **Package ID** (from Step 3, if using on-chain billing):
   ```bash
   BILLING_PACKAGE_ID=your-package-id
   ```

4. **Billing Portal URL** (if you have a devnet instance):
   ```bash
   BILLING_PORTAL_URL=https://your-devnet-billing-portal.com
   ```
   Or comment out if not using:
   ```bash
   # BILLING_PORTAL_URL=http://localhost:3050
   ```

#### Already Configured (from template):
- ✅ `CANTON_LEDGER_URL` - ChainSafe DevNet ledger API
- ✅ `CANTON_OAUTH_TOKEN_URL` - Auth0 token endpoint
- ✅ `CANTON_DSO_PARTY` - DevNet DSO party
- ✅ `CANTON_NETWORK=canton-devnet`
- ✅ `TOKEN_STANDARD_URL` - ChainSafe validator API

### 5. Test Authentication

Verify OAuth2 credentials work:

```bash
# Get Auth0 token
curl -X POST https://dev-2j3m40ajwym1zzaq.eu.auth0.com/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "client_credentials",
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "audience": "https://canton.network.global"
  }'
```

If successful, you'll get:
```json
{
  "access_token": "eyJhbGc...",
  "token_type": "Bearer",
  "expires_in": 86400
}
```

### 6. Test Canton Ledger API Access

Verify you can query the ledger:

```bash
# Set your token
TOKEN="your-auth0-token-from-step-5"

# Query parties
curl -X POST https://canton-ledger-api-http-dev1.01.chainsafe.dev/api/json-api/v2/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "templateId": "DA.Types:Tuple2",
    "query": {}
  }'
```

### 7. Start the MCP Server

```bash
cd /home/skynet/canton/canton-mcp-server
python -m canton_mcp_server.server
```

Check logs for:
- ✅ OAuth2 token acquisition successful
- ✅ Canton ledger connection successful
- ✅ Party registration/verification successful

### 8. Test End-to-End Payment

Use the facilitator to test a payment:

```bash
cd /home/skynet/canton/canton-x402-facilitator
# Update .env with devnet settings
npm run test:payment
```

Or use the MCP client:
```bash
cd /home/skynet/canton/canton-mcp-client
node dist/pay.js daml_automater "spin up canton network"
```

## Common Issues

### "401 Unauthorized" from Canton API
- ❌ Check `CANTON_OAUTH_CLIENT_ID` and `CANTON_OAUTH_CLIENT_SECRET`
- ❌ Verify token URL is correct
- ❌ Check token hasn't expired (1 hour default)
- ❌ Ensure `CANTON_USER_ID` matches your Auth0 user

### "Party not found" errors
- ❌ Verify party exists on DevNet (not just localnet)
- ❌ Check party format: `name::1220<fingerprint>`
- ❌ Ensure party is registered on the correct participant

### "Package not found" errors
- ❌ Verify DAR is deployed to DevNet
- ❌ Check `BILLING_PACKAGE_ID` matches deployed package
- ❌ Ensure package is vetted on your participant

### OAuth2 token expired quickly
- ❌ Auth0 tokens typically last 24 hours
- ❌ Implement token refresh logic in your client
- ❌ The MCP server should auto-refresh tokens

### Cannot create party on DevNet
- ❌ Party creation on DevNet may require ChainSafe approval
- ❌ Use the Canton Wallet UI to create parties (easier)
- ❌ Contact ChainSafe support for participant access

## What You Don't Need to Change

These stay the same:
- ✅ `JWT_SECRET` - Keep your existing secret for MCP authentication
- ✅ `BILLING_API_KEY` - Keep for billing portal authentication
- ✅ `MIN_BALANCE_THRESHOLD` - Same billing logic
- ✅ `MCP_SERVER_URL` - Still runs on localhost

## Network Comparison

### Localnet (cn-quickstart)
**Pros:**
- Fast setup with Docker Compose
- Full control over all components
- Easy debugging (logs accessible)
- Can reset/restart anytime
- Free test tokens via faucet

**Cons:**
- Not persistent (data lost on restart)
- Not accessible to external users
- Manual party registration
- No production readiness

### DevNet (ChainSafe)
**Pros:**
- Persistent state
- Shared with other developers
- Production-like environment
- Professional infrastructure
- Real network conditions

**Cons:**
- Requires OAuth2 credentials
- Cannot reset state easily
- Party creation may need approval
- Rate limiting on APIs
- Costs for Canton Coin (if not using faucet)

## Next Steps After Migration

1. **Test all payment flows** - Ensure charges work end-to-end
2. **Monitor logs** - Watch for OAuth2 token refresh, API errors
3. **Update billing portal** - Point to DevNet if needed
4. **Document party IDs** - Keep a record of your DevNet parties
5. **Setup monitoring** - Track API usage, payment success rates

## References

- **Canton x402 SDK DevNet Config**: `/home/skynet/canton/canton-x402-sdk/.env.example`
- **Facilitator DevNet Template**: `/home/skynet/canton/canton-x402-facilitator/env.production.template`
- **Billing Portal DevNet Config**: `/home/skynet/canton/canton-billing-portal/.env`
- **ChainSafe DevNet Docs**: Contact ChainSafe for official documentation
- **Auth0 Docs**: https://auth0.com/docs/api/authentication

## Support

If you encounter issues:
1. Check the error messages in MCP server logs
2. Verify all credentials are correct
3. Test OAuth2 token acquisition separately
4. Contact ChainSafe for DevNet-specific issues
5. Open issue in canton-mcp-server repo for bugs
