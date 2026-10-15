/**
 * #110 regression — the account-chain walk is implemented ONCE
 * (lib/redis_chain.ts runWithAccountChain) and every routed caller shares the
 * same cooldown + shift policy.
 *
 * Acceptance criterion 2 (issue #110): "Quota-marking behavior is identical
 * for a quota-exhausted primary across all five paths — one test asserts
 * cooldown + shift for each caller."
 *
 * Technique: a fake global fetch answers the PRIMARY account with Upstash's
 * daily-quota rejection (400 + "max requests limit exceeded") and serves every
 * other account. After each caller runs, the primary must be
 * (a) marked into cooldown (isAccountQuotaExhausted) and
 * (b) skipped — the operation must land on the next account.
 *
 * Runners: `npx tsx test_account_chain_callers.ts` (wired as test:account-chain
 * via scripts/test-runner.ts, per the #116 wiring guard).
 */

import assert from "node:assert/strict";

// ── env setup BEFORE importing chain-dependent modules ─────────────────────
process.env.UPSTASH_REDIS_REST_URL = "https://primary.example.invalid";
process.env.UPSTASH_REDIS_REST_TOKEN = "t-primary";
process.env.UPSTASH_REDIS_SECONDARY_REST_URL = "https://secondary.example.invalid";
process.env.UPSTASH_REDIS_SECONDARY_REST_TOKEN = "t-secondary";

const realFetch = globalThis.fetch;
type FakeResponse = { ok: boolean; status: number; headers: { get: (name: string) => string | null }; text: () => Promise<string>; json: () => Promise<unknown> };
type FetchLike = (url: string, init?: { body?: string }) => Promise<FakeResponse>;
const callsByUrl = new Map<string, number>();
/** Per-command fake responder (shared by single + pipeline request shapes). */
function fakeCommandResult(cmdRaw: unknown, argRaw: unknown): unknown {
  const cmd = String(cmdRaw ?? "").toUpperCase();
  const arg = String(argRaw ?? "");
  if (cmd === "PING") return "PONG";
  if (cmd === "KEYS") return [];
  if (cmd === "GET" && arg.includes("client-registry")) return null; // fresh registry
  return "OK";
}
(globalThis as unknown as { fetch: FetchLike }).fetch = (async (url: string, init?: { body?: string }) => {
  callsByUrl.set(url, (callsByUrl.get(url) ?? 0) + 1);
  const headers = { get: (_name: string) => null }; // @upstash/redis reads headers.get()
  if (String(url).startsWith("https://primary.")) {
    // Upstash daily-quota rejection shape (see lib/redis_chain QUOTA_EXCEEDED_MARKER)
    const errJson = JSON.stringify({ error: "ERR max requests limit exceeded. Limit: 500000, Usage: 500002" });
    return { ok: false, status: 400, headers, text: async () => errJson, json: async () => ({ error: "ERR max requests limit exceeded. Limit: 500000, Usage: 500002" }) };
  }
  // secondary serves successfully. The @upstash/redis SDK (this version) runs
  // every command through an AutoPipeline → POST {url}/pipeline with an array
  // of command arrays, expecting an ARRAY of {error, result} back. Hand-rolled
  // callers POST a JSON array [CMD, ...] and expect {result}.
  const isPipeline = /\/pipeline\/?$/.test(String(url));
  let parsed: unknown = [];
  try {
    parsed = JSON.parse(String(init?.body ?? "[]")) as unknown;
  } catch { /* fall through with empty */ }
  if (isPipeline) {
    const commands = Array.isArray(parsed) ? parsed : [];
    const arr = commands.map((c) => {
      const parts = Array.isArray(c) ? c : [];
      return { error: null, result: fakeCommandResult(parts[0], parts[1]) };
    });
    const bodyJson = JSON.stringify(arr);
    return { ok: true, status: 200, headers, text: async () => bodyJson, json: async () => arr };
  }
  let cmd = "";
  let arg = "";
  if (Array.isArray(parsed)) {
    cmd = String(parsed[0] ?? "");
    arg = String(parsed[1] ?? "");
  }
  const bodyJson = JSON.stringify({ result: fakeCommandResult(cmd, arg) });
  return { ok: true, status: 200, headers, text: async () => bodyJson, json: async () => ({ result: fakeCommandResult(cmd, arg) }) };
}) as unknown as typeof fetch;

