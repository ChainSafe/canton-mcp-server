/**
 * PartyPool — caps the number of Canton parties the orchestrator will
 * provision and recycles them across bot lifetimes. The validator app caps
 * at ~200 parties per validator, so burning a fresh party for every
 * autobot (including churned ones) is not sustainable.
 *
 * Model:
 *   - `idle`  — keyfiles available for a new bot to adopt
 *   - `inUse` — keyfiles currently bound to a running bot
 *   - `size = idle + inUse`, capped at `maxSize`
 *
 * checkout() prefers an idle keyfile; only provisions a new party when the
 * pool has headroom. release(keyPath) returns a keyfile to idle so another
 * bot can reuse it.
 *
 * Existing keyfiles in keysDir are adopted as idle on init(), so restarts
 * and scheduled runs reuse the same pool automatically.
 */

import { listExistingKeys, provisionNewParty } from "./provisioner.js";

const iso = () => new Date().toISOString();

export class PartyPool {
  #billingPortalUrl;
  #keysDir;
  #maxSize;
  #idle = new Set();
  #inUse = new Set();

  constructor({ billingPortalUrl, keysDir, maxSize }) {
    if (!billingPortalUrl) throw new Error("PartyPool: billingPortalUrl is required");
    if (!keysDir) throw new Error("PartyPool: keysDir is required");
    if (!maxSize || maxSize <= 0) {
      throw new Error("PartyPool: maxSize must be a positive integer");
    }
    this.#billingPortalUrl = billingPortalUrl;
    this.#keysDir = keysDir;
    this.#maxSize = maxSize;
  }

  /**
   * Adopt any existing keyfiles in keysDir as idle. Safe to call once at
   * startup.
   */
  init() {
    const existing = listExistingKeys(this.#keysDir);
    for (const keyPath of existing) this.#idle.add(keyPath);
    return { adopted: existing.length, capacity: this.#maxSize };
  }

  get size() { return this.#idle.size + this.#inUse.size; }
  get idleCount() { return this.#idle.size; }
  get inUseCount() { return this.#inUse.size; }
  get maxSize() { return this.#maxSize; }

  /**
   * Reserve a party for a new bot. Prefers idle existing keyfiles; only
   * provisions a new party when the pool has headroom.
   *
   * @returns {Promise<{keyPath: string, reused: boolean} | null>} null when
   *   the pool is exhausted (all slots checked out AND size >= maxSize).
   */
  async checkout() {
    const first = this.#idle.values().next();
    if (!first.done) {
      const keyPath = first.value;
      this.#idle.delete(keyPath);
      this.#inUse.add(keyPath);
      return { keyPath, reused: true };
    }
    if (this.size >= this.#maxSize) return null;
    const keyPath = await provisionNewParty({
      billingPortalUrl: this.#billingPortalUrl,
      keysDir: this.#keysDir,
    });
    this.#inUse.add(keyPath);
    return { keyPath, reused: false };
  }

  /**
   * Return a keyfile to idle. No-op if it isn't tracked as in-use (covers
   * double-release from retries / shutdown races).
   */
  release(keyPath) {
    if (!this.#inUse.delete(keyPath)) return false;
    this.#idle.add(keyPath);
    console.log(
      `[EVENT] ${iso()} party_recycled keyPath=${keyPath} poolInUse=${this.#inUse.size} poolIdle=${this.#idle.size}`
    );
    return true;
  }
}
