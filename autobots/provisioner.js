/**
 * Provisioner — creates new Canton external parties for autobot growth mode.
 *
 * Registration flow (devnet/mainnet):
 *   1. Generate Ed25519 keypair locally, derive Canton fingerprint and partyId
 *   2. POST /api/register-party/generate  — billing portal asks the validator
 *      to prepare the topology transactions
 *   3. Sign each returned topology-tx hash with the party's private key
 *   4. POST /api/register-party/submit    — billing portal submits the signed
 *      txs to the validator and polls the synchronizer until visible
 *
 * We skip the optional transfer-preapproval step: autobots top up via the
 * billing API key path (`/billing/credit`), which writes a CreditReceipt on
 * the MCP billing ledger without moving CC on-chain, so they don't need a
 * preapproval to receive funds.
 *
 * Party hints are realistic-looking usernames (see names.js) rather than
 * `autobot-N`, so stakeholder views don't scream "synthetic."
 */

import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "fs";
import { resolve } from "path";
import crypto from "crypto";
import { generateUniqueHint } from "./names.js";

const iso = () => new Date().toISOString();

// PKCS#8 DER prefix for an Ed25519 private key; the 32-byte raw seed follows.
const PKCS8_ED25519_PREFIX = Buffer.from(
  "302e020100300506032b657004220420",
  "hex"
);
// Canton hash-purpose prefix for key fingerprints (hashPurpose = 12).
const HASH_PURPOSE = Buffer.from([0x00, 0x00, 0x00, 0x0c]);

function generateEd25519Keypair() {
  const { publicKey, privateKey } = crypto.generateKeyPairSync("ed25519");
  const pubDer = publicKey.export({ format: "der", type: "spki" });
  const pubRaw = pubDer.subarray(pubDer.length - 32);
  const privDer = privateKey.export({ format: "der", type: "pkcs8" });
  const privRaw = privDer.subarray(privDer.length - 32);
  return { publicKey: pubRaw, privateKey: privRaw };
}

function fingerprintFromPublicKey(publicKey) {
  const digest = crypto
    .createHash("sha256")
    .update(Buffer.concat([HASH_PURPOSE, publicKey]))
    .digest("hex");
  return `1220${digest}`;
}

/**
 * Build a Node crypto KeyObject for an Ed25519 raw private key.
 */
function ed25519PrivateKeyObject(privateRaw) {
  return crypto.createPrivateKey({
    key: Buffer.concat([PKCS8_ED25519_PREFIX, privateRaw]),
    format: "der",
    type: "pkcs8",
  });
}

/**
 * Sign a hex-encoded topology hash with an Ed25519 private key. Matches the
 * browser-ed25519 signTopologyHash helper the billing portal UI uses.
 * @returns hex-encoded signature
 */
function signTopologyHashHex(hashHex, privateKeyObj) {
  const hashBytes = Buffer.from(hashHex, "hex");
  const signature = crypto.sign(null, hashBytes, privateKeyObj);
  return signature.toString("hex");
}

/**
 * List existing keyfiles in keysDir. Returns absolute paths in insertion order.
 */
export function listExistingKeys(keysDir) {
  try {
    mkdirSync(keysDir, { recursive: true });
  } catch {}
  return readdirSync(keysDir)
    .filter((f) => f.endsWith(".json"))
    .map((f) => resolve(keysDir, f))
    .sort();
}

function readUsedHints(keysDir) {
  try {
    return new Set(
      readdirSync(keysDir)
        .filter((f) => f.endsWith(".json"))
        .map((f) => f.replace(/\.json$/, ""))
    );
  } catch {
    return new Set();
  }
}

/**
 * Provision a new Canton external party on devnet/mainnet via the billing
 * portal. Writes a keyfile to `<keysDir>/<hint>.json` and returns its path.
 */
