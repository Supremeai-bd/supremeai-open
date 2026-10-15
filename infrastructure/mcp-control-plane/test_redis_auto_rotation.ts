import assert from "node:assert/strict";
import {
  buildAccountChain,
  activeAccountChain,
  getActiveRedisAccount,
  markAccountQuotaExhausted,
  isAccountQuotaExhausted,
  clearAllQuotaCooldowns,
  quotaChainStatus,
  nextQuotaResetEpochMs,
  responseIndicatesQuotaExhaustion,
} from "./src/lib/redis_chain.js";
import {
  runWithAccountChain,
  readAcrossAccountChain,
  pingRedis,
} from "./src/adapters/redis/index.js";
import { recordHeartbeat } from "./src/registry/agent_heartbeat.js";
import { recordPresence } from "./src/registry/mcp_presence.js";
import { makeDispatchStore } from "./src/registry/orchestrator_dispatch.js";
import { UpstashClientRegistryStore } from "./src/policy/client-registry.store.js";

// Setup environment with 3 accounts
process.env.UPSTASH_REDIS_REST_URL = "https://primary.upstash.io";
process.env.UPSTASH_REDIS_REST_TOKEN = "t1";
process.env.UPSTASH_REDIS_SECONDARY_REST_URL = "https://secondary.upstash.io";
process.env.UPSTASH_REDIS_SECONDARY_REST_TOKEN = "t2";
process.env.UPSTASH_REDIS_TERTIARY_REST_URL = "https://tertiary.upstash.io";
process.env.UPSTASH_REDIS_TERTIARY_REST_TOKEN = "t3";

// 1. Initial State: primary is active
assert.equal(getActiveRedisAccount().label, "primary");
assert.equal(activeAccountChain().length, 3);
assert.equal(activeAccountChain()[0].label, "primary");

// 2. Quota exhaustion marker detection
assert.ok(responseIndicatesQuotaExhaustion(400, "ERR max requests limit exceeded. Limit: 500000, Usage: 500002"));
assert.ok(responseIndicatesQuotaExhaustion(400, "command failed: max requests limit"));
assert.ok(!responseIndicatesQuotaExhaustion(200, "PONG"));

// 3. Mark primary exhausted -> Auto-rotate to secondary
markAccountQuotaExhausted("primary");
assert.ok(isAccountQuotaExhausted("primary"));
assert.equal(getActiveRedisAccount().label, "secondary", "Active primary must auto-rotate to secondary");
assert.equal(activeAccountChain()[0].label, "secondary");
assert.equal(activeAccountChain().length, 2);

// 4. Quota chain status reflection
const status = quotaChainStatus();
const primaryStatus = status.find((s) => s.label === "primary");
const secondaryStatus = status.find((s) => s.label === "secondary");
assert.ok(primaryStatus?.cooldownUntil !== null, "Primary must have cooldownUntil timestamp");
assert.equal(primaryStatus?.isActivePrimary, false);
assert.equal(secondaryStatus?.isActivePrimary, true, "Secondary must be active primary");

// 5. If secondary also exhausts -> Auto-rotate to tertiary
markAccountQuotaExhausted("secondary");
assert.equal(getActiveRedisAccount().label, "tertiary", "Active primary must auto-rotate to tertiary");
assert.equal(activeAccountChain()[0].label, "tertiary");
assert.equal(activeAccountChain().length, 1);

// 6. Reset epoch verification: 1st of next month
const resetMs = nextQuotaResetEpochMs();
const resetDate = new Date(resetMs);
assert.equal(resetDate.getUTCDate(), 1, "Reset day must be 1st of month");
assert.equal(resetDate.getUTCHours(), 0, "Reset hour must be 00:00 UTC");

// ── 7. #110 SSOT regression: every routed path rotates off a quota-dead primary ──
// Forces the FIRST account into quota exhaustion (HTTP 400 + "max requests
// limit" body) and asserts every consolidated call site — shared walk, health
// adapter, heartbeat write, presence write, orchestrator state, client-registry
// hydration, merge-read — lands on the NEXT account with ONE cooldown marking.
clearAllQuotaCooldowns();
const realFetch = globalThis.fetch;
const restCalls: Array<{ url: string; command: string }> = [];
globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = String(input);
  const body = JSON.parse(String(init?.body ?? "[]")) as unknown[];
  const command = String(body[0]);
  restCalls.push({ url, command });
  if (url.includes("primary.upstash.io")) {
    return new Response("ERR max requests limit exceeded. Limit: 500000, Usage: 500002", {
      status: 400,
      headers: { "Content-Type": "text/plain" },
    });
  }
  let result: unknown = "OK";
  if (command === "GET") result = null;
  else if (command === "PING") result = "PONG";
  else if (command === "HGETALL") result = {};
  else if (command === "KEYS") result = [];
  return new Response(JSON.stringify({ result }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}) as typeof fetch;

