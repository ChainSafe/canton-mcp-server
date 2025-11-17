# Canton MCP Server - Quick Start Guide

## 🚀 Start the Server (3 Commands)

```bash
# 1. Navigate to project
cd /Users/martinmaurer/Projects/Martin/canton-mcp-server

# 2. Start the server
uv run canton-mcp-server

# 3. Test it works
curl http://localhost:7284/health
```

**Done!** Server is running on `http://localhost:7284`

## 🧪 Test the Tools

### Using curl
```bash
# List available tools
curl -X POST http://localhost:7284/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# Test DAML Reason tool
curl -X POST http://localhost:7284/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "daml_reason",
      "arguments": {
        "businessIntent": "Create a simple IOU",
        "damlCode": "template IOU\n  with\n    issuer: Party\n    owner: Party\n  where\n    signatory issuer"
      }
    }
  }'
```

### Using MCP Inspector (Interactive)
```bash
npx @modelcontextprotocol/inspector http://localhost:7284/mcp
```

## 🔧 Common Commands

```bash
# Stop the server
# Press Ctrl+C (or)
pkill -f canton-mcp-server

# Restart with fresh dependencies
uv sync
uv run canton-mcp-server

# View configuration
cat .env.canton

# Check canonical docs exist
ls /Users/martinmaurer/Projects/Martin/canonical-daml-docs
```

## 📝 Available Tools

| Tool | Description | Price |
|------|-------------|-------|
| `daml_reason` | 🧠 DAML code analyzer and advisor | FREE |
| `daml_automater` | 🤖 CI/CD and environment automation | FREE |

## 🆘 Troubleshooting

**Port already in use:**
```bash
pkill -f canton-mcp-server
```

**Dependencies missing:**
```bash
uv sync
```

**Canonical docs not found:**
```bash
# Clone them if missing
cd /Users/martinmaurer/Projects/Martin
mkdir -p canonical-daml-docs && cd canonical-daml-docs
git clone https://github.com/digital-asset/daml.git
git clone https://github.com/digital-asset/canton.git
git clone https://github.com/digital-asset/daml-finance.git
```

## 📚 More Info

- **Full docs**: `README.md`
- **Recovery status**: `RECOVERY_STATUS.md`
- **Server URL**: `http://localhost:7284`
- **MCP endpoint**: `http://localhost:7284/mcp`
- **Health check**: `http://localhost:7284/health`

---

**That's it!** Your Canton MCP Server is ready to use. 🎉

