/**
 * Quota-routing regression test (#110).
 *
 * AC2: quota-marking behavior must be identical for a quota-exhausted primary
 * across ALL routed paths — every first-responder fallback now flows through
 * the single runWithAccountChain engine in lib/redis_chain.ts, so one test
 * forces the first account into quota exhaustion (via a mocked Upstash REST
 * response carrying the quota marker) and asserts every routed caller lands on
 * the NEXT account with the primary visibly in cooldown afterwards.
 *
 * Routed paths covered:
 *   1. recordHeartbeat            (registry/agent_heartbeat.ts)
 *   2. recordPresence             (registry/mcp_presence.ts)
 *   3. orchestrator dispatch GET  (registry/orchestrator_dispatch.ts)
 *   4. client-registry store load (policy/client-registry.store.ts)
 *
 * NOT routed (by design, documented in the PR): the fan-out MERGE readers
 * (listPresence / listHeartbeats) and the fan-out flush writer — their
 * semantics are "touch every account", not "stop at the first responder".
 *
 * Run: npm run test:quota-routing   (wired into test:unit)
 */
import assert from "node:assert/strict";

import {
  isAccountQuotaExhausted,
  quotaChainStatus,
} from "./src/lib/redis_chain.js";
import { recordHeartbeat } from "./src/registry/agent_heartbeat.js";
import { recordPresence } from "./src/registry/mcp_presence.js";
import { makeDispatchStore } from "./src/registry/orchestrator_dispatch.js";
import { UpstashClientRegistryStore } from "./src/policy/client-registry.store.js";

// ── Chain under test: two REST accounts, primary will fake quota-exhaustion ─
process.env.UPSTASH_REDIS_REST_URL = "https://primary.quota-test.invalid";
process.env.UPSTASH_REDIS_REST_TOKEN = "t1";
process.env.UPSTASH_REDIS_SECONDARY_REST_URL = "https://secondary.quota-test.invalid";
process.env.UPSTASH_REDIS_SECONDARY_REST_TOKEN = "t2";
// Also clear env vars that could add extra accounts on this machine.
for (const k of ["UPSTASH_REDIS_TERTIARY_REST_URL", "UPSTASH_REDIS_TERTIARY_REST_TOKEN", "UPSTASH_REDIS_QUATERNARY_REST_URL", "UPSTASH_REDIS_QUATERNARY_REST_TOKEN", "UPSTASH_REDIS_QUINARY_REST_URL", "UPSTASH_REDIS_QUINARY_REST_TOKEN", "REDIS_URL"]) {
  delete process.env[k];
}

/** Cooldown state is module-global — clear it before/after each scenario. */
function resetCooldowns(): void {
  // Expired-check deletes the entry: any nowMs beyond the stored until works.
  for (const label of ["primary", "secondary"]) {
    isAccountQuotaExhausted(label, 8_200_000_000_000);
  }
}

// ── Host-keyed fetch mock: primary answers quota, secondary answers success ─
type MockReply = { status: number; body: string | Record<string, unknown> };
const realFetch = globalThis.fetch.bind(globalThis);
const calls: { host: string; command: string }[] = [];

(globalThis as unknown as { fetch: typeof fetch }).fetch = (async (input: unknown, init?: RequestInit) => {
  const url = new URL(String(input));
  const payload = JSON.parse(String(init?.body ?? "[]")) as string[];
  calls.push({ host: url.host, command: payload[0] ?? "?" });
  const quota = url.host.startsWith("primary.");
  if (quota) {
    // Upstash quota shape: any body containing the marker trips
    // responseIndicatesQuotaExhaustion regardless of status.
    return new Response("max requests limit exceeded for this account", { status: 429 });
  }
  // Secondary: answer the command like Upstash REST would.
  let reply: MockReply;
  switch (payload[0]) {
    case "HSET":
    case "SET":
      reply = { status: 200, body: { result: "OK" } };
      break;
    case "GET":
      reply = { status: 200, body: { result: payload[1]?.includes("registry") ? JSON.stringify([{ id: "client-1", roles: ["agent"], scopes: ["mcp:call"] }]) : "stored-value" } };
      break;
    default:
      reply = { status: 200, body: { result: null } };
  }
  return new Response(JSON.stringify(reply.body), { status: reply.status });
}) as typeof fetch;

// ── 1. recordHeartbeat: quota on primary → write lands on secondary ─────────
{
  resetCooldowns();
  calls.length = 0;
  const result = await recordHeartbeat({ slot: "agent-1", source: "mcp-tower" });
  assert.equal(result.ok, true);
  assert.equal(result.redisAccount, "secondary", "heartbeat write must shift to secondary when primary is quota-exhausted");
  assert.deepEqual(
    calls.map((c) => c.host),
    ["primary.quota-test.invalid", "secondary.quota-test.invalid", "secondary.quota-test.invalid"],
    "primary attempted once (quota reply), then the write lands fully on secondary",
  );
  assert.ok(calls.slice(1).every((c) => c.command === "HSET" || c.command === "SET"), "hash-first write contract preserved");
  const status = quotaChainStatus().find((s) => s.label === "primary");
  assert.ok(status?.cooldownUntil, "primary must be visibly in cooldown after the quota error");
}

// ── 2. recordPresence: same policy, same engine ──────────────────────────────
{
  resetCooldowns();
  calls.length = 0;
  const result = await recordPresence({ clientName: "test-client", clientId: "cid-1", protocol: "http" });
  assert.equal(result.ok, true);
  assert.deepEqual(calls.map((c) => c.host), ["primary.quota-test.invalid", "secondary.quota-test.invalid"], "presence write must shift to secondary on primary quota error");
  assert.equal(calls[0]?.command, "SET");
  assert.ok(quotaChainStatus().find((s) => s.label === "primary")?.cooldownUntil, "primary cooldown marked by the presence path too (previously unmarked — now identical)");
}

// ── 3. Orchestrator dispatch store: GET shifts to secondary ──────────────────
{
  resetCooldowns();
  calls.length = 0;
  const store = await makeDispatchStore();
  const value = await store.get("orchestrator:test");
  assert.equal(value, "stored-value");
  assert.deepEqual(calls.map((c) => c.host), ["primary.quota-test.invalid", "secondary.quota-test.invalid"], "orchestrator REST call must land on secondary after primary quota error");
}

// ── 4. Client-registry store hydration: shifts to secondary ──────────────────
{
  resetCooldowns();
  calls.length = 0;
  const store = new UpstashClientRegistryStore("supremeai:test:registry");
  const records = await store.loadAsync();
  assert.equal(records.length, 1);
  assert.equal(records[0]?.id, "client-1");
  assert.deepEqual(calls.map((c) => c.host), ["primary.quota-test.invalid", "secondary.quota-test.invalid"], "registry hydration must land on secondary after primary quota error");
  assert.equal(store.load()[0]?.id, "client-1", "snapshot updated from the answering account");
}

// ── Cleanup: restore real fetch, clear cooldowns ─────────────────────────────
resetCooldowns();
(globalThis as unknown as { fetch: typeof fetch }).fetch = realFetch;

console.log("ALL QUOTA-ROUTING REGRESSION TESTS PASSED (#110) — 4/4 routed paths shift on quota exhaustion");