try {
  // (a) THE shared first-responder walk: primary quota-dead → secondary answers
  const run = await runWithAccountChain((c) => c.ping());
  assert.equal(run.client.account, "secondary", "shared walk must land on the next account");
  assert.equal(run.attempts[0].account, "primary");
  assert.equal(run.attempts[0].ok, false);
  assert.ok(
    isAccountQuotaExhausted("primary"),
    "canonical quota-marking must put the dead primary into cooldown",
  );
  assert.ok(
    !restCalls.some((c) => c.url.includes("tertiary")),
    "rotation stops at the first healthy account — no wasted tertiary requests",
  );

  // (b) health adapter (pingRedis) routes through the same walk — and the
  // cooldown policy means NO wasted request is sent to the exhausted primary.
  const ping = (await pingRedis()) as { account: string; attemptedAccounts: Array<{ account: string; ok: boolean }> };
  assert.equal(ping.account, "secondary");
  assert.ok(
    !ping.attemptedAccounts.some((a) => a.account === "primary"),
    "cooldown policy: exhausted primary must be skipped without a wasted request",
  );

  // (c) heartbeat write lands on secondary
  const hb = await recordHeartbeat({ slot: "agent-4", source: "mcp-tower" });
  assert.equal(hb.redisAccount, "secondary", "heartbeat write must rotate to secondary");

  // (d) presence write lands on secondary
  const presence = await recordPresence({
    clientName: "ChatGPT",
    clientId: "c110-regression",
    protocol: "streamable-http",
  });
  assert.equal(presence.ok, true);
  assert.ok(
    restCalls.some((c) => c.url.includes("secondary") && c.command === "SET"),
    "presence write must reach the secondary account",
  );

  // (e) orchestrator dispatch state routes through the same walk
  const dispatchStore = await makeDispatchStore();
  assert.equal(await dispatchStore.get("supremeai:orchestrate:#110-regression"), null);

  // (f) client-registry hydration: secondary reachable + fresh → [] (NOT fail-closed)
  const registry = new UpstashClientRegistryStore("supremeai:test:#110-regression");
  assert.deepEqual(await registry.loadAsync(), []);

  // (g) merge-read helper reports per-account outcomes across ALL active
  // accounts (fresh cooldowns → primary fail, secondary + tertiary merge-ok).
  clearAllQuotaCooldowns();
  const read = await readAcrossAccountChain((c) => c.get("x"));
  assert.equal(read.entries.length, 3, "merge-read touches every active account");
  assert.equal(read.entries[0].account, "primary");
  assert.equal(read.entries[0].ok, false);
  assert.equal(read.entries[1].account, "secondary");
  assert.equal(read.entries[1].ok, true);

  // (h) fail-loud preserved: unconfigured chain still throws the honest error
  const savedUrl = process.env.UPSTASH_REDIS_REST_URL;
  const savedToken = process.env.UPSTASH_REDIS_REST_TOKEN;
  const savedSecondaryUrl = process.env.UPSTASH_REDIS_SECONDARY_REST_URL;
  const savedSecondaryToken = process.env.UPSTASH_REDIS_SECONDARY_REST_TOKEN;
  const savedTertiaryUrl = process.env.UPSTASH_REDIS_TERTIARY_REST_URL;
  const savedTertiaryToken = process.env.UPSTASH_REDIS_TERTIARY_REST_TOKEN;
  delete process.env.UPSTASH_REDIS_REST_URL;
  delete process.env.UPSTASH_REDIS_REST_TOKEN;
  delete process.env.UPSTASH_REDIS_SECONDARY_REST_URL;
  delete process.env.UPSTASH_REDIS_SECONDARY_REST_TOKEN;
  delete process.env.UPSTASH_REDIS_TERTIARY_REST_URL;
  delete process.env.UPSTASH_REDIS_TERTIARY_REST_TOKEN;
  try {
    let unconfiguredErr: unknown;
    try {
      await runWithAccountChain((c) => c.ping());
    } catch (err) {
      unconfiguredErr = err;
    }
    assert.ok(unconfiguredErr instanceof Error);
    assert.match((unconfiguredErr as Error).message, /No Redis configuration found/);
  } finally {
    process.env.UPSTASH_REDIS_REST_URL = savedUrl;
    process.env.UPSTASH_REDIS_REST_TOKEN = savedToken;
    process.env.UPSTASH_REDIS_SECONDARY_REST_URL = savedSecondaryUrl;
    process.env.UPSTASH_REDIS_SECONDARY_REST_TOKEN = savedSecondaryToken;
    process.env.UPSTASH_REDIS_TERTIARY_REST_URL = savedTertiaryUrl;
    process.env.UPSTASH_REDIS_TERTIARY_REST_TOKEN = savedTertiaryToken;
  }

  console.log("✅ #110 SSOT regression: every routed path rotates off the quota-dead primary");
} finally {
  globalThis.fetch = realFetch;
  clearAllQuotaCooldowns();
}

console.log("✅ All Redis auto-rotation contract tests PASSED!");
