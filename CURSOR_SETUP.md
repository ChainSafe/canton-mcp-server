# Cursor Setup for Canton MCP Server

This guide shows you how to configure Cursor to use the Canton MCP server with billing portal integration.

## Overview

Cursor can connect to MCP servers to provide additional tools and capabilities. The Canton MCP server provides:
- Backtest execution tools
- Strategy management
- Payment integration with Canton Coin
- Billing portal for top-ups when balance is low

## Prerequisites

- Cursor IDE installed
- Canton MCP server running (port 5173)
- Canton facilitator running (port 3000)
- Billing portal running (port 3002)

## Step 1: Start Required Services

### 1.1 Start Canton Facilitator
```bash
cd /home/skynet/canton/canton-x402-facilitator
npm run dev
# Should start on port 3000
```

### 1.2 Start Billing Portal
```bash
cd /home/skynet/canton/canton-billing-portal
npm run dev
# Should start on port 3002
```

### 1.3 Start MCP Server
```bash
cd /home/skynet/canton/canton-mcp-server
source .venv/bin/activate
python -m uvicorn src.canton_mcp_server.server:app --reload --port 5173
```

## Step 2: Configure Cursor MCP Settings

Cursor uses a configuration file to connect to MCP servers. There are two ways to configure it:

### Option A: Using Cursor Settings UI (Recommended)

1. **Open Cursor Settings**
   - Press `Cmd/Ctrl + ,` or go to `File > Preferences > Settings`

2. **Navigate to MCP Settings**
   - Search for "MCP" in the settings search bar
   - Or go to `Extensions > MCP Servers`

3. **Add Canton MCP Server**
   - Click "Add MCP Server"
   - Fill in the configuration:

   ```json
   {
     "name": "canton-mcp",
     "url": "http://localhost:5173",
     "description": "Canton MCP Server with payment integration",
     "headers": {
       "X-Canton-Party-ID": "your-canton-party-id-here"
     }
   }
   ```

### Option B: Manual Configuration File

Create or edit Cursor's MCP configuration file:

**Location**: `~/.cursor/mcp_config.json` (or `%APPDATA%\.cursor\mcp_config.json` on Windows)

```json
{
  "mcpServers": [
    {
      "name": "canton-mcp",
      "url": "http://localhost:5173",
      "description": "Canton MCP Server - Backtest execution and strategy management",
      "transport": "sse",
      "headers": {
        "X-Canton-Party-ID": "user-0x123::1220abc...",
        "Content-Type": "application/json"
      },
      "enabled": true
    }
  ]
}
```

**Important**: Replace `"user-0x123::1220abc..."` with your actual Canton party ID.

## Step 3: Get Your Canton Party ID

You need your Canton party ID to authenticate with the MCP server.

### Option 1: From Canton CLI
```bash
# If you have Canton CLI
canton participant participant1 parties list
```

### Option 2: From Facilitator Logs
```bash
# Check facilitator logs when you register
cd /home/skynet/canton/canton-x402-facilitator
# Look for party allocations in the logs
```

### Option 3: From Billing Portal (once OAuth2 is set up)
- Log in to http://localhost:3002
- Your party ID will be displayed on the dashboard

### For Testing (Local Development)
Use the example party from `.env.canton`:
```
app_provider_quickstart-skynet-1::1220de769fb9fa9505bb61fc6fc1e30507829f8179e140645f40e222bc7bcdac21d7
```

## Step 4: Test the Connection

### 4.1 In Cursor
1. Open Cursor
2. Look for the MCP icon in the sidebar (usually bottom left)
3. You should see "canton-mcp" listed
4. Click to connect

### 4.2 Test MCP Tools
In Cursor's chat interface, try:

```
@canton-mcp Get all available strategies
```

Or:
```
Can you show me my backtesting strategies using the MCP server?
```

### 4.3 Verify Connection
```bash
# Check MCP server logs
cd /home/skynet/canton/canton-mcp-server
# You should see connection attempts in the console
```

## Step 5: Configure Payment Integration

### 5.1 Update MCP Server Environment
Edit `/home/skynet/canton/canton-mcp-server/.env.canton`:

```bash
# Canton payments enabled
CANTON_ENABLED=true
CANTON_FACILITATOR_URL=http://localhost:3000
CANTON_PAYEE_PARTY=app_provider_quickstart-skynet-1::1220de769fb9fa9505bb61fc6fc1e30507829f8179e140645f40e222bc7bcdac21d7
CANTON_NETWORK=canton-local

# IMPORTANT: Add billing portal URL
BILLING_PORTAL_URL=http://localhost:3002
```

### 5.2 Restart MCP Server
```bash
# Stop current server (Ctrl+C)
# Start again
python -m uvicorn src.canton_mcp_server.server:app --reload --port 5173
```

## Step 6: Test Payment Flow

### 6.1 Make Requests Until Payment Required
```
# In Cursor chat
@canton-mcp Run a backtest for strategy XYZ
```

Keep making requests until your balance reaches $2.00.

