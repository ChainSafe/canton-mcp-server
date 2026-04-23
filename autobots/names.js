/**
 * Realistic username generation for autobot party hints.
 *
 * Party IDs look like `<hint>::<fingerprint>` on Canton; the hint is the
 * human-readable part a dashboard shows. Rather than `autobot-42`, we want
 * hints that look like real usernames — first names, first.last patterns,
 * handle + digits — so stakeholder views feel organic.
 *
 * All hints are lowercased `[a-z0-9_]+` (Canton-safe). No hyphens, so they
 * visually distinguish from any pre-existing `autobot-N` keys.
 */

const FIRST_NAMES = [
  "alex", "sam", "jamie", "taylor", "jordan", "morgan", "riley", "casey",
  "quinn", "avery", "chris", "maya", "priya", "arjun", "raj", "ananya",
  "yuki", "ken", "haruto", "mei", "wei", "jun", "lin", "chen",
  "sofia", "diego", "luca", "emma", "liam", "noah", "olivia", "ava",
  "sarah", "mike", "dave", "jen", "rachel", "ben", "nate", "kate",
  "amir", "leila", "omar", "zara", "kwame", "adaeze", "tomas", "anna",
  "erik", "lars", "freya", "nora", "finn", "ivy", "eli", "ada",
  "hiro", "miko", "sana", "aiko", "ravi", "neha", "vikram", "asha",
];

const LAST_NAMES = [
  "smith", "jones", "brown", "taylor", "lee", "wang", "kim", "patel",
  "singh", "garcia", "martinez", "lopez", "kumar", "sharma", "tanaka",
  "suzuki", "nguyen", "tran", "cohen", "muller", "schmidt", "novak",
  "rossi", "bianchi", "silva", "oliveira", "kowalski", "andersson",
  "kapoor", "chen", "liu", "zhang", "yamada", "ito", "park", "choi",
];

const HANDLE_WORDS = [
  "fox", "wolf", "raven", "kite", "otter", "atlas", "nova", "echo",
  "river", "orbit", "pixel", "drift", "spark", "bloom", "loop", "forge",
  "neon", "sable", "lumen", "quartz", "flux", "cipher", "nebula",
];

const HANDLE_ADJECTIVES = [
  "cool", "silent", "neon", "fast", "lucky", "quiet", "brave", "sunny",
  "misty", "shady", "wild", "urban", "retro", "rapid", "clever",
];

function pick(arr, rng) {
  return arr[Math.floor(rng() * arr.length)];
}

function maybe(rng, p) {
  return rng() < p;
}

function twoDigit(rng) {
  // 10..99 — avoid the very common "1"/"2" suffix that looks incremental
  return String(10 + Math.floor(rng() * 90));
}

/**
 * Generate one realistic username-style party hint.
 * Patterns are roughly distributed across common real-world shapes.
 */
export function generateHint(rng = Math.random) {
  const pattern = rng();
  const first = pick(FIRST_NAMES, rng);
  const last = pick(LAST_NAMES, rng);
  const lastInitial = last[0];

  if (pattern < 0.25) {
    // "alex"
    return first;
  }
  if (pattern < 0.5) {
    // "alex42"
    return `${first}${twoDigit(rng)}`;
  }
  if (pattern < 0.65) {
    // "alex_kim"
    return `${first}_${last}`;
  }
  if (pattern < 0.8) {
    // "alexk" or "alexk21"
    const base = `${first}${lastInitial}`;
    return maybe(rng, 0.5) ? `${base}${twoDigit(rng)}` : base;
  }
  // "coolfox7" / "neonkite42"
  const adj = pick(HANDLE_ADJECTIVES, rng);
  const word = pick(HANDLE_WORDS, rng);
  const digit = maybe(rng, 0.6) ? String(Math.floor(rng() * 1000)) : "";
  return `${adj}${word}${digit}`;
}

/**
 * Generate a hint that doesn't collide with any existing one. Collision on
 * hint is not a Canton uniqueness violation (fingerprint disambiguates), but
 * local keyfiles live at `<hint>.json` so filename collision matters.
 *
 * @param {(hint: string) => boolean} exists — returns true if hint already used
 * @param {number} maxTries
 */
export function generateUniqueHint(exists, rng = Math.random, maxTries = 50) {
  for (let i = 0; i < maxTries; i++) {
    const h = generateHint(rng);
    if (!exists(h)) return h;
  }
  // Fallback: append random hex suffix
  return `${generateHint(rng)}${Math.floor(rng() * 1e6).toString(36)}`;
}
