/**
 * Persona definitions for autobot simulation.
 *
 * Each persona describes one type of user. VirtualBots get a persona at spawn
 * time and use its fields to shape their own cadence (task interval, top-up
 * schedule, lifetime cap). The orchestrator draws personas from the weighted
 * distribution when it provisions new identities.
 *
 * Cadences are specified in real-world days/weeks. The orchestrator's
 * `demoTimeScale` multiplier (1 = real time, 168 = 1 hour ≈ 1 week) is applied
 * at runtime so demos can show cohort behavior in a short window without
 * changing these numbers.
 *
 * All intervals carry ±jitterPct variance so the simulation doesn't produce
 * suspicious metronome-like timing.
 */

const DAY_MS = 24 * 60 * 60 * 1000;

export const PERSONAS = {
  casual: {
    name: "casual",
    weight: 0.6,                   // ~60% of population
    taskIntervalMs: 15 * DAY_MS,   // roughly one task every two weeks
    topUpIntervalMs: 45 * DAY_MS,  // top up once every month or two
    topUpAmountCC: 2,              // small top-ups, mirrors low-usage user
    lifetimeTasks: null,           // open-ended
    jitterPct: 0.5,                // wide spread — some users are very sparse
  },
  regular: {
    name: "regular",
    weight: 0.3,                   // ~30% of population
    taskIntervalMs: 2 * DAY_MS,    // a few tasks per week
    topUpIntervalMs: 18 * DAY_MS,  // top up roughly every 2-3 weeks
    topUpAmountCC: 8,
    lifetimeTasks: null,
    jitterPct: 0.4,
  },
  churned: {
    name: "churned",
    weight: 0.1,                   // ~10% of population
    taskIntervalMs: 3 * DAY_MS,    // 1-2 runs in first week, then dormant
    topUpIntervalMs: null,         // never tops up (uses starting balance)
    topUpAmountCC: 0,
    lifetimeTasks: 2,              // stops after 2 tasks → visible churn
    jitterPct: 0.5,
  },
};

/**
 * Pick a persona name weighted by its `weight` field. Weights are re-normalized
 * so callers don't need to ensure they sum to 1.
 */
export function drawPersona(personas = PERSONAS, rng = Math.random) {
  const entries = Object.values(personas);
  const total = entries.reduce((s, p) => s + p.weight, 0);
  let r = rng() * total;
  for (const p of entries) {
    r -= p.weight;
    if (r <= 0) return p;
  }
  return entries[entries.length - 1];
}

/**
 * Apply a symmetric ±jitterPct multiplier to an interval.
 * jitterPct=0.4 → returns something in [0.6×, 1.4×] of base.
 */
export function jittered(baseMs, jitterPct, rng = Math.random) {
  if (!Number.isFinite(baseMs) || baseMs <= 0) return baseMs;
  const factor = 1 + (rng() * 2 - 1) * jitterPct;
  return Math.max(100, Math.round(baseMs * factor));
}

/**
 * Scale a real-world interval by the demo time compression factor.
 * demoTimeScale=168 → one real hour represents one real week of behavior.
 */
export function scaleForDemo(ms, demoTimeScale) {
  if (!demoTimeScale || demoTimeScale <= 1) return ms;
  return Math.max(100, Math.round(ms / demoTimeScale));
}
