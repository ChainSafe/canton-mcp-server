/**
 * VirtualBot — one Canton identity running its own independent behavior loop.
 *
 * Each bot is assigned a `persona` (see personas.js) that drives its cadence:
 *   - how often it runs a task
 *   - whether/how often it tops itself up
 *   - whether it has a lifetime task cap (churned users stop after N tasks)
 *
 * On each wake the bot decides between running a task and topping up based on
 * which event's scheduled fire time is closest. Once lifetimeTasks is reached
 * the bot stops gracefully, which produces the "dormant user" shape in metrics.
 *
 * Intervals are scaled by `demoTimeScale` so a 2h demo can show weeks of
 * simulated behavior; jitter is drawn from the persona's jitterPct.
 */

import { Agent } from "./agent.js";
import { jittered, scaleForDemo } from "./personas.js";
import { topUpParty } from "./provisioner.js";

const iso = () => new Date().toISOString();

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

export class VirtualBot {
  #agent;
  #keyPath;
  #tasks;
  #stats;
  #persona;
  #demoTimeScale;
  #mcpServerUrl;
  #billingApiKey;
  #running = false;
  #stopped = false;
  #dormant = false;
  #released = false;
  #onRelease;
  #taskIndex = 0;
  #tasksRun = 0;
  #topUpsDone = 0;
  #nextTaskAt = 0;
  #nextTopUpAt = 0;

  constructor({
    keyPath,
    serverUrl,
    tasks,
    stats,
    persona,
    demoTimeScale = 1,
    billingApiKey = null,
    onRelease = null,
  }) {
    if (!persona) throw new Error("VirtualBot: persona is required");
    this.#agent = new Agent(serverUrl);
    this.#keyPath = keyPath;
    this.#tasks = tasks;
    this.#stats = stats;
    this.#persona = persona;
    this.#demoTimeScale = demoTimeScale;
    this.#mcpServerUrl = serverUrl;
    this.#billingApiKey = billingApiKey;
    this.#onRelease = onRelease;
  }

  get partyId() {
    return this.#agent.partyId;
  }

  get persona() {
    return this.#persona;
  }

  get dormant() {
    return this.#dormant;
  }

  async authenticate() {
    return this.#agent.authenticate(this.#keyPath);
  }

  stop() {
    this.#stopped = true;
  }

  #scheduleNextTask(now) {
    const base = scaleForDemo(this.#persona.taskIntervalMs, this.#demoTimeScale);
    this.#nextTaskAt = now + jittered(base, this.#persona.jitterPct);
  }

  #scheduleNextTopUp(now) {
    if (!this.#persona.topUpIntervalMs || !this.#billingApiKey) {
      this.#nextTopUpAt = Infinity;
      return;
    }
    const base = scaleForDemo(this.#persona.topUpIntervalMs, this.#demoTimeScale);
    this.#nextTopUpAt = now + jittered(base, this.#persona.jitterPct);
  }

  async #runTask() {
    const task = this.#tasks[this.#taskIndex % this.#tasks.length];
    this.#taskIndex++;
    try {
      const result = await this.#agent.executeTask(task);
      this.#stats.addTaskResults([result], { persona: this.#persona.name });
      this.#tasksRun++;
    } catch (err) {
      console.log(
        `[EVENT] ${iso()} bot_task_crash partyId=${this.partyId?.slice(0, 40) || "unknown"} persona=${this.#persona.name} error=${JSON.stringify(err.message)}`
      );
    }
  }

  async #runTopUp() {
    try {
      await topUpParty({
        mcpServerUrl: this.#mcpServerUrl,
        billingApiKey: this.#billingApiKey,
        partyId: this.partyId,
        amountCC: this.#persona.topUpAmountCC,
        personaName: this.#persona.name,
      });
      this.#topUpsDone++;
      this.#stats.addTopUp?.({
        partyId: this.partyId,
        persona: this.#persona.name,
        amountCC: this.#persona.topUpAmountCC,
      });
    } catch (err) {
      console.log(
        `[WARN] ${iso()} bot_topup_failed partyId=${this.partyId?.slice(0, 40) || "unknown"} persona=${this.#persona.name} error=${JSON.stringify(err.message)}`
      );
    }
  }

  #goDormant(reason) {
    if (this.#dormant) return;
    this.#dormant = true;
    this.#stats.markDormant?.({ partyId: this.partyId, persona: this.#persona.name, reason });
    console.log(
      `[EVENT] ${iso()} bot_dormant partyId=${this.partyId?.slice(0, 40) || "unknown"} persona=${this.#persona.name} reason=${reason} tasksRun=${this.#tasksRun}`
    );
    this.#fireRelease();
  }

  #fireRelease() {
    if (this.#released) return;
    this.#released = true;
    if (!this.#onRelease) return;
    try {
      this.#onRelease();
    } catch (err) {
      console.log(
        `[WARN] ${iso()} bot_release_cb_failed partyId=${this.partyId?.slice(0, 40) || "unknown"} error=${err.message}`
      );
    }
  }

  startLoop() {
    if (this.#running) return;
    this.#running = true;

    (async () => {
      const now = Date.now();
      this.#scheduleNextTask(now);
      this.#scheduleNextTopUp(now);

      while (!this.#stopped && !this.#dormant) {
        const nowTick = Date.now();
        const nextEvent = Math.min(this.#nextTaskAt, this.#nextTopUpAt);
        const wait = Math.max(100, nextEvent - nowTick);
        await sleep(wait);
        if (this.#stopped) break;

        const fired = Date.now();
        if (fired >= this.#nextTaskAt) {
          await this.#runTask();
          if (
            this.#persona.lifetimeTasks &&
            this.#tasksRun >= this.#persona.lifetimeTasks
          ) {
            this.#goDormant("lifetime_cap");
            break;
          }
          this.#scheduleNextTask(Date.now());
        } else if (fired >= this.#nextTopUpAt) {
          await this.#runTopUp();
          this.#scheduleNextTopUp(Date.now());
        }
      }
      this.#running = false;
    })();
  }
}
