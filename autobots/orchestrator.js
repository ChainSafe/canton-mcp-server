/**
 * GrowthOrchestrator — manages a fleet of persona-driven VirtualBots.
 *
 * The orchestrator decides *when* to add new bots; each bot's cadence is
 * driven by its persona (see personas.js), not by the orchestrator. Signup
 * follows a sqrt-ramp from 0 → maxUsers over rampMs, producing an organic
 * cohort curve rather than a flat spawn.
 *
 * On spawn, each new bot is assigned a persona drawn from the configured
 * weighted distribution (Casual / Regular / Churned by default).
 *
 * On startup the orchestrator adopts any pre-existing keyfiles before minting
 * new ones, so restarts are idempotent.
 */

import { PartyPool } from "./party-pool.js";
import { drawPersona, PERSONAS } from "./personas.js";
import { VirtualBot } from "./virtual-bot.js";

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

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

export class GrowthOrchestrator {
  #serverUrl;
  #billingApiKey;
  #maxUsers;
  #rampMs;
  #tickMs;
  #tasks;
  #stats;
  #personas;
  #demoTimeScale;
  #pool;

  #startedAt = 0;
  #bots = [];
  #stopped = false;

  constructor({
    serverUrl,
    billingPortalUrl,
    billingApiKey = null,
    keysDir,
    maxUsers,
    rampHours,
    tickSeconds = 30,
    tasks,
    stats,
    personas = PERSONAS,
    demoTimeScale = 1,
    poolSize = 100,
  }) {
    this.#serverUrl = serverUrl;
    this.#billingApiKey = billingApiKey;
    this.#maxUsers = maxUsers;
    this.#rampMs = rampHours * 3600 * 1000;
    this.#tickMs = tickSeconds * 1000;
    this.#tasks = tasks;
    this.#stats = stats;
    this.#personas = personas;
    this.#demoTimeScale = demoTimeScale;
    this.#pool = new PartyPool({ billingPortalUrl, keysDir, maxSize: poolSize });
  }

  get botCount() {
    return this.#bots.length;
  }

  get activeBotCount() {
    return this.#bots.filter((b) => !b.dormant).length;
  }

  get targetBotCount() {
    return this.#usersAt(this.#elapsedFraction());
  }

  #elapsedFraction() {
    if (this.#rampMs <= 0) return 1;
    const elapsed = Date.now() - this.#startedAt;
    return Math.min(1, Math.max(0, elapsed / this.#rampMs));
  }

  #usersAt(fraction) {
    return Math.max(1, Math.round(this.#maxUsers * Math.sqrt(fraction)));
  }

  async start() {
    this.#startedAt = Date.now();
    const personaNames = Object.keys(this.#personas).join("/");
    const { adopted, capacity } = this.#pool.init();
    logInfo(
      `Growth orchestrator starting — maxUsers=${this.#maxUsers} rampHours=${(this.#rampMs / 3600_000).toFixed(2)} personas=${personaNames} demoTimeScale=${this.#demoTimeScale} billingApiKey=${this.#billingApiKey ? "configured" : "missing"} poolSize=${capacity} adoptedKeys=${adopted}`
    );
    if (this.#maxUsers > capacity) {
      logWarn(
        `maxUsers=${this.#maxUsers} exceeds pool capacity=${capacity}; active bots will cap at pool size`
      );
    }

    // Warm-start: if we adopted keyfiles from a previous run, spawn bots for
    // them immediately (up to maxUsers) instead of re-ramping from zero.
    // Bots get freshly drawn personas — we don't persist persona-to-party
    // mapping across runs.
    const warmStart = Math.min(adopted, this.#maxUsers);
    for (let i = 0; i < warmStart && !this.#stopped; i++) {
      try {
        const reservation = await this.#pool.checkout();
        if (!reservation) break;
        await this.#spawnBot(reservation.keyPath, reservation.reused);
      } catch (err) {
        logWarn(`Warm-start spawn failed: ${err.message} — continuing`);
      }
    }

    await this.#tickLoop();
  }

  stop() {
    this.#stopped = true;
    for (const bot of this.#bots) bot.stop();
  }

  async #spawnBot(keyPath, reused = false) {
    const persona = drawPersona(this.#personas);
    const bot = new VirtualBot({
      keyPath,
      serverUrl: this.#serverUrl,
      tasks: this.#tasks,
      stats: this.#stats,
      persona,
      demoTimeScale: this.#demoTimeScale,
      billingApiKey: this.#billingApiKey,
      onRelease: () => this.#handleBotReleased(bot, keyPath),
    });
    try {
      await bot.authenticate();
    } catch (err) {
      logCritical(`Bot auth failed for ${keyPath}: ${err.message}`);
      this.#pool.release(keyPath);
      throw err;
    }
    this.#bots.push(bot);
    this.#stats.addBotSpawned?.(bot.partyId, persona.name);
    bot.startLoop();
    logInfo(
      `Bot online (${this.#bots.length}/${this.targetBotCount}) persona=${persona.name} party=${reused ? "recycled" : "new"} partyId=${bot.partyId.slice(0, 50)}...`
    );
  }

  #handleBotReleased(bot, keyPath) {
    const idx = this.#bots.indexOf(bot);
    if (idx >= 0) this.#bots.splice(idx, 1);
    this.#pool.release(keyPath);
  }

  async #tickLoop() {
    while (!this.#stopped) {
      try {
        const fraction = this.#elapsedFraction();
        const target = this.#usersAt(fraction);

        while (this.#bots.length < target && !this.#stopped) {
          let reservation;
          try {
            reservation = await this.#pool.checkout();
          } catch (err) {
            logWarn(`Provisioning failed: ${err.message} — will retry next tick`);
            break;
          }
          if (!reservation) {
            logWarn(
              `Party pool exhausted (${this.#pool.inUseCount}/${this.#pool.maxSize}); will retry next tick`
            );
            break;
          }
          try {
            await this.#spawnBot(reservation.keyPath, reservation.reused);
          } catch {
            // #spawnBot already released the party and logged.
            break;
          }
        }

        console.log(
          `[STATUS] ${iso().slice(0, 19)}Z growth bots=${this.#bots.length} active=${this.activeBotCount} target=${target} ramp=${(fraction * 100).toFixed(1)}% pool=${this.#pool.size}/${this.#pool.maxSize} idle=${this.#pool.idleCount}`
        );
      } catch (err) {
        logCritical(`Orchestrator tick error: ${err.message}`);
        if (err.stack) console.error(err.stack);
      }
      await sleep(this.#tickMs);
    }
  }
}
