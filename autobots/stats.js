/**
 * StatsAggregator — tracks autobots task results across iterations.
 *
 * Maintains:
 *  - Cumulative totals since startup
 *  - Rolling 1-hour stats (ring buffer, auto-prunes >1h old)
 *  - Rolling 1-minute stats
 *
 * Emits structured single-line status logs for Loki/journalctl.
 */

const MAX_BUFFER = 3600; // cap ring buffer (1 task/sec for 1 hour)
const HOUR_MS = 60 * 60 * 1000;
const MINUTE_MS = 60 * 1000;

export class StatsAggregator {
  #startedAt = Date.now();
  #iterations = 0;
  #buffer = []; // [{ts, durationMs, ccSpent, pass, error, action}]
  #cumulative = {
    tasks: 0,
    passed: 0,
    failed: 0,
    errors: 0,
    ccSpent: 0,
    totalDurationMs: 0,
  };
  #consecutiveEmptyIterations = 0; // for outage detection
  #consecutiveAllErrorIterations = 0;
  #spawnedBots = new Set();
  #dormantBots = new Set();
  // Persona breakdown: { [personaName]: { tasks, topUps, topUpCC, spawned, dormant } }
  #byPersona = {};

  #persona(name) {
    if (!name) name = "unknown";
    if (!this.#byPersona[name]) {
      this.#byPersona[name] = { tasks: 0, topUps: 0, topUpCC: 0, spawned: 0, dormant: 0 };
    }
    return this.#byPersona[name];
  }

  /** Feed individual task results as they complete (real-time). */
  addTaskResults(results, meta = {}) {
    const now = Date.now();
    const personaName = meta.persona;
    for (const r of results) {
      this.#buffer.push({
        ts: now,
        durationMs: r.durationMs,
        ccSpent: r.ccSpent,
        pass: r.pass,
        error: !!r.error,
        action: r.action,
        persona: personaName,
      });
      this.#cumulative.tasks++;
      this.#cumulative.ccSpent += r.ccSpent;
      this.#cumulative.totalDurationMs += r.durationMs;
      if (r.error) this.#cumulative.errors++;
      else if (r.pass) this.#cumulative.passed++;
      else this.#cumulative.failed++;
      if (personaName) this.#persona(personaName).tasks++;
    }
    this.#prune();
  }

  /** Record a top-up event (persona-tagged). */
  addTopUp({ partyId, persona, amountCC } = {}) {
    const row = this.#persona(persona);
    row.topUps++;
    row.topUpCC += Number(amountCC) || 0;
  }

  /** Mark a bot as dormant (lifetime cap reached or similar). */
  markDormant({ partyId, persona } = {}) {
    if (partyId) this.#dormantBots.add(partyId);
    const row = this.#persona(persona);
    row.dormant++;
  }

  /** Record that a new bot identity has joined the fleet (growth mode). */
  addBotSpawned(partyId, personaName) {
    if (partyId) this.#spawnedBots.add(partyId);
    if (personaName) this.#persona(personaName).spawned++;
  }

  get botCount() {
    return this.#spawnedBots.size;
  }

  get dormantCount() {
    return this.#dormantBots.size;
  }

  get activeCount() {
    return Math.max(0, this.#spawnedBots.size - this.#dormantBots.size);
  }

  get personaBreakdown() {
    // Return a stable shallow copy so callers can log without mutating internals.
    const out = {};
    for (const [name, row] of Object.entries(this.#byPersona)) {
      out[name] = { ...row, topUpCC: +row.topUpCC.toFixed(2) };
    }
    return out;
  }

  /** Mark end of an iteration for outage detection. */
  endIteration(results, iteration) {
    this.#iterations = iteration;
    const iterErrors = results.filter((r) => r.error).length;

    if (results.length === 0) {
      this.#consecutiveEmptyIterations++;
    } else {
      this.#consecutiveEmptyIterations = 0;
    }

    if (results.length > 0 && iterErrors === results.length) {
      this.#consecutiveAllErrorIterations++;
    } else {
      this.#consecutiveAllErrorIterations = 0;
    }
  }

  #prune() {
    const cutoff = Date.now() - HOUR_MS;
    // Find first entry within the window (O(n) scan, no O(n) shift per entry)
    let firstValid = 0;
    while (firstValid < this.#buffer.length && this.#buffer[firstValid].ts < cutoff) {
      firstValid++;
    }
    if (firstValid > 0) {
      this.#buffer = this.#buffer.slice(firstValid);
    }
    // Hard cap
    if (this.#buffer.length > MAX_BUFFER) {
      this.#buffer = this.#buffer.slice(-MAX_BUFFER);
    }
  }

  #windowStats(windowMs) {
    const cutoff = Date.now() - windowMs;
    const entries = this.#buffer.filter((e) => e.ts >= cutoff);
    const tasks = entries.length;
    if (tasks === 0) {
      return { tasks: 0, passed: 0, failed: 0, errors: 0, ccSpent: 0, avgDurationMs: 0, p95DurationMs: 0, actionCounts: {} };
    }
    let passed = 0, failed = 0, errors = 0, ccSpent = 0;
    const durations = [];
    const actionCounts = {};
    for (const e of entries) {
      if (e.error) errors++;
      else if (e.pass) passed++;
      else failed++;
      ccSpent += e.ccSpent;
      durations.push(e.durationMs);
      actionCounts[e.action] = (actionCounts[e.action] || 0) + 1;
    }
    durations.sort((a, b) => a - b);
    const avg = Math.round(durations.reduce((s, d) => s + d, 0) / durations.length);
    const p95 = durations[Math.floor(durations.length * 0.95)] || durations[durations.length - 1];
    return { tasks, passed, failed, errors, ccSpent: +ccSpent.toFixed(2), avgDurationMs: avg, p95DurationMs: p95, actionCounts };
  }

  snapshot() {
    this.#prune();
    const uptimeMs = Date.now() - this.#startedAt;
    const hour = this.#windowStats(HOUR_MS);
    const minute = this.#windowStats(MINUTE_MS);
    const lastEntry = this.#buffer[this.#buffer.length - 1];
    return {
      uptime: formatDuration(uptimeMs),
      startedAt: new Date(this.#startedAt).toISOString(),
      cumulative: {
        iterations: this.#iterations,
        tasks: this.#cumulative.tasks,
        passed: this.#cumulative.passed,
        failed: this.#cumulative.failed,
        errors: this.#cumulative.errors,
        passRate: this.#cumulative.tasks > 0 ? +(this.#cumulative.passed / this.#cumulative.tasks).toFixed(3) : 0,
        ccSpent: +this.#cumulative.ccSpent.toFixed(2),
        avgDurationMs: this.#cumulative.tasks > 0 ? Math.round(this.#cumulative.totalDurationMs / this.#cumulative.tasks) : 0,
      },
      hour: { ...hour, passRate: hour.tasks > 0 ? +(hour.passed / hour.tasks).toFixed(3) : 0 },
      minute: { tasks: minute.tasks, passed: minute.passed, errors: minute.errors, lastTaskAt: lastEntry ? new Date(lastEntry.ts).toISOString() : null },
    };
  }

  formatStatus() {
    const s = this.snapshot();
    const now = new Date().toISOString().slice(0, 19) + "Z";
    const m = s.minute;
    const h = s.hour;
    const c = s.cumulative;
    let botsSegment = "";
    if (this.#spawnedBots.size > 0) {
      botsSegment = ` bots=${this.#spawnedBots.size}(active=${this.activeCount},dormant=${this.dormantCount}) |`;
    }
    const personaSegment = this.#personaSegment();
    return (
      `[STATUS] ${now} uptime=${s.uptime} |${botsSegment} ` +
      `last_min: tasks=${m.tasks} passed=${m.passed} errors=${m.errors} | ` +
      `hour: tasks=${h.tasks} pass_rate=${(h.passRate * 100).toFixed(1)}% cc=${h.ccSpent.toFixed(2)} avg=${h.avgDurationMs}ms p95=${h.p95DurationMs}ms | ` +
      `total: tasks=${c.tasks} pass_rate=${(c.passRate * 100).toFixed(1)}% cc=${c.ccSpent.toFixed(2)} iter=${c.iterations}` +
      personaSegment
    );
  }

  #personaSegment() {
    const entries = Object.entries(this.#byPersona);
    if (entries.length === 0) return "";
    const parts = entries
      .sort(([a], [b]) => a.localeCompare(b))
      .map(
        ([name, r]) =>
          `${name}(spawn=${r.spawned},tasks=${r.tasks},topups=${r.topUps},topupCC=${r.topUpCC.toFixed(2)},dormant=${r.dormant})`
      );
    return ` | personas: ${parts.join(" ")}`;
  }

  get consecutiveAllErrorIterations() {
    return this.#consecutiveAllErrorIterations;
  }
  get consecutiveEmptyIterations() {
    return this.#consecutiveEmptyIterations;
  }
}

function formatDuration(ms) {
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h${m}m`;
  if (m > 0) return `${m}m${sec}s`;
  return `${sec}s`;
}
