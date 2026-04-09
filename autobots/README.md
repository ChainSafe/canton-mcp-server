# Autobots — Liveliness & E2E Load Testing

Testing agent for the Canton MCP Server. Generates real transactions (ChargeReceipts), surfaces issues, and validates server behavior 24/7.

## Quick Start

```bash
cd canton-mcp-server/autobots

# Run once against devnet
node runner.js --key ~/.canton/test-billing-user-key.json --server https://mcp-dev1.01.chainsafe.dev

# Run once against mainnet
node runner.js --key ~/Downloads/my-cursor-party424242-key.json --server https://mcp-server.chainsafe.io

# Continuous loop (24/7 liveliness testing)
node runner.js --key ~/.canton/test-billing-user-key.json --server https://mcp-dev1.01.chainsafe.dev --loop --loop-interval 60

# Parallel execution (3 tasks at a time)
node runner.js --key ~/.canton/test-billing-user-key.json --server https://mcp-dev1.01.chainsafe.dev --parallel 3

# With balance reporting
node runner.js --key ~/.canton/test-billing-user-key.json --server https://mcp-dev1.01.chainsafe.dev --billing-portal https://billing-dev1.01.chainsafe.dev
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--key <path>` | (required) | Canton key file (.json with partyId, privateKey, publicKey, fingerprint) |
| `--server <url>` | `https://mcp-dev1.01.chainsafe.dev` | MCP server URL |
| `--parallel <n>` | `1` | Run n tasks concurrently |
| `--interval <ms>` | `5000` | Delay between tasks (ms) |
| `--loop` | off | Run continuously |
| `--loop-interval <s>` | `60` | Seconds between loop iterations |
| `--tasks <path>` | `./tasks.json` | Custom tasks file |
| `--billing-portal <url>` | none | Billing portal URL for balance checks |

## Requirements

- Node.js 18+ (uses built-in `fetch` and `crypto`)
- No external dependencies
- A Canton key file (generated via the billing portal setup wizard)

## How It Works

1. **Authenticates** via Ed25519 challenge-response → gets JWT token
2. **Loads tasks** from `tasks.json` (DAML code + business intents)
3. **Calls `daml_reason`** for each task via MCP protocol
4. **Parses response**: action (approved/suggest_patterns/suggest_edits/delegate), confidence, issues
5. **Compares** to expected outcome if provided
6. **Logs** structured results with CC spent and latency

## Files

| File | Purpose |
|------|---------|
| `runner.js` | CLI entry point — feeds tasks to agent, prints summary |
| `agent.js` | Executes a single task against the MCP server |
| `payment-adapter-canton.js` | Ed25519 challenge-response auth for Canton |
| `payment-adapter-interface.js` | Interface contract for payment adapters |
| `tasks.json` | 12 test tasks (valid code, invalid code, queries) |

## Output

```
Task                           | Action             | Expected   | Pass  | CC     | Time
valid-iou                      | approved           | approved   | PASS  | 0.10   | 2.3s
query-transfer-patterns        | suggest_patterns   | suggest_p  | PASS  | 0.10   | 1.8s
bad-missing-signatory          | suggest_edits      | suggest_e  | PASS  | 0.10   | 3.1s
...
Total: 10/12 passed, 2 failed, 0 errors | 1.20 CC spent | avg 2.4s
```

## Custom Tasks

Create a JSON file with your own tasks:

```json
[
  {
    "id": "my-test",
    "businessIntent": "Create a payment splitting contract",
    "damlCode": "module Main where\n\ntemplate Split...",
    "expectedAction": "approved",
    "description": "Payment splitter with proper auth"
  }
]
```

Then: `node runner.js --key my-key.json --tasks my-tasks.json`

## What the Results Mean

| Action | Meaning |
|--------|---------|
| `approved` | Code passed all safety gates |
| `suggest_patterns` | Query-only mode — returned pattern recommendations |
| `suggest_edits` | Code has issues — patterns suggested for fixing |
| `delegate` | Server confidence too low — needs human review |
| `error` | Network/auth/server failure |

If code tasks return `delegate` with 0.00 confidence, check that `ENABLE_LLM_ENRICHMENT=true` and `ANTHROPIC_API_KEY` are set on the MCP server.
