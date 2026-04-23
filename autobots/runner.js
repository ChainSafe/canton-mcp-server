#!/usr/bin/env node
/**
 * Autobots Runner
 *
 * Feeds tasks to the testing agent sequentially or in parallel.
 * Supports continuous loop mode for 24/7 liveliness testing.
 *
 * Emits structured logs:
 *   [EVENT] ... task_start/task_end/task_error/auth_*
 *   [STATUS] ... periodic rollup (default every 60s)
 *   [WARN] ... server delegations or soft issues
 *   [CRITICAL] ... all-errors outage detected
 *
 * Usage:
 *   node runner.js --key ~/.canton/my-key.json
 *   node runner.js --key ... --loop --loop-interval 60 --status-interval 60
 */

import { readFileSync } from "fs";
import { resolve } from "path";
import { Agent } from "./agent.js";
import { GrowthOrchestrator } from "./orchestrator.js";
import { PERSONAS } from "./personas.js";
import { StatsAggregator } from "./stats.js";

const DEFAULT_SERVER = "https://mcp-dev1.01.chainsafe.dev";
const DEFAULT_INTERVAL = 5000;
const DEFAULT_LOOP_INTERVAL = 60;
const DEFAULT_STATUS_INTERVAL = 60;

const iso = () => new Date().toISOString();

