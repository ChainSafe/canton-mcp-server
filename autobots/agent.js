/**
 * Autobots Testing Agent
 *
 * Executes a single DAML task against the MCP server:
 * 1. Authenticates via Canton challenge-response
 * 2. Calls daml_reason with the task
 * 3. Parses the response (action, confidence, issues)
 * 4. Compares to expected outcome
 * 5. Returns structured result with full error detail (no silent fails)
 */

import { CantonPaymentAdapter } from "./payment-adapter-canton.js";

/**
 * @typedef {Object} Task
 * @property {string} id
 * @property {string} businessIntent
 * @property {string} [damlCode]
 * @property {string} [query]
 * @property {string} [expectedAction] - "approved"|"suggest_patterns"|"suggest_edits"|"delegate"
 * @property {string} [description]
 */

/**
 * @typedef {Object} TaskResult
 * @property {string} taskId
 * @property {string} action
 * @property {string} [expectedAction]
 * @property {boolean} pass
 * @property {number} confidence
 * @property {number} ccSpent
 * @property {number} durationMs
 * @property {string[]} issues
 * @property {string} [llmInsights]
 * @property {string} [error]
 * @property {string} timestamp
 */

const iso = () => new Date().toISOString();

function logEvent(name, fields = {}) {
  const parts = [`[EVENT]`, iso(), name];
  for (const [k, v] of Object.entries(fields)) {
    const val = typeof v === "string" ? (v.includes(" ") ? JSON.stringify(v) : v) : v;
    parts.push(`${k}=${val}`);
  }
  console.log(parts.join(" "));
}

function logWarn(message) {
  console.log(`[WARN] ${iso()} ${message}`);
}

export class Agent {
  #adapter;
  #serverUrl;
  #authenticated = false;

  constructor(serverUrl) {
    this.#serverUrl = serverUrl;
    this.#adapter = new CantonPaymentAdapter();
  }

  async authenticate(keyFilePath) {
    const result = await this.#adapter.authenticate(
      keyFilePath,
      this.#serverUrl
    );
    this.#authenticated = true;
    return result;
  }

  /**
   * Execute a single task against daml_reason.
   * @param {Task} task
   * @returns {Promise<TaskResult>}
   */
  async executeTask(task) {
    if (!this.#authenticated) throw new Error("Not authenticated");

    logEvent("task_start", { taskId: task.id });

    // Refresh token if needed
    try {
      await this.#adapter.refreshToken(this.#serverUrl);
    } catch (err) {
      const error = `AUTH_REFRESH_FAILED: ${err.message}`;
      logEvent("task_error", { taskId: task.id, error });
      return this.#errorResult(task, error, 0);
    }

    const start = Date.now();
    const partyId = this.#adapter.partyId;

    try {
      // Build MCP request
      const args = { businessIntent: task.businessIntent };
      if (task.damlCode) args.damlCode = task.damlCode;
      if (task.query) args.query = task.query;

      const mcpUrl = new URL("/mcp", this.#serverUrl);
      mcpUrl.searchParams.set("payerParty", partyId);
      mcpUrl.searchParams.set("businessIntent", task.businessIntent);

      let res;
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 60_000);
        res = await fetch(mcpUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${this.#adapter.token}`,
          },
          body: JSON.stringify({
            jsonrpc: "2.0",
            method: "tools/call",
            params: { name: "daml_reason", arguments: args },
            id: task.id,
          }),
          signal: controller.signal,
        });
        clearTimeout(timeout);
      } catch (fetchErr) {
        const durationMs = Date.now() - start;
        const code = fetchErr.cause?.code || fetchErr.code || "FETCH_ERROR";
        const error = `NETWORK_${code}: ${fetchErr.message}`;
        logEvent("task_error", { taskId: task.id, error, durationMs });
        return this.#errorResult(task, error, durationMs);
      }

      const durationMs = Date.now() - start;

      if (!res.ok) {
        const body = (await res.text()).slice(0, 500);
        const error = `HTTP_${res.status}: ${body}`;
        logEvent("task_error", { taskId: task.id, error, durationMs });
        return this.#errorResult(task, error, durationMs);
      }

      const data = await res.json();

      // Handle JSON-RPC error
      if (data.error) {
        const error = `RPC_${data.error.code || "ERR"}: ${data.error.message || JSON.stringify(data.error)}`;
        logEvent("task_error", { taskId: task.id, error, durationMs });
        return this.#errorResult(task, error, durationMs);
      }

      // Parse structured content
      const sc = data.result?.structuredContent || {};
      const action = sc.action || "unknown";
      const confidence = sc.confidence || 0;
      const issues = sc.issues || [];
      const llmInsights = sc.llmInsights || null;

      // Surface server-side errors (delegate with a failure reason)
      if (action === "delegate" && sc.delegationReason) {
        logWarn(`Server returned delegate: taskId=${task.id} reason="${sc.delegationReason}"`);
      }

      // Determine pass/fail
      const pass = task.expectedAction
        ? action === task.expectedAction
        : true; // No expectation = informational

      logEvent("task_end", {
        taskId: task.id,
        action,
        pass,
        confidence: confidence.toFixed(2),
        durationMs,
      });

      return {
        taskId: task.id,
        action,
        expectedAction: task.expectedAction || null,
        pass,
        confidence,
        ccSpent: 0.1, // Fixed price per daml_reason call
        durationMs,
        issues,
        llmInsights: llmInsights ? llmInsights.slice(0, 200) : null,
        error: null,
        timestamp: new Date().toISOString(),
      };
    } catch (err) {
      const durationMs = Date.now() - start;
      const error = `${err.constructor.name}: ${err.message}`;
      logEvent("task_error", { taskId: task.id, error, durationMs, stack: err.stack?.split("\n")[1]?.trim() });
      return this.#errorResult(task, error, durationMs);
    }
  }

  #errorResult(task, error, durationMs) {
    return {
      taskId: task.id,
      action: "error",
      expectedAction: task.expectedAction || null,
      pass: false,
      confidence: 0,
      ccSpent: 0,
      durationMs,
      issues: [],
      llmInsights: null,
      error,
      timestamp: new Date().toISOString(),
    };
  }

  async getBalance(billingPortalUrl) {
    return this.#adapter.getBalance(billingPortalUrl);
  }

  get partyId() {
    return this.#adapter.partyId;
  }
}