### 6.2 Payment Threshold
When balance >= $2.00, you'll see:
```
Error: Payment required: Your balance is $2.05.
Please top up your account at http://localhost:3002/topup?party=user-0x123::1220abc...
```

### 6.3 Top Up
1. Click the billing portal link
2. Log in (once OAuth2 is configured)
3. Enter amount to top up
4. Complete payment
5. Balance resets, continue using MCP tools

## Troubleshooting

### "Cannot connect to MCP server"

**Check server is running:**
```bash
curl http://localhost:5173/health
# Should return 200 OK
```

**Check party ID:**
```bash
# Verify your party ID is correct in Cursor config
# Should match format: namespace::identifier
```

**Check logs:**
```bash
cd /home/skynet/canton/canton-mcp-server
# Look for connection errors
```

### "Payment required" but I have balance

**Check facilitator:**
```bash
curl "http://localhost:3000/balance?party=YOUR_PARTY_ID"
# Should show your balance
```

**Reset balance (testing):**
```bash
# Restart facilitator to reset in-memory balance
cd /home/skynet/canton/canton-x402-facilitator
npm run dev
```

### "Unauthorized" errors

**Check headers:**
```json
// In Cursor config
"headers": {
  "X-Canton-Party-ID": "your-party-id-here"  // Must be present
}
```

**Verify party exists:**
```bash
# Check Canton party is allocated
canton participant participant1 parties list
```

### Cursor not showing MCP tools

**Reload Cursor:**
- `Cmd/Ctrl + Shift + P` → "Developer: Reload Window"

**Check MCP enabled:**
- Settings → Extensions → MCP Servers → Ensure "canton-mcp" is enabled

**Check configuration file:**
```bash
cat ~/.cursor/mcp_config.json
# Should contain valid JSON
```

## Advanced Configuration

### Using Environment Variables

You can use environment variables in Cursor config:

```json
{
  "mcpServers": [
    {
      "name": "canton-mcp",
      "url": "${CANTON_MCP_URL:http://localhost:5173}",
      "headers": {
        "X-Canton-Party-ID": "${CANTON_PARTY_ID}"
      }
    }
  ]
}
```

Then set in your shell:
```bash
export CANTON_MCP_URL=http://localhost:5173
export CANTON_PARTY_ID=user-0x123::1220abc...
```

### Using Multiple Environments

```json
{
  "mcpServers": [
    {
      "name": "canton-mcp-local",
      "url": "http://localhost:5173",
      "headers": {
        "X-Canton-Party-ID": "local-party-id"
      },
      "enabled": true
    },
    {
      "name": "canton-mcp-testnet",
      "url": "https://mcp.testnet.canton.network",
      "headers": {
        "X-Canton-Party-ID": "testnet-party-id"
      },
      "enabled": false
    }
  ]
}
```

Toggle between environments by enabling/disabling in Cursor settings.

## MCP Server Tools Available

Once connected, you'll have access to:

1. **get_all_strategies** - List available backtest strategies
2. **run_backtest** - Execute a backtest with specific parameters
3. **get_backtest_results** - Retrieve backtest results
4. **create_strategy** - Create a new trading strategy
5. **get_balance** - Check your Canton Coin balance
6. **get_payment_history** - View payment transactions

## Payment Pricing

Tool execution costs are dynamic based on resource usage:
- Simple queries: $0.00 (free)
- Backtest execution: $0.01 - $0.10 (varies by complexity)
- Strategy creation: $0.05

View pricing in real-time at: http://localhost:3002/dashboard

## Next Steps

1. **Get Canton OAuth2 Credentials**
   - Contact Canton Network to register your app
   - Update billing portal `.env` with real credentials
   - Test login flow

2. **Add Real Payment Processing**
   - Integrate with Canton wallet
   - Replace placeholder top-up URL
   - Test end-to-end payment flow

3. **Deploy to Production**
   - Deploy billing portal to Vercel/AWS
   - Update MCP server with production URLs
   - Configure production party IDs

## Support

- **Billing Portal Issues**: http://localhost:3002 (check README.md)
- **MCP Server Issues**: Check `/home/skynet/canton/canton-mcp-server` logs
- **Facilitator Issues**: http://localhost:3000/health

## Quick Reference

```bash
# Start all services
cd /home/skynet/canton/canton-x402-facilitator && npm run dev &
cd /home/skynet/canton/canton-billing-portal && npm run dev &
cd /home/skynet/canton/canton-mcp-server && source .venv/bin/activate && python -m uvicorn src.canton_mcp_server.server:app --reload --port 5173 &

# Check status
curl http://localhost:3000/health  # Facilitator
curl http://localhost:3002         # Billing portal
curl http://localhost:5173/health  # MCP server

# View logs
tail -f /home/skynet/canton/canton-x402-facilitator/logs/*.log
tail -f /home/skynet/canton/canton-mcp-server/logs/*.log

# Stop all services
pkill -f "npm run dev"
pkill -f "uvicorn"
```

That's it! You're ready to use Canton MCP server with Cursor. 🚀
