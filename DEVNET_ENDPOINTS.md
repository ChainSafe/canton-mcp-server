# DevNet Endpoints Quick Reference

## 🔄 Endpoint Migration Map

### OAuth2 Authentication

| Variable | Localnet | DevNet |
|----------|----------|--------|
| `CANTON_OAUTH_TOKEN_URL` | `http://localhost:8082/realms/AppProvider/protocol/openid-connect/token` | `https://dev-2j3m40ajwym1zzaq.eu.auth0.com/oauth/token` |
| `CANTON_OAUTH_CLIENT_ID` | `app-provider-validator` | **YOUR_AUTH0_CLIENT_ID** (get from ChainSafe) |
| `CANTON_OAUTH_CLIENT_SECRET` | `AL8648b9SfdTFImq7FV56Vd0KHifHBuC` | **YOUR_AUTH0_CLIENT_SECRET** (get from ChainSafe) |
| `CANTON_OAUTH_AUDIENCE` | `https://canton.network.global` | `https://canton.network.global` (same) |

### Canton Ledger API (JSON API v2)

| Variable | Localnet | DevNet |
|----------|----------|--------|
| `CANTON_LEDGER_URL` | `http://localhost:3975` | `https://canton-ledger-api-http-dev1.01.chainsafe.dev/api/json-api` |
| `LEDGER_URL` | `http://localhost:3975` | `https://canton-ledger-api-http-dev1.01.chainsafe.dev/api/json-api` |

### Validator / Token Standard API

| Variable | Localnet | DevNet |
|----------|----------|--------|
| `TOKEN_STANDARD_URL` | `http://localhost:3903/api/validator/v0/scan-proxy` | `https://wallet-validator-dev1.01.chainsafe.dev/api/validator/v0/scan-proxy` |
| `VALIDATOR_API_URL` | `http://localhost:3903/api/validator` | `https://wallet-validator-dev1.01.chainsafe.dev/api/validator` |
| `CANTON_SCAN_PROXY_URL` | `http://scan.localhost:4000` | `https://wallet-validator-dev1.01.chainsafe.dev/api/validator/v0/scan-proxy` |

### Network Configuration

| Variable | Localnet | DevNet |
|----------|----------|--------|
| `CANTON_NETWORK` | `canton-local` | `canton-devnet` |
| `CANTON_DSO_PARTY` | `DSO::122047eef66db8287c720e7341327610d5601a508b5164675b18012adf47db7eda1d` | `DSO::1220be58c29e65de40bf273be1dc2b266d43a9a002ea5b18955aeef7aac881bb471a` |

### Facilitator (x402 Payments)

| Variable | Localnet | DevNet |
|----------|----------|--------|
| `CANTON_FACILITATOR_URL` | `http://localhost:3001` | `http://46.224.109.63:3000` (your public facilitator) |
| `FACILITATOR_URL` | `http://localhost:3001` | `http://46.224.109.63:3000` |

### Your Party IDs (Update These!)

| Variable | Localnet | DevNet |
|----------|----------|--------|
| `CANTON_PAYEE_PARTY` | `app_provider_quickstart-skynet-1::1220be93...` | **YOUR_DEVNET_PARTY::1220...** |
| `CANTON_PROVIDER_PARTY` | `app_provider_quickstart-skynet-1::1220be93...` | **YOUR_DEVNET_PARTY::1220...** |
| `APP_PROVIDER_PARTY` | `app_provider_quickstart-skynet-1::1220be93...` | **YOUR_DEVNET_PARTY::1220...** |

### Canton User ID

| Variable | Localnet | DevNet |
|----------|----------|--------|
| `CANTON_USER_ID` | `c87743ab-80e0-4b83-935a-4c0582226691` (from Keycloak) | **YOUR_AUTH0_USER_ID** (may be same as client ID) |
| `CANTON_API_USER_ID` | `app-provider-validator` | **YOUR_AUTH0_CLIENT_ID** (for client_credentials flow) |

### Package IDs (After DAR Upload)

| Variable | Localnet | DevNet |
|----------|----------|--------|
| `BILLING_PACKAGE_ID` | `a131f642bb6d2f65534bc300a9cc2975e927d7fdc102a82cc2a02420cc594801` | **YOUR_DEVNET_PACKAGE_ID** (deploy DAR first) |
| `CHARGE_RECEIPT_PACKAGE_ID` | `1cdb79cf535e8fdd0b1ae677ddf7a534f6d343a1a8811b88cf19e00ffbcf2c0` | **YOUR_DEVNET_PACKAGE_ID** |

### Domain/Synchronizer IDs

| Variable | Localnet | DevNet |
|----------|----------|--------|
| `SYNCHRONIZER_ID` | `global-domain::122047eef66db8287c720e7341327610d5601a508b5164675b18012adf47db7eda1d` | **ASK_CHAINSAFE** (DevNet synchronizer ID) |
| `DOMAIN_ID` | `global-domain::122047eef66db8287c720e7341327610d5601a508b5164675b18012adf47db7eda1d` | **ASK_CHAINSAFE** (DevNet domain ID) |

