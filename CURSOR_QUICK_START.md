# Cursor Quick Start - 5 Minutes

Get Cursor connected to Canton MCP Server in 5 minutes!

## Step 1: Start Services (30 seconds)

```bash
# Terminal 1: Facilitator
cd /home/skynet/canton/canton-x402-facilitator
npm run dev  # Port 3000

# Terminal 2: Billing Portal
cd /home/skynet/canton/canton-billing-portal
npm run dev  # Port 3002

# Terminal 3: MCP Server
cd /home/skynet/canton/canton-mcp-server
source .venv/bin/activate
python -m uvicorn src.canton_mcp_server.server:app --reload --port 5173
```

## Step 2: Configure Cursor (2 minutes)

### Option 1: Cursor Settings UI (Easiest)

1. Open Cursor
2. Press `Cmd/Ctrl + ,` (Settings)
3. Search for "MCP"
4. Click "Add MCP Server"
5. Paste this config:

```json
{
  "name": "canton-mcp",
  "url": "http://localhost:5173",
  "headers": {
    "X-Canton-Party-ID": "app_provider_quickstart-skynet-1::1220de769fb9fa9505bb61fc6fc1e30507829f8179e140645f40e222bc7bcdac21d7"
  }
}
```

6. Click Save

### Option 2: Manual Config File

Create `~/.cursor/mcp_config.json`:

```json
{
  "mcpServers": [
    {
      "name": "canton-mcp",
      "url": "http://localhost:5173",
      "transport": "sse",
      "headers": {
        "X-Canton-Party-ID": "app_provider_quickstart-skynet-1::1220de769fb9fa9505bb61fc6fc1e30507829f8179e140645f40e222bc7bcdac21d7"
      },
      "enabled": true
    }
  ]
}
```

## Step 3: Test Connection (1 minute)

1. **Reload Cursor**: `Cmd/Ctrl + Shift + P` → "Developer: Reload Window"

2. **Look for MCP icon** in sidebar (bottom left)

3. **In Cursor chat, type:**
   ```
   @canton-mcp Get all strategies
   ```

4. **Should see response** with available strategies!

## Step 4: Test Payment Flow (2 minutes)

1. **Make requests** until balance hits $2.00:
   ```
   @canton-mcp Run a backtest for RN1
   ```

2. **When you hit threshold**, you'll see:
   ```
   Error: Payment required: Your balance is $2.05.
   Please top up at http://localhost:3002/topup?party=...
   ```

3. **Click link** → Top up page

4. **Enter amount** (e.g., 10 CC) → Continue using MCP

## Troubleshooting

### Can't connect?
```bash
# Check MCP server is running
curl http://localhost:5173/health

# Should return: {"status": "healthy"}
```

### Not seeing tools?
1. Reload Cursor window
2. Check MCP icon shows "connected"
3. Try: `@canton-mcp` in chat

### Payment errors?
```bash
# Check facilitator
curl "http://localhost:3000/balance?party=app_provider_quickstart-skynet-1::1220de769fb9fa9505bb61fc6fc1e30507829f8179e140645f40e222bc7bcdac21d7"

# Should show balance: {"balance": 0, "amountDue": 0, "amountPaid": 0}
```

## Quick Commands

```bash
# Check all services
curl http://localhost:3000/health  # Facilitator
curl http://localhost:3002         # Billing portal
curl http://localhost:5173/health  # MCP server

# View balances
curl "http://localhost:3000/balance?party=app_provider_quickstart-skynet-1::1220de769fb9fa9505bb61fc6fc1e30507829f8179e140645f40e222bc7bcdac21d7"

# Restart everything
pkill -f "npm run dev"
pkill -f uvicorn
# Then start services again
```

## Available MCP Tools

Once connected, use these in Cursor:

- `@canton-mcp Get all strategies` - List strategies
- `@canton-mcp Run backtest for [strategy]` - Execute backtest
- `@canton-mcp Show my balance` - Check Canton Coin balance
- `@canton-mcp Create new strategy` - Build a strategy

## What's Next?

1. **Use MCP tools** in your Cursor workflow
2. **Monitor balance** at http://localhost:3002
3. **Set spending limits** at http://localhost:3002/limits
4. **View transaction history** at http://localhost:3002/transactions

## Full Documentation

- **Complete Setup Guide**: `CURSOR_SETUP.md`
- **Billing Portal**: `/home/skynet/canton/canton-billing-portal/README.md`
- **MCP Server**: `/home/skynet/canton/canton-mcp-server/README.md`

That's it! You're ready to use Canton MCP with Cursor. 🚀
