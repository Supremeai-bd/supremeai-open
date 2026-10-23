/**
 * Timeout / retry contract tests for the shared HTTP client
 * (defect-class guard: one AbortController per ATTEMPT).
 *
 * Background: httpRequest() previously created a single AbortController
 * before the retry loop, so a timeout on attempt N permanently aborted the
 * shared signal and every later retry failed instantly with AbortError —
 * retries were dead code for the most common retry cause (cold-start
 * spin-up of sleeping Render backends). These tests stub globalThis.fetch
 * to prove the retry contract offline; no network access, no credentials.
 *
 * House style: node:assert + plain script; restores globalThis.fetch in a
 * finally block so a failing assertion can never poison sibling suites.
 * Run: tsx scripts/test-runner.ts test_http_retry.ts
 */

import assert from "node:assert/strict";
import { httpRequest } from "./src/lib/http.js";

type FetchStub = (url: unknown, init?: { signal?: AbortSignal }) => Promise<unknown>;

async function withStubbedFetch(stub: FetchStub, fn: () => Promise<void>): Promise<void> {
  const real = globalThis.fetch;
  (globalThis as unknown as { fetch: unknown }).fetch = stub;
  try {
    await fn();
  } finally {
    (globalThis as unknown as { fetch: unknown }).fetch = real;
  }
}

/** A fetch that never resolves unless its signal aborts (timeout case). */
function hangUntilAborted(signal?: AbortSignal): Promise<never> {
  return new Promise((_, reject) => {
    signal?.addEventListener("abort", () => {
      const err = new Error("This operation was aborted");
      (err as unknown as { name: string }).name = "AbortError";
      reject(err);
    });
  });
}

const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });

let passed = 0;

// 1. THE defect: attempt-0 times out, retry attempt must run with a FRESH
//    (non-aborted) signal and succeed.
{
  const calls: boolean[] = [];
  await withStubbedFetch(async (_url, init) => {
    calls.push(init?.signal?.aborted ?? false);
    if (calls.length === 1) return hangUntilAborted(init?.signal);
    return jsonResponse({ ok: true });
  }, async () => {
    const res = await httpRequest("https://example.test/api", { method: "GET", timeoutMs: 120, retries: 2 });
    assert.equal(res.ok, true, "retry after timeout must eventually succeed");
    assert.ok(calls.length >= 2, `expected >=2 fetch attempts, got ${calls.length}`);
    assert.equal(calls[1], false, "retry attempt inherited an ALREADY-ABORTED signal (defect regression)");
  });
  passed++;
  console.log("✔ retry after timeout runs with a fresh signal");
}

// 2. Per-attempt timeout still enforced: every attempt hangs → throws after
//    attempts + backoff, not instantly.
{
  let elapsed = 0;
  await withStubbedFetch(async (_url, init) => hangUntilAborted(init?.signal), async () => {
    const t0 = Date.now();
    await assert.rejects(
      () => httpRequest("https://example.test/slow", { method: "GET", timeoutMs: 100, retries: 1 }),
      undefined,
      "exhausted timeouts must throw"
    );
    elapsed = Date.now() - t0;
  });
  // 2 timeouts (2x100ms) + backoff (500ms) — floor proves sequential budgets.
  assert.ok(elapsed >= 690, `retries exhausted too fast (${elapsed}ms) — per-attempt timeout not enforced`);
  assert.ok(elapsed < 5000, `exhaustion took too long (${elapsed}ms)`);
  passed++;
  console.log(`✔ per-attempt timeout enforced (${elapsed}ms total)`);
}

// 3. First-attempt success: exactly one call, JSON parsed.
{
  const calls: boolean[] = [];
  await withStubbedFetch(async () => {
    calls.push(true);
    return jsonResponse({ hello: "world" });
  }, async () => {
    const res = await httpRequest("https://example.test/good", { method: "GET", timeoutMs: 1000, retries: 2 });
    assert.equal(res.ok, true);
    assert.deepEqual(res.data, { hello: "world" });
    assert.equal(calls.length, 1, "successful first attempt must not retry");
  });
  passed++;
  console.log("✔ first-attempt success parses JSON without retry");
}

// 4. Non-2xx: returns ok:false WITHOUT throwing and WITHOUT retrying.
{
  const calls: boolean[] = [];
  await withStubbedFetch(async () => {
    calls.push(true);
    return jsonResponse({ error: "nope" }, 500);
  }, async () => {
    const res = await httpRequest("https://example.test/boom", { method: "GET", timeoutMs: 1000, retries: 2 });
    assert.equal(res.ok, false);
    assert.equal(res.status, 500);
    assert.equal(calls.length, 1, "HTTP error status must not trigger a network retry");
  });
  passed++;
  console.log("✔ non-2xx returns ok:false without retry");
}

// 5. Non-JSON content type: raw text passthrough.
{
  await withStubbedFetch(async () =>
    new Response("pong", { status: 200, headers: { "content-type": "text/plain" } })
  , async () => {
    const res = await httpRequest<string>("https://example.test/ping", { method: "GET", timeoutMs: 1000, retries: 0 });
    assert.equal(res.data, "pong");
  });
  passed++;
  console.log("✔ non-JSON response falls back to text");
}

// 6. Exhausted network errors: throws the LAST error after all attempts
//    (retries:1 → 2 calls + one 500ms backoff).
{
  const calls: number[] = [];
  let elapsed = 0;
  await withStubbedFetch(async () => {
    calls.push(1);
    throw new Error("boom");
  }, async () => {
    const t0 = Date.now();
    await assert.rejects(
      () => httpRequest("https://example.test/flaky", { method: "GET", timeoutMs: 1000, retries: 1 }),
      /boom/,
      "last network error must surface after exhaustion"
    );
    elapsed = Date.now() - t0;
  });
  assert.equal(calls.length, 2, `expected exactly 2 attempts, got ${calls.length}`);
  assert.ok(elapsed >= 490, `backoff schedule not honored (${elapsed}ms)`);
  passed++;
  console.log(`✔ exhausted retries throw last error after backoff (${elapsed}ms)`);
}

console.log(`http retry/timeout contract tests passed (${passed} cases)`);
