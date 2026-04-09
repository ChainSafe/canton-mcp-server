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
      return { token: this.#token };
    }
    return this.#doAuth(serverUrl);
  }

  async #doAuth(serverUrl) {
    // Step 1: Request challenge
    const challengeRes = await fetch(`${serverUrl}/auth/challenge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        partyId: this.#partyId,
        publicKey: this.#publicKeyB64,
      }),
    });
    if (!challengeRes.ok) {
      throw new Error(
        `Challenge failed: ${challengeRes.status} ${await challengeRes.text()}`
      );
    }
    const { challenge } = await challengeRes.json();

    // Step 2: Sign challenge
    const challengeBytes = Buffer.from(challenge, "base64");
    const signature = crypto.sign(null, challengeBytes, this.#privateKeyDer);
    const signatureB64 = signature.toString("base64");

    // Step 3: Verify and get JWT
    const verifyRes = await fetch(`${serverUrl}/auth/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        partyId: this.#partyId,
        challenge,
        signature: signatureB64,
      }),
    });
    if (!verifyRes.ok) {
      throw new Error(
        `Verify failed: ${verifyRes.status} ${await verifyRes.text()}`
      );
    }
    const { token } = await verifyRes.json();
    this.#token = token;
    this.#tokenExpiresAt = Date.now() + 55 * 60_000; // 55 min (JWT is 1hr)

    return { token, partyId: this.#partyId, fingerprint: this.#fingerprint };
  }

  async getBalance(billingPortalUrl) {
    const res = await fetch(
      `${billingPortalUrl}/api/balance?party=${encodeURIComponent(this.#partyId)}`
    );
    if (!res.ok) return { balance: 0, totalCharged: 0, totalCredited: 0 };
    return res.json();
  }
}
