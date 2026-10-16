import assert from "node:assert/strict";
import { upstashRestUrl, mapConcurrentSettled } from "./src/tools/system.tools.js";

// ── 1. upstashRestUrl password token extraction test ──
const tcpUrlWithPassword = "rediss://default:superSecretToken99@us1-test-redis.upstash.io:6379";
const parsedTcp = upstashRestUrl(tcpUrlWithPassword);
assert.ok(parsedTcp, "parsedTcp must not be null");
assert.equal(parsedTcp.url, "https://us1-test-redis.upstash.io/ping");
assert.equal(parsedTcp.token, "superSecretToken99", "Token must be extracted from password, not username 'default'");

// ── 2. upstashRestUrl https REST URL test (auto-rotated accounts) ──
const restUrl = "https://us1-test-redis.upstash.io";
const parsedRest = upstashRestUrl(restUrl);
assert.ok(parsedRest, "parsedRest must not be null");
assert.equal(parsedRest.url, "https://us1-test-redis.upstash.io/ping");
assert.equal(parsedRest.token, undefined, "REST URL has no embedded token — caller falls back to apiKeyRef");

// ── 3. mapConcurrentSettled concurrency bound test ──
let activeConcurrent = 0;
let peakConcurrent = 0;
const totalTasks = 20;
const concurrencyLimit = 5;

const tasks = Array.from({ length: totalTasks }, (_, i) => i);
const results = await mapConcurrentSettled(tasks, concurrencyLimit, async (id) => {
  activeConcurrent++;
  if (activeConcurrent > peakConcurrent) {
    peakConcurrent = activeConcurrent;
  }
  // Simulate network latency
  await new Promise((resolve) => setTimeout(resolve, 20));
  activeConcurrent--;
  if (id === 13) throw new Error("task 13 simulated error");
  return `result-${id}`;
});

assert.equal(results.length, totalTasks, "Must return results for all tasks");
assert.ok(peakConcurrent <= concurrencyLimit, `Peak concurrency (${peakConcurrent}) must not exceed limit (${concurrencyLimit})`);

const fulfilled = results.filter((r) => r.status === "fulfilled");
const rejected = results.filter((r) => r.status === "rejected");
assert.equal(fulfilled.length, totalTasks - 1);
assert.equal(rejected.length, 1);

console.log("✅ test_system_health_probe: all assertions passed! Peak concurrency:", peakConcurrent);
