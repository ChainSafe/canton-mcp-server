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

## Docker Deployment

**Build and run:**
```bash
# With docker-compose (easiest)
KEY_FILE=~/.canton/bot-key.json MCP_SERVER_URL=https://mcp-server.chainsafe.io docker compose up -d

# Or build and run directly
docker build -t autobots .
docker run -d --name autobots \
  -v ~/.canton/bot-key.json:/config/key.json:ro \
  -e MCP_SERVER_URL=https://mcp-server.chainsafe.io \
  autobots
```

**Environment variables:**

| Var | Default | Description |
|-----|---------|-------------|
| `MCP_SERVER_URL` | `https://mcp-dev1.01.chainsafe.dev` | MCP server to test against |
| `KEY_FILE` | `/config/key.json` | Path to Canton key file inside container |
| `LOOP_INTERVAL` | `60` | Seconds between iterations |
| `STATUS_INTERVAL` | `60` | Seconds between `[STATUS]` logs |
| `TASK_INTERVAL` | `5000` | Milliseconds between tasks |

**View logs:**
```bash
docker logs -f autobots
docker logs autobots 2>&1 | grep STATUS
docker logs autobots 2>&1 | grep CRITICAL
```

**For K8s:** Use the Dockerfile as-is. Mount the key file as a Secret volume at `/config/key.json`. Set env vars via ConfigMap.

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

### Single-run mode (no `--loop`)

A summary table after all tasks complete:

```
Task                           | Action             | Expected   | Pass  | CC     | Time
valid-iou                      | approved           | approved   | PASS  | 0.10   | 2.3s
query-transfer-patterns        | suggest_patterns   | suggest_p  | PASS  | 0.10   | 1.8s
...
Total: 10/12 passed, 2 failed, 0 errors | 1.20 CC spent | avg 2.4s
```

### Loop mode (24/7 liveliness) — structured logs

All logs are **single-line** and grep-friendly for Loki/journalctl:

**Per-task events** (every task):
```
[EVENT] 2026-04-13T17:42:00.123Z task_start taskId=valid-iou
[EVENT] 2026-04-13T17:42:02.345Z task_end taskId=valid-iou action=approved pass=true confidence=1.00 durationMs=2222
[EVENT] 2026-04-13T17:42:05.678Z task_error taskId=bad-auth error=HTTP_500:...
[EVENT] 2026-04-13T17:42:10.900Z auth_ok
```

**Periodic status** (every `--status-interval` seconds, default 60):
```
[STATUS] 2026-04-13T17:42:00Z uptime=2h34m | last_min: tasks=2 passed=2 errors=0 | hour: tasks=119 pass_rate=97.5% cc=11.90 avg=2350ms p95=4800ms | total: tasks=253 pass_rate=97.7% cc=25.30 iter=23
```

**Warnings & alerts**:
```
[WARN] 2026-04-13T17:42:00Z Server returned delegate: taskId=valid-iou reason="Safety check failed (NotFoundError): model not found"
[CRITICAL] 2026-04-13T17:42:00Z 3 consecutive iterations with 100% error rate — possible server outage
```

### Watching logs

**Local (systemd)**:
```bash
sudo journalctl -fu autobots | grep -E "STATUS|CRITICAL"
```

**Grafana/Loki**:
```
{container="autobots"} |= "[STATUS]"              # just periodic status
{container="autobots"} |= "[EVENT] task_error"    # just errors
{container="autobots"} |~ "CRITICAL|WARN"         # anything needing attention
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