export async function provisionNewParty({ billingPortalUrl, keysDir }) {
  if (!billingPortalUrl) {
    throw new Error("provisionNewParty: billingPortalUrl is required");
  }
  if (!keysDir) {
    throw new Error("provisionNewParty: keysDir is required");
  }
  mkdirSync(keysDir, { recursive: true });

  const usedHints = readUsedHints(keysDir);
  const hint = generateUniqueHint((h) => usedHints.has(h));

  const { publicKey, privateKey } = generateEd25519Keypair();
  const fingerprint = fingerprintFromPublicKey(publicKey);
  const partyId = `${hint}::${fingerprint}`;
  const publicKeyB64 = publicKey.toString("base64");
  const privateKeyB64 = privateKey.toString("base64");

  const base = billingPortalUrl.replace(/\/$/, "");
  const privateKeyObj = ed25519PrivateKeyObject(privateKey);

  // Step 1: ask the validator to generate topology transactions.
  let genRes;
  try {
    genRes = await fetch(`${base}/api/register-party/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ partyId, publicKey: publicKeyB64 }),
    });
  } catch (err) {
    throw new Error(`PROVISION_FAILED (generate network): ${err.message}`);
  }

  if (!genRes.ok) {
    const body = (await genRes.text()).slice(0, 500);
    throw new Error(`PROVISION_FAILED (generate HTTP ${genRes.status}): ${body}`);
  }
  const genData = await genRes.json();

  // Write the keyfile early so if submit crashes we can still reuse the party.
  const keyfile = { partyId, privateKey: privateKeyB64, publicKey: publicKeyB64, fingerprint };
  const keyPath = resolve(keysDir, `${hint}.json`);
  writeFileSync(keyPath, JSON.stringify(keyfile, null, 2), { mode: 0o600 });

  if (genData.alreadyRegistered) {
    console.log(
      `[EVENT] ${iso()} party_provisioned partyId=${partyId.slice(0, 50)}... hint=${hint} already_registered=true`
    );
    return keyPath;
  }

  const topologyTxs = genData.topologyTxs || [];
  if (topologyTxs.length === 0) {
    throw new Error(
      `PROVISION_FAILED (generate returned no topologyTxs): ${JSON.stringify(genData).slice(0, 300)}`
    );
  }

  // Step 2: sign each topology tx hash.
  const signedTopologyTxs = topologyTxs.map((tx) => ({
    topology_tx: tx.topology_tx,
    signed_hash: signTopologyHashHex(tx.hash, privateKeyObj),
  }));

  // Step 3: submit. The billing portal polls the synchronizer before returning.
  let submitRes;
  try {
    submitRes = await fetch(`${base}/api/register-party/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        signedTopologyTxs,
        publicKey: publicKeyB64,
        keyFingerprint: genData.keyFingerprint,
        originalHash: topologyTxs[0].hash,
        partyId,
      }),
    });
  } catch (err) {
    throw new Error(`PROVISION_FAILED (submit network): ${err.message}`);
  }

  if (!submitRes.ok) {
    const body = (await submitRes.text()).slice(0, 500);
    throw new Error(`PROVISION_FAILED (submit HTTP ${submitRes.status}): ${body}`);
  }
  const submitData = await submitRes.json();
  if (!submitData.success) {
    throw new Error(`PROVISION_FAILED: ${JSON.stringify(submitData).slice(0, 300)}`);
  }

  console.log(
    `[EVENT] ${iso()} party_provisioned partyId=${partyId.slice(0, 50)}... hint=${hint} already_existed=${!!submitData.already_existed}`
  );
  return keyPath;
}

/**
 * Credit CC to an autobot party via MCP server's /billing/credit endpoint
 * (authed with X-Billing-API-Key). Creates a CreditReceipt on the MCP billing
 * ledger — no on-chain CC transfer, no preapproval needed.
 *
 * `transferId` is required by the endpoint; when authorized via API key it
 * functions as a dedup key rather than a real Canton transaction ID.
 */
export async function topUpParty({
  mcpServerUrl,
  billingApiKey,
  partyId,
  amountCC,
  personaName,
}) {
  if (!mcpServerUrl) throw new Error("topUpParty: mcpServerUrl is required");
  if (!billingApiKey) throw new Error("topUpParty: billingApiKey is required");
  if (!partyId) throw new Error("topUpParty: partyId is required");
  if (!amountCC || amountCC <= 0) {
    throw new Error("topUpParty: amountCC must be positive");
  }

  const transferId = `autobot-topup-${Date.now()}-${crypto.randomBytes(6).toString("hex")}`;
  const url = `${mcpServerUrl.replace(/\/$/, "")}/billing/credit`;

  let res;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Billing-API-Key": billingApiKey,
      },
      body: JSON.stringify({
        userParty: partyId,
        amount: amountCC,
        transferId,
        description: `autobot ${personaName || "top-up"}`,
      }),
    });
  } catch (err) {
    throw new Error(`TOPUP_FAILED (network): ${err.message}`);
  }

  if (!res.ok) {
    const body = (await res.text()).slice(0, 500);
    throw new Error(`TOPUP_FAILED (HTTP ${res.status}): ${body}`);
  }
  const data = await res.json();
  if (!data.success) {
    throw new Error(`TOPUP_FAILED: ${JSON.stringify(data).slice(0, 300)}`);
  }

  console.log(
    `[EVENT] ${iso()} autobot_topup partyId=${partyId.slice(0, 40)}... amount=${amountCC} persona=${personaName || "unknown"} balance=${data.balance} transferId=${transferId}`
  );
  return { contractId: data.contractId, balance: data.balance, amount: data.amount };
}

/**
 * Convenience: read a keyfile's partyId without loading key material.
 */
export function readPartyId(keyPath) {
  const data = JSON.parse(readFileSync(keyPath, "utf8"));
  return data.partyId;
}