function logInfo(msg) {
  console.log(`[INFO] ${iso()} ${msg}`);
}
function logWarn(msg) {
  console.log(`[WARN] ${iso()} ${msg}`);
}
function logCritical(msg) {
  console.log(`[CRITICAL] ${iso()} ${msg}`);
}

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {
    key: null,
    server: DEFAULT_SERVER,
    parallel: 1,
    interval: DEFAULT_INTERVAL,
    loop: false,
    loopInterval: DEFAULT_LOOP_INTERVAL,
    statusInterval: DEFAULT_STATUS_INTERVAL,
    tasks: null,
    billingPortal: null,
    verbose: false,
    growth: false,
    maxUsers: 50,
    rampHours: 24,
    keysDir: null,
    growthTickSeconds: 30,
    poolSize: 100,
    billingApiKey: process.env.BILLING_API_KEY || null,
    demoTimeScale: 1,
    personaWeights: null, // e.g., "casual=0.7,regular=0.25,churned=0.05"
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
        opts.parallel = parseInt(args[++i], 10) || 1;
        break;
      case "--interval":
        opts.interval = parseInt(args[++i], 10) || DEFAULT_INTERVAL;
        break;
      case "--loop":
        opts.loop = true;
        break;
      case "--loop-interval":
        opts.loopInterval = parseInt(args[++i], 10) || DEFAULT_LOOP_INTERVAL;
        break;
      case "--status-interval":
        opts.statusInterval = parseInt(args[++i], 10) ?? DEFAULT_STATUS_INTERVAL;
        break;
      case "--tasks":
        opts.tasks = args[++i];
        break;
      case "--billing-portal":
        opts.billingPortal = args[++i];
        break;
      case "--verbose":
        opts.verbose = true;
        break;
      case "--growth":
        opts.growth = true;
        break;
      case "--max-users":
        opts.maxUsers = parseInt(args[++i], 10) || opts.maxUsers;
        break;
      case "--ramp-hours":
        opts.rampHours = parseFloat(args[++i]) || opts.rampHours;
        break;
      case "--billing-api-key":
        opts.billingApiKey = args[++i];
        break;
      case "--demo-time-scale":
        opts.demoTimeScale = parseFloat(args[++i]) || 1;
        break;
      case "--personas":
        opts.personaWeights = args[++i];
        break;
      case "--keys-dir":
        opts.keysDir = args[++i];
        break;
      case "--growth-tick-seconds":
        opts.growthTickSeconds = parseInt(args[++i], 10) || opts.growthTickSeconds;
        break;
      case "--pool-size":
        opts.poolSize = parseInt(args[++i], 10) || opts.poolSize;
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
  --status-interval <s>   Seconds between [STATUS] logs in loop mode (default: ${DEFAULT_STATUS_INTERVAL}, 0 to disable)
  --tasks <path>          Custom tasks JSON file (default: ./tasks.json)
  --billing-portal <url>  Billing portal URL (for balance checks)
  --verbose               Print per-iteration summary tables (in loop mode)
  --help                  Show this help

Growth mode (simulate organic user growth with persona-driven bot identities):
  --growth                Enable growth mode (ignores --key; provisions identities on-the-fly)
  --billing-portal <url>  REQUIRED in growth mode — used to register new parties
  --billing-api-key <key> Billing API key for in-band top-ups (or set BILLING_API_KEY env).
                          Omit to disable auto top-ups (bots will still run tasks).
  --max-users <n>         Target concurrent bot identities (default: 50)
  --ramp-hours <h>        Signup ramp duration in hours (default: 24)
  --demo-time-scale <n>   Compress simulated time: 1=real time (default),
                          168=1 real hour ≈ 1 simulated week (for short demos).
  --personas <spec>       Comma-separated persona weight overrides,
                          e.g. "casual=0.7,regular=0.25,churned=0.05".
                          Unspecified personas keep their default weight.
  --keys-dir <path>       Dir for generated keyfiles (default: ./keys)
  --growth-tick-seconds   Orchestrator tick interval (default: 30)
  --pool-size <n>         Max number of distinct Canton parties to provision
                          (default: 100). Existing keyfiles are adopted into
                          the pool; bots release their party on dormancy so
                          new bots can recycle it instead of provisioning
                          a fresh one. Keeps the validator under its
                          200-party cap.
  Party hints are realistic usernames (alex42, maya_kim, coolfox7, …) generated
  at provisioning time — not sequential "autobot-N" IDs.

Personas (see personas.js for defaults):
  casual   ~60%  light users (task every ~2 weeks, top-up every ~6 weeks)
  regular  ~30%  active users (task every ~2 days, top-up every ~2-3 weeks)
  churned  ~10%  sign up and vanish (1-2 tasks then dormant, no top-ups)

Log levels:
  [EVENT]     per-task events (task_start, task_end, task_error, auth_*)
  [STATUS]    periodic rollup (cumulative + hour + minute stats)
  [WARN]      server delegations, soft issues
  [CRITICAL]  outage detected (3+ consecutive all-error iterations)
`);
        process.exit(0);
    }
  }

  if (opts.growth) {
    if (!opts.billingPortal) {
      console.error("Error: --growth requires --billing-portal. Use --help for usage.");
      process.exit(1);
    }
    if (!opts.keysDir) {
      opts.keysDir = resolve(import.meta.dirname, "keys");
    }
  } else if (!opts.key) {
    console.error("Error: --key is required (or use --growth). Use --help for usage.");
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

async function runOnce(agent, tasks, opts, stats = null) {
  const results = [];

  if (opts.parallel > 1) {
    // Run in batches
    for (let i = 0; i < tasks.length; i += opts.parallel) {
      const batch = tasks.slice(i, i + opts.parallel);
      const batchResults = await Promise.all(
        batch.map((task) => agent.executeTask(task))
      );
      results.push(...batchResults);
      if (stats) stats.addTaskResults(batchResults);

      if (i + opts.parallel < tasks.length) {
        await sleep(opts.interval);
      }
    }
  } else {
    // Sequential
    for (const [i, task] of tasks.entries()) {
      const result = await agent.executeTask(task);
      results.push(result);
      if (stats) stats.addTaskResults([result]);

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

function buildPersonas(weightsSpec) {
  // Start with a deep-enough copy so we don't mutate PERSONAS.
  const personas = {};
  for (const [name, p] of Object.entries(PERSONAS)) {
    personas[name] = { ...p };
  }
  if (!weightsSpec) return personas;
  for (const pair of weightsSpec.split(",")) {
    const [rawName, rawWeight] = pair.split("=").map((s) => s.trim());
    if (!rawName || !personas[rawName]) {
      logWarn(`Ignoring unknown persona in --personas: ${rawName}`);
      continue;
    }
    const w = parseFloat(rawWeight);
    if (!Number.isFinite(w) || w < 0) {
      logWarn(`Ignoring invalid weight for ${rawName}: ${rawWeight}`);
      continue;
    }
    personas[rawName].weight = w;
  }
  return personas;
}

async function runGrowthMode(opts, tasks) {
  const personas = buildPersonas(opts.personaWeights);
  const personaSummary = Object.values(personas)
    .map((p) => `${p.name}=${p.weight}`)
    .join(",");
  logInfo(
    `Autobots starting in GROWTH mode — server=${opts.server} tasks=${tasks.length} maxUsers=${opts.maxUsers} rampHours=${opts.rampHours} personas=[${personaSummary}] demoTimeScale=${opts.demoTimeScale} billingPortal=${opts.billingPortal} billingApiKey=${opts.billingApiKey ? "set" : "none"}`
  );

  if (!opts.billingApiKey) {
    logWarn(
      "No --billing-api-key (and BILLING_API_KEY env not set). Auto top-ups disabled — bots will run tasks but never credit themselves."
    );
  }

  const stats = new StatsAggregator();

  // Periodic status logger
  let statusTimer = null;
  if (opts.statusInterval > 0) {
    statusTimer = setInterval(() => {
      console.log(stats.formatStatus());
    }, opts.statusInterval * 1000);
  }

  const orchestrator = new GrowthOrchestrator({
    serverUrl: opts.server,
    billingPortalUrl: opts.billingPortal,
    billingApiKey: opts.billingApiKey,
    keysDir: opts.keysDir,
    maxUsers: opts.maxUsers,
    rampHours: opts.rampHours,
    tickSeconds: opts.growthTickSeconds,
    tasks,
    stats,
    personas,
    demoTimeScale: opts.demoTimeScale,
    poolSize: opts.poolSize,
  });

  const shutdown = () => {
    logInfo("Shutdown requested — stopping orchestrator and printing final status...");
    orchestrator.stop();
    if (statusTimer) clearInterval(statusTimer);
    console.log(stats.formatStatus());
    logInfo(`Final: ${JSON.stringify(stats.snapshot().cumulative)} bots=${stats.botCount}`);
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);

  process.on("uncaughtException", (err) => {
    logCritical(`Uncaught exception: ${err.message}`);
    console.error(err.stack);
    process.exit(1);
  });
  process.on("unhandledRejection", (reason) => {
    logCritical(`Unhandled rejection: ${reason}`);
    if (reason?.stack) console.error(reason.stack);
  });

  await orchestrator.start();
}

async function main() {
  const opts = parseArgs();
  const tasks = loadTasks(opts.tasks);

  if (opts.growth) {
    return runGrowthMode(opts, tasks);
  }

  logInfo(`Autobots starting — server=${opts.server} tasks=${tasks.length} parallel=${opts.parallel} loop=${opts.loop}`);

  // Authenticate — hard exit on failure with full error
  const agent = new Agent(opts.server);
  try {
    const auth = await agent.authenticate(opts.key);
    logInfo(`Authenticated as ${auth.partyId.slice(0, 50)}...`);
  } catch (err) {
    logCritical(`AUTH FAILED — cannot continue: ${err.message}`);
    if (err.stack) console.error(err.stack);
    process.exit(1);
  }

  if (opts.billingPortal) {
    try {
      const balance = await agent.getBalance(opts.billingPortal);
      logInfo(`Balance: ${balance.balance} CC (charged: ${balance.totalCharged}, credited: ${balance.totalCredited})`);
    } catch (err) {
      logWarn(`Balance check failed: ${err.message}`);
    }
  }

  // Crash-safe: log uncaught exceptions before dying
  process.on("uncaughtException", (err) => {
    logCritical(`Uncaught exception: ${err.message}`);
    console.error(err.stack);
    process.exit(1);
  });
  process.on("unhandledRejection", (reason) => {
    logCritical(`Unhandled rejection: ${reason}`);
    if (reason?.stack) console.error(reason.stack);
  });

  if (opts.loop) {
    const stats = new StatsAggregator();
    let iteration = 0;

    // Periodic status logger
    let statusTimer = null;
    if (opts.statusInterval > 0) {
      statusTimer = setInterval(() => {
        console.log(stats.formatStatus());
      }, opts.statusInterval * 1000);
    }

    // Graceful shutdown
    const shutdown = () => {
      logInfo("Shutdown requested — printing final status...");
      if (statusTimer) clearInterval(statusTimer);
      console.log(stats.formatStatus());
      logInfo(`Final: ${JSON.stringify(stats.snapshot().cumulative)}`);
      process.exit(0);
    };
    process.on("SIGINT", shutdown);
    process.on("SIGTERM", shutdown);

    while (true) {
      try {
        iteration++;
        logInfo(`Iteration #${iteration} starting`);

        let results = [];
        try {
          results = await runOnce(agent, tasks, opts, stats);
        } catch (err) {
          logCritical(`Iteration #${iteration} failed: ${err.message}`);
          if (err.stack) console.error(err.stack);
        }

        stats.endIteration(results, iteration);

        if (opts.verbose) {
          printSummary(results);
        }

        // Outage detection
        if (stats.consecutiveAllErrorIterations >= 3) {
          logCritical(`${stats.consecutiveAllErrorIterations} consecutive iterations with 100% error rate — possible server outage`);
        }
        if (stats.consecutiveEmptyIterations >= 3) {
          logCritical(`${stats.consecutiveEmptyIterations} consecutive empty iterations — tasks not running`);
        }

        logInfo(`Iteration #${iteration} complete — sleeping ${opts.loopInterval}s`);
        await sleep(opts.loopInterval * 1000);
      } catch (err) {
        logCritical(`Loop iteration error: ${err.message}`);
        await sleep(5000); // Brief pause before retrying
      }
    }
  } else {
    logInfo("Running tasks (single pass)...");
    const results = await runOnce(agent, tasks, opts);
    printSummary(results);

    if (opts.billingPortal) {
      try {
        const balance = await agent.getBalance(opts.billingPortal);
        logInfo(`Final balance: ${balance.balance} CC`);
      } catch (err) {
        logWarn(`Balance check failed: ${err.message}`);
      }
    }

    const allPassed = results.every((r) => r.pass);
    process.exit(allPassed ? 0 : 1);
  }
}

main().catch((err) => {
  logCritical(`Fatal error in main: ${err.message}`);
  if (err.stack) console.error(err.stack);
  process.exit(1);
});
