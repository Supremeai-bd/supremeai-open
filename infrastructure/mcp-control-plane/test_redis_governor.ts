import assert from "node:assert/strict";
import { RedisGovernor, RedisClient } from "./src/lib/redis-governor.js";

function makeMockClient(): RedisClient & { store: Map<string, string> } {
  const store = new Map<string, string>();
  return {
    store,
    get: async (key: string) => store.get(key) ?? null,
    set: async (key: string, value: string) => {
      store.set(key, value);
      return "OK";
    },
    del: async (key: string) => {
      store.delete(key);
      return 1;
    },
  };
}

async function runTests() {
  console.log("Running RedisGovernor tests...");

  // 1. Validation
  const client = makeMockClient();
  assert.throws(() => new RedisGovernor(client, { namespace: "", defaultTtlSeconds: 60 }));
  assert.throws(() => new RedisGovernor(client, { namespace: "test", defaultTtlSeconds: 0 }));

  // 2. Cache hit
  const governor = new RedisGovernor(client, { namespace: "test", defaultTtlSeconds: 60 });
  client.store.set("test:my-key", JSON.stringify({ ok: true }));

  let fetcherCalled = false;
  const res1 = await governor.getOrSet("my-key", async () => {
    fetcherCalled = true;
    return { ok: false };
  });
  assert.equal(res1.cacheHit, true);
  assert.deepEqual(res1.value, { ok: true });
  assert.equal(fetcherCalled, false);

  // 3. Cache miss & set
  const res2 = await governor.getOrSet("new-key", async () => ({ value: 42 }));
  assert.equal(res2.cacheHit, false);
  assert.deepEqual(res2.value, { value: 42 });
  assert.equal(client.store.get("test:new-key"), JSON.stringify({ value: 42 }));

  // 4. Degraded mode on client failure
  const failingClient: RedisClient = {
    get: async () => {
      throw new Error("redis offline");
    },
    set: async () => {
      throw new Error("redis offline");
    },
    del: async () => {
      throw new Error("redis offline");
    },
  };
  const degradedGovernor = new RedisGovernor(failingClient, {
    namespace: "degraded",
    defaultTtlSeconds: 60,
    maxRetries: 0,
    failureCooldownMs: 1000,
  });

  const res3 = await degradedGovernor.getOrSet("fail-key", async () => "fallback-value");
  assert.equal(res3.value, "fallback-value");
  assert.equal(res3.cacheHit, false);

  console.log("ALL RedisGovernor tests passed cleanly!");
}

runTests().catch((err) => {
  console.error("Test failed:", err);
  process.exit(1);
});
