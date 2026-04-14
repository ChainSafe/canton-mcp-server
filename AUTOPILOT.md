# Canton DAML Autopilot

## Autopilot v1 — Current State

- **How it works:** MCP server + 2 tools (`daml_reason`, `daml_automater`)
- **Gate 1 safety checking:** compilation → auth extraction (LLM/regex) → validation
- **Semantic search:** ChromaDB + 10K+ canonical DAML resources

**What it CAN do:**
- Validate DAML code for safety, authorization, and type correctness
- Recommend patterns from canonical DAML repositories
- Delegate to a human when confidence is low
- Audit authorization patterns and flag missing checks

**What it CANNOT do:**
- Generate code
- Run tests server-side
- Deploy to Canton
- Reason across multiple files
- Understand business logic beyond what the code expresses

---

## Billing & Payments

- **Tab model:** ChargeReceipts on Canton ledger
- **Free tier:** 350 calls, then 0.1 CC per `daml_reason` call
- **Top-up:** Via billing portal (`TransferFactory_Transfer`, atomic settlement)
- **Auth:** Ed25519 challenge-response, JWT tokens

---

## Autopilot Testing | "Autobots"

**Official framing:** Liveliness and e2e load testing.

**One JS file. It's the "testing" agent.**

- Connects to the MCP server via stdio or HTTP transport
- Sends `initialize` → `tools/call` → reads result
- Payment in Canton coin — `pay(amount) → receipt`, pluggable (the SDK does that job, agents just use it)

### Goals

1. **Transactions happening** — allows us to figure out how rewards are getting allocated
2. **Server running 24/7** — generates logs around the clock, surfaces parts that need attention

### Agent behavior

- The MCP server responds with **how certain it is**, which drives what the agent does next
- **Termination:** the MCP server tells the agent "you're done — code is as good as it gets, find a human to do the manual audit next"
- **Delegation:** when the server is unreachable, the agent delegates back to the user. This is expected behavior, not a bug

### What the JS file actually does

1. Loads a DAML task (`business intent` only OR `[business intent, daml_code]`) — or generates one with an LLM call
2. Calls `daml_reason` with that task
3. Handles the payment loop
4. Logs: task in, coin spent, result out, pass/fail against expected output

### What you need to build

| File | Purpose |
|------|---------|
| `agent.js` | The testing agent described above |
| `payment-adapter-canton.js` | Implements the seam for Canton coin |
| `payment-adapter-interface.js` | The contract (input: challenge, output: proof) |
| Task fixture file | DAML snippets + expected outputs (or LLM-generated test cases) |
| Runner script | Feeds tasks to `agent.js` sequentially or in parallel |
