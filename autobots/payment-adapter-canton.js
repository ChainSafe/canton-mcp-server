/**
 * Canton Coin Payment Adapter
 *
 * Implements Ed25519 challenge-response authentication for Canton MCP server.
 * Uses Node.js built-in crypto module (no external deps).
 */

import { readFileSync } from "fs";
import crypto from "crypto";
import { PaymentAdapter } from "./payment-adapter-interface.js";

export class CantonPaymentAdapter extends PaymentAdapter {
  #partyId = "";
  #fingerprint = "";
  #publicKeyB64 = "";
  #privateKeyDer = null;
  #token = "";
  #tokenExpiresAt = 0;

  get partyId() {
    return this.#partyId;
  }
  get token() {
    return this.#token;
  }
  get fingerprint() {
    return this.#fingerprint;
  }

  async authenticate(keyFilePath, serverUrl) {
    const keyData = JSON.parse(readFileSync(keyFilePath, "utf8"));
    this.#partyId = keyData.partyId;
    this.#fingerprint = keyData.fingerprint;
    this.#publicKeyB64 = keyData.publicKey;

    // Build DER-encoded Ed25519 private key for Node crypto
    const privKeyBuf = Buffer.from(keyData.privateKey, "base64");
    this.#privateKeyDer = crypto.createPrivateKey({
      key: Buffer.concat([
        Buffer.from("302e020100300506032b657004220420", "hex"),
        privKeyBuf,
      ]),
      format: "der",
      type: "pkcs8",
    });

    return this.#doAuth(serverUrl);
  }

  async refreshToken(serverUrl) {
    if (Date.now() < this.#tokenExpiresAt - 60_000) {
      return { token: this.#token }; // Still valid, skip refresh
    }
    return this.#doAuth(serverUrl);
  }

  async #doAuth(serverUrl) {
    const iso = () => new Date().toISOString();
    console.log(`[EVENT] ${iso()} auth_start partyId=${this.#partyId.slice(0, 40)}`);

    // Step 1: Request challenge
    let challengeRes;
    try {
      challengeRes = await fetch(`${serverUrl}/auth/challenge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          partyId: this.#partyId,
          publicKey: this.#publicKeyB64,
        }),
      });
    } catch (err) {
      const code = err.cause?.code || err.code || "FETCH_ERROR";
      console.log(`[EVENT] ${iso()} auth_error phase=challenge code=${code} error=${JSON.stringify(err.message)}`);
      throw new Error(`AUTH_FAILED (network ${code}): ${err.message}`);
    }

    if (!challengeRes.ok) {
      const body = await challengeRes.text();
      console.log(`[EVENT] ${iso()} auth_error phase=challenge status=${challengeRes.status} body=${JSON.stringify(body.slice(0, 500))}`);
      throw new Error(`AUTH_FAILED (challenge HTTP ${challengeRes.status}): ${body}`);
    }
    const challengeData = await challengeRes.json();
    const challenge = challengeData?.challenge;
    if (!challenge) {
      console.log(`[EVENT] ${iso()} auth_error phase=challenge error="No challenge in response: ${JSON.stringify(challengeData).slice(0, 200)}"`);
      throw new Error(`AUTH_FAILED (no challenge in response)`);
    }

    // Step 2: Sign challenge
    const challengeBytes = Buffer.from(challenge, "base64");
    const signature = crypto.sign(null, challengeBytes, this.#privateKeyDer);
    const signatureB64 = signature.toString("base64");

    // Step 3: Verify and get JWT
    let verifyRes;
    try {
      verifyRes = await fetch(`${serverUrl}/auth/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          partyId: this.#partyId,
          challenge,
          signature: signatureB64,
        }),
      });
    } catch (err) {
      const code = err.cause?.code || err.code || "FETCH_ERROR";
      console.log(`[EVENT] ${iso()} auth_error phase=verify code=${code} error=${JSON.stringify(err.message)}`);
      throw new Error(`AUTH_FAILED (network ${code}): ${err.message}`);
    }

    if (!verifyRes.ok) {
      const body = await verifyRes.text();
      console.log(`[EVENT] ${iso()} auth_error phase=verify status=${verifyRes.status} body=${JSON.stringify(body.slice(0, 500))}`);
      throw new Error(`AUTH_FAILED (verify HTTP ${verifyRes.status}): ${body}`);
    }
    const verifyData = await verifyRes.json();
    const token = verifyData?.token;
    if (!token) {
      console.log(`[EVENT] ${iso()} auth_error phase=verify error="No token in response: ${JSON.stringify(verifyData).slice(0, 200)}"`);
      throw new Error(`AUTH_FAILED (no token in response)`);
    }
    this.#token = token;
    this.#tokenExpiresAt = Date.now() + 55 * 60_000; // 55 min (JWT is 1hr)

    console.log(`[EVENT] ${iso()} auth_ok`);
    return { token, partyId: this.#partyId, fingerprint: this.#fingerprint };
  }

  async getBalance(billingPortalUrl) {
    try {
      const res = await fetch(
        `${billingPortalUrl}/api/balance?party=${encodeURIComponent(this.#partyId)}`
      );
      if (!res.ok) {
        console.log(`[WARN] ${new Date().toISOString()} Balance check failed: HTTP ${res.status}`);
        return { balance: 0, totalCharged: 0, totalCredited: 0 };
      }
      return await res.json();
    } catch (err) {
      console.log(`[WARN] ${new Date().toISOString()} Balance check error: ${err.message}`);
      return { balance: 0, totalCharged: 0, totalCredited: 0 };
    }
  }
}
