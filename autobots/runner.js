#!/usr/bin/env node
/**
 * Autobots Runner
 *
 * Feeds tasks to the testing agent sequentially or in parallel.
 * Supports continuous loop mode for 24/7 liveliness testing.
 *
 * Usage:
 *   node runner.js --key ~/.canton/my-key.json --server https://mcp-dev1.01.chainsafe.dev
 *   node runner.js --key ~/.canton/my-key.json --loop --loop-interval 60
 *   node runner.js --key ~/.canton/my-key.json --parallel 3
 */

import { readFileSync } from "fs";
import { resolve } from "path";
import { Agent } from "./agent.js";

const DEFAULT_SERVER = "https://mcp-dev1.01.chainsafe.dev";
const DEFAULT_INTERVAL = 5000;
const DEFAULT_LOOP_INTERVAL = 60;

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {
    key: null,
    server: DEFAULT_SERVER,
    parallel: 1,
    interval: DEFAULT_INTERVAL,
    loop: false,
    loopInterval: DEFAULT_LOOP_INTERVAL,
    tasks: null,
    billingPortal: null,
  };

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case "--key":
        opts.key = args[++i];
        break;
      case "--server":
        opts.server = args[++i];
        break;
      case "--parallel":
        opts.parallel = parseInt(args[++i], 10);
        break;
      case "--interval":
        opts.interval = parseInt(args[++i], 10);
        break;
      case "--loop":
        opts.loop = true;
        break;
      case "--loop-interval":
        opts.loopInterval = parseInt(args[++i], 10);
        break;
      case "--tasks":
        opts.tasks = args[++i];
        break;
      case "--billing-portal":
        opts.billingPortal = args[++i];
        break;
      case "--help":
        console.log(`
Autobots Runner — Liveliness & e2e load testing for Canton MCP Server

Usage: node runner.js [options]

Options:
  --key <path>            Canton key file (required)
  --server <url>          MCP server URL (default: ${DEFAULT_SERVER})
  --parallel <n>          Run n tasks concurrently (default: 1)
  --interval <ms>         Delay between tasks in ms (default: ${DEFAULT_INTERVAL})
  --loop                  Run continuously
  --loop-interval <s>     Seconds between loop iterations (default: ${DEFAULT_LOOP_INTERVAL})
  --tasks <path>          Custom tasks JSON file (default: ./tasks.json)
  --billing-portal <url>  Billing portal URL (for balance checks)
  --help                  Show this help
`);
        process.exit(0);
    }
  }

  if (!opts.key) {
    console.error("Error: --key is required. Use --help for usage.");
    process.exit(1);
  }

  return opts;
}

function loadTasks(tasksPath) {
  const file = tasksPath || resolve(import.meta.dirname, "tasks.json");
  return JSON.parse(readFileSync(file, "utf8"));
}

function printSummary(results) {
  const passed = results.filter((r) => r.pass).length;
  const failed = results.filter((r) => !r.pass && !r.error).length;
  const errors = results.filter((r) => r.error).length;
  const totalCC = results.reduce((s, r) => s + r.ccSpent, 0);
  const avgMs =
    results.length > 0
      ? Math.round(results.reduce((s, r) => s + r.durationMs, 0) / results.length)
      : 0;

  console.log("\n" + "=".repeat(78));
  console.log(
    `${"Task".padEnd(30)} | ${"Action".padEnd(18)} | ${"Expected".padEnd(10)} | ${"Pass".padEnd(5)} | ${"CC".padEnd(6)} | Time`
  );
  console.log("-".repeat(78));

  for (const r of results) {
    const passStr = r.error ? "ERR" : r.pass ? "PASS" : "FAIL";
    const action = r.error ? `error: ${r.error.slice(0, 12)}` : r.action;
    console.log(
      `${r.taskId.padEnd(30)} | ${action.padEnd(18)} | ${(r.expectedAction || "-").padEnd(10)} | ${passStr.padEnd(5)} | ${r.ccSpent.toFixed(2).padEnd(6)} | ${r.durationMs}ms`
    );
  }

  console.log("=".repeat(78));
  console.log(
    `Total: ${passed}/${results.length} passed, ${failed} failed, ${errors} errors | ${totalCC.toFixed(2)} CC spent | avg ${avgMs}ms`
  );
  console.log("");
}

async function runOnce(agent, tasks, opts) {
  const results = [];

  if (opts.parallel > 1) {
    // Run in batches
    for (let i = 0; i < tasks.length; i += opts.parallel) {
      const batch = tasks.slice(i, i + opts.parallel);
      const batchResults = await Promise.all(
        batch.map((task) => agent.executeTask(task))
      );
      results.push(...batchResults);

      for (const r of batchResults) {
        const icon = r.error ? "X" : r.pass ? "+" : "-";
        console.log(
          `  [${icon}] ${r.taskId}: ${r.action} (${r.confidence.toFixed(2)}) ${r.durationMs}ms`
        );
      }

      if (i + opts.parallel < tasks.length) {
        await sleep(opts.interval);
      }
    }
  } else {
    // Sequential
    for (const [i, task] of tasks.entries()) {
      const result = await agent.executeTask(task);
      results.push(result);

      const icon = result.error ? "X" : result.pass ? "+" : "-";
      console.log(
        `  [${icon}] ${result.taskId}: ${result.action} (${result.confidence.toFixed(2)}) ${result.durationMs}ms`
      );

      if (i < tasks.length - 1) {
        await sleep(opts.interval);
      }
    }
  }

  return results;
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function main() {
  const opts = parseArgs();
  const tasks = loadTasks(opts.tasks);

  console.log("=== Autobots Testing Agent ===");
  console.log(`Server:   ${opts.server}`);
  console.log(`Tasks:    ${tasks.length}`);
  console.log(`Parallel: ${opts.parallel}`);
  console.log(`Loop:     ${opts.loop ? `yes (every ${opts.loopInterval}s)` : "no"}`);
  console.log("");

  // Authenticate
  const agent = new Agent(opts.server);
  console.log("Authenticating...");
  const auth = await agent.authenticate(opts.key);
  console.log(`Authenticated: ${auth.partyId.slice(0, 40)}...`);

  if (opts.billingPortal) {
    const balance = await agent.getBalance(opts.billingPortal);
    console.log(`Balance: ${balance.balance} CC (charged: ${balance.totalCharged}, credited: ${balance.totalCredited})`);
  }
  console.log("");

  if (opts.loop) {
    let iteration = 0;
    process.on("SIGINT", () => {
      console.log("\nShutdown requested. Exiting...");
      process.exit(0);
    });

    while (true) {
      iteration++;
      console.log(
        `--- Iteration #${iteration} (${new Date().toISOString()}) ---`
      );
      const results = await runOnce(agent, tasks, opts);
      printSummary(results);

      if (opts.billingPortal) {
        const balance = await agent.getBalance(opts.billingPortal);
        console.log(`Balance after iteration: ${balance.balance} CC`);
      }

      console.log(
        `Sleeping ${opts.loopInterval}s until next iteration...\n`
      );
      await sleep(opts.loopInterval * 1000);
    }
  } else {
    console.log("Running tasks...");
    const results = await runOnce(agent, tasks, opts);
    printSummary(results);

    if (opts.billingPortal) {
      const balance = await agent.getBalance(opts.billingPortal);
      console.log(`Final balance: ${balance.balance} CC`);
    }

    const allPassed = results.every((r) => r.pass);
    process.exit(allPassed ? 0 : 1);
  }
}

main().catch((err) => {
  console.error("Fatal:", err.message);
  process.exit(1);
});