## 🗑️ Variables to Remove for DevNet

These are localnet-only and should be removed or set to `false`:

```bash
# Remove these from DevNet .env:
NEXT_PUBLIC_IS_LOCALNET=false  # Change from true
CANTON_WALLET_URL=              # Remove (no local wallet)
KEYCLOAK_URL=                   # Remove (using Auth0 instead)
USE_CANTON_34_FLOW=false        # Keep false
CANTON_PARTICIPANT_ADMIN_API=   # Remove (no direct gRPC access)
PARTICIPANT_ID=                 # Remove (not running participant)
```

## 📋 DevNet-Only Variables to Add

```bash
# Add these for DevNet if not present:
CANTON_OAUTH_AUDIENCE=https://canton.network.global
X402_ENABLED=true  # Enable x402 payments via facilitator
```

## 🧪 Testing Endpoints

### Test OAuth2 Token Acquisition

```bash
curl -X POST https://dev-2j3m40ajwym1zzaq.eu.auth0.com/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "client_credentials",
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "audience": "https://canton.network.global"
  }'
```

Expected: `{"access_token": "eyJ...", "token_type": "Bearer", "expires_in": 86400}`

### Test Canton Ledger API

```bash
TOKEN="your-token-from-above"
curl -X POST https://canton-ledger-api-http-dev1.01.chainsafe.dev/api/json-api/v2/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "templateId": "Splice.Amulet:Amulet",
    "query": {"owner": "YOUR_PARTY"}
  }'
```

Expected: List of contracts (may be empty if you have no holdings)

### Test Validator API

```bash
curl -X GET https://wallet-validator-dev1.01.chainsafe.dev/api/validator/v0/scan-proxy/parties/YOUR_PARTY \
  -H "Authorization: Bearer $TOKEN"
```

Expected: Party details if registered

### Test Facilitator

```bash
curl -X POST http://46.224.109.63:3000/payment-object \
  -H "Content-Type: application/json" \
  -d '{
    "payer": "PAYER_PARTY",
    "payee": "YOUR_PARTY",
    "amount": "1.0",
    "resource": "test"
  }'
```

Expected: Payment object with `factoryId` and `choiceContext`

## 🔐 Where to Get Credentials

### Auth0 Credentials
1. **Contact ChainSafe**: Ask for DevNet OAuth2 credentials
2. **Or** login to your Auth0 account at https://manage.auth0.com
3. Go to Applications → Your Application
4. Copy Client ID and Client Secret

### Party IDs
1. **Via Canton Wallet UI**:
   - Go to ChainSafe Canton Wallet (DevNet)
   - Login/create account
   - Party shown in UI
2. **Via Validator API**: POST to `/api/validator/v0/parties` with party hint
3. **Via Scripts**: Use `/home/skynet/canton/canton-x402-facilitator/scripts/create-external-party.ts`

### Package IDs
1. Build your DAR: `daml build`
2. Upload to DevNet (contact ChainSafe for upload process)
3. Package ID = SHA256 hash of DAR contents
4. Format: `<64-hex-chars>`

## 📚 API Documentation

- **Canton JSON API v2**: https://docs.daml.com/json-api/index.html
- **Token Standard API**: Ask ChainSafe for OpenAPI spec
- **Validator API**: Ask ChainSafe for documentation
- **Auth0 OAuth2**: https://auth0.com/docs/api/authentication

## 🆘 Common Error Codes

| Error | Cause | Solution |
|-------|-------|----------|
| `401 Unauthorized` | Invalid OAuth2 token | Check client ID/secret, get new token |
| `403 Forbidden` | User lacks permissions | Verify `CANTON_USER_ID` has actAs rights for party |
| `404 Not Found - PARTY_NOT_KNOWN_ON_DOMAIN` | Party not registered | Register party via wallet or validator API |
| `404 Not Found - TEMPLATES_OR_INTERFACES_NOT_FOUND` | Package not uploaded | Upload DAR to DevNet |
| `GRPC_ERROR` with localnet endpoints | Using wrong config | Switch to DevNet endpoints |
| Token expired | Token > 24 hours old | Request new token from Auth0 |

## 🔄 Quick Migration Script

```bash
#!/bin/bash
# migrate-to-devnet.sh

cd /home/skynet/canton/canton-mcp-server

# Backup current config
cp .env.canton .env.canton.localnet.backup

# Copy DevNet template
cp .env.canton.devnet .env.canton

echo "✅ Created .env.canton for DevNet"
echo ""
echo "⚠️  You MUST update these values:"
echo "   - CANTON_OAUTH_CLIENT_ID"
echo "   - CANTON_OAUTH_CLIENT_SECRET"
echo "   - CANTON_USER_ID"
echo "   - CANTON_PAYEE_PARTY"
echo "   - CANTON_PROVIDER_PARTY"
echo "   - BILLING_PACKAGE_ID (if using on-chain billing)"
echo ""
echo "📖 See DEVNET_MIGRATION_GUIDE.md for detailed steps"
```

Make executable: `chmod +x migrate-to-devnet.sh`