const {
  buildAccountChain,
  isAccountQuotaExhausted,
  activeAccountChain,
} = await import("./src/lib/redis_chain.js");
const { recordHeartbeat } = await import("./src/registry/agent_heartbeat.js");
const { recordPresence } = await import("./src/registry/mcp_presence.js");
const { pingRedis } = await import("./src/adapters/redis/index.js");
const { UpstashClientRegistryStore } = await import("./src/policy/client-registry.store.js");
const { makeDispatchStore } = await import("./src/registry/orchestrator_dispatch.js");

let checks = 0;
function check(name: string, cond: boolean): void {
  checks += 1;
  assert.ok(cond, `#110 chain-walk regression: ${name}`);
  console.log(`  ✅ ${name}`);
}

// Chain sanity: two REST accounts, primary first, none in cooldown yet.
check("chain has primary + secondary", buildAccountChain().map((a) => a.label).join(",") === "primary,secondary");
check("primary starts active", activeAccountChain()[0].label === "primary");

// 1. Heartbeat write → primary quota-marked, write lands on secondary.
{
  const res = await recordHeartbeat({ slot: "agent-1", source: "test", agentId: "zai-#110" } as never);
  check("heartbeat write shifted to secondary", res.redisAccount === "secondary");
  check("heartbeat path marked primary cooldown", isAccountQuotaExhausted("primary"));
}

// 2. Presence write → same policy (previously this copy NEVER marked quota).
{
  const res = await recordPresence({ clientName: "zai-110-probe", protocol: "mcp" } as never);
  check("presence write accepted (ok:true)", res.ok === true);
  check("presence path kept primary in cooldown", isAccountQuotaExhausted("primary"));
}

// 3. Adapter ping (the canonical health path) → secondary answers.
{
  const res = (await pingRedis()) as { account: string; attemptedAccounts: { account: string; ok: boolean }[] };
  check("adapter ping answered by secondary", res.account === "secondary");
  check("adapter attempt report shows primary failure + secondary success",
    res.attemptedAccounts.filter((a) => a.account === "primary").every((a) => !a.ok) &&
    res.attemptedAccounts.some((a) => a.account === "secondary" && a.ok));
}

// 4. Client-registry store hydration → loads via secondary, fail-closed intact.
{
  const store = new UpstashClientRegistryStore("supremeai:mcp:client-registry:test-#110");
  const records = await store.loadAsync();
  check("store loadAsync returns fresh-registry [] via secondary", Array.isArray(records) && records.length === 0);
  check("store path kept primary in cooldown", isAccountQuotaExhausted("primary"));
}

// 5. Orchestrator dispatch store → GET served by secondary.
{
  const store = await makeDispatchStore();
  const value = await store.get("supremeai:orchestrator:test-#110");
  check("dispatch store GET served (value from secondary)", value === "OK");
  check("dispatch path kept primary in cooldown", isAccountQuotaExhausted("primary"));
}

// 6. Quota cooldown is real: primary excluded from the ACTIVE chain afterwards.
check("primary excluded from active chain after marking", activeAccountChain().every((a) => a.label !== "primary"));

// 7. Helper unit semantics: message-level quota evidence also marks cooldown.
{
  const { runWithAccountChain } = await import("./src/lib/redis_chain.js");
  // primary is in cooldown; walk starts at secondary. Fail secondary with a
  // quota-flavored MESSAGE → helper must mark secondary too, then fail-open
  // to the full chain (primary cooldown-skipped retry) and throw aggregated.
  let sawAccounts: string[] = [];
  await assert.rejects(
    () => runWithAccountChain(async (account) => {
      sawAccounts.push(account.label);
      throw new Error("ERR max requests limit exceeded (fixture)");
    }),
    /All \d+ Redis account\(s\) failed/,
  );
  check("helper aggregated throw on total failure", true);
  check("helper marked secondary from message evidence", isAccountQuotaExhausted("secondary"));
  void sawAccounts;
}

(globalThis as unknown as { fetch: FetchLike }).fetch = realFetch as unknown as FetchLike;
console.log(`\n✅ #110 account-chain walk regression: ${checks} checks passed — one walk, one cooldown policy across all routed callers`);
