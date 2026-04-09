/**
 * Autobots Testing Agent
 *
 * Executes a single DAML task against the MCP server:
 * 1. Authenticates via Canton challenge-response
 * 2. Calls daml_reason with the task
 * 3. Parses the response (action, confidence, issues)
 * 4. Compares to expected outcome
 * 5. Returns structured result
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

    // Refresh token if needed
    await this.#adapter.refreshToken(this.#serverUrl);

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

      const res = await fetch(mcpUrl, {
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
      });

      const durationMs = Date.now() - start;

      if (!res.ok) {
        return this.#errorResult(
          task,
          `HTTP ${res.status}: ${(await res.text()).slice(0, 200)}`,
          durationMs
        );
      }

      const data = await res.json();

      // Handle JSON-RPC error
      if (data.error) {
        return this.#errorResult(
          task,
          `RPC error: ${data.error.message || JSON.stringify(data.error)}`,
          durationMs
        );
      }

      // Parse structured content
      const sc = data.result?.structuredContent || {};
      const action = sc.action || "unknown";
      const confidence = sc.confidence || 0;
      const issues = sc.issues || [];
      const llmInsights = sc.llmInsights || null;

      // Determine pass/fail
      const pass = task.expectedAction
        ? action === task.expectedAction
        : true; // No expectation = informational

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
      return this.#errorResult(task, err.message, Date.now() - start);
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
