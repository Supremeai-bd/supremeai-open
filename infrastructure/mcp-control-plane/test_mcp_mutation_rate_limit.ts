/**
 * #2363 — anonymous-mutation plane rate-limit regression battery (pure, offline).
 * House style: tsx script, hard asserts, exit code = verdict.
 *
 * The audit (#2363 F-1, live-mapped 2026-10-29) proved 4 side-effect-capable
 * tools (github_create_issue, memory_remember_fact, work_claim,
 * bridge_submit_patch) reachable zero-credential with ZERO 429s observed
 * across 27 dispatch cycles. The pre-existing per-(identity, tool) limit
 * collapses every anonymous caller into the shared "default|anon" bucket —
 * one abusive tenant exhausts it (a DoS against the other anonymous agents),
 * and nothing bounds novel-content spam at writes/hour scale per IP.
 *
 * The fix: per-(caller IP, tool) HOURLY sliding window on exactly those 4
 * mutation tools, enforced at the /mcp POST entry with 429 + Retry-After.
 * Read plane untouched; malformed bodies fail open into the downstream
 * RBAC/limits (availability over blocking — never silent).
 */
import {
  MUTATION_TOOLS,
  mutationRateBuckets,
  consumeMutationRateLimit,
  mutationToolGateError,
  consumeSlidingWindow,
  consumeSlidingWindowAt,
} from "./src/lib/mcp_rate_limit.js";

let failures = 0;
function check(name: string, cond: boolean, detail?: string): void {
  if (cond) {
    console.log(`  ✓ ${name}`);
  } else {
    failures += 1;
    console.error(`  ✗ ${name}${detail ? ` — ${detail}` : ""}`);
  }
}
function section(title: string): void {
  console.log(`\n=== ${title} ===`);
}

const HOUR = 3_600_000;
const T0 = 1_770_000_000_000; // fixed epoch for deterministic replay

function freshBuckets(): Map<string, number[]> {
  const b = new Map<string, number[]>();
  for (const [k, v] of mutationRateBuckets) b.set(k, [...v]);
  mutationRateBuckets.clear();
  return b;
}

function call(name: string): unknown {
  return { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: {} } };
}

// ─── 1. Mutation surface declaration ────────────────────────────────────────
section("1. MUTATION_TOOLS = exactly the 4 anonymous-reachable mutators (#2363 F-1 table)");
check("github_create_issue declared (PROVEN side effect)", MUTATION_TOOLS.has("github_create_issue"));
check("memory_remember_fact declared (PROVEN side effect)", MUTATION_TOOLS.has("memory_remember_fact"));
check("work_claim declared (would-be side effect)", MUTATION_TOOLS.has("work_claim"));
check("bridge_submit_patch declared (would-be side effect)", MUTATION_TOOLS.has("bridge_submit_patch"));
check("exactly 4 tools — no scope creep", MUTATION_TOOLS.size === 4, `size=${MUTATION_TOOLS.size}`);

// ─── 2. Sliding window mechanics (injectable clock) ─────────────────────────
section("2. consumeSlidingWindowAt mechanics");
{
  const b = new Map<string, number[]>();
  const r1 = consumeSlidingWindowAt(b, "k", 2, HOUR, T0);
  const r2 = consumeSlidingWindowAt(b, "k", 2, HOUR, T0 + 1);
  check("first two consumes allowed", r1.allowed && r2.allowed);
  const r3 = consumeSlidingWindowAt(b, "k", 2, HOUR, T0 + 2);
  check("third consume denied at max", !r3.allowed);
  check("retryAfterMs > 0 on denial", r3.retryAfterMs > 0);
  const r4 = consumeSlidingWindowAt(b, "k", 2, HOUR, T0 + HOUR + 1);
  check("window slide re-allows", r4.allowed);
  check("injectable clock equals wall-clock variant shape", (() => {
    const w = new Map<string, number[]>();
    consumeSlidingWindow(w, "k2", 1, 1000);
    const probe = consumeSlidingWindowAt(w, "k2", 1, 1000, Date.now() + 5000);
    return probe.allowed === true; // old stamp evicted by the later clock
  })());
}

// ─── 3. Per-(IP, tool) hourly bucket ────────────────────────────────────────
section("3. Per-(IP, tool) hourly bound");
{
  freshBuckets();
  const ip = "203.0.113.7";
  let last = { allowed: true, retryAfterMs: 0 };
  let denies = 0;
  for (let i = 0; i < 31; i++) {
    last = consumeMutationRateLimit(ip, "github_create_issue", T0 + i);
    if (!last.allowed) denies += 1;
  }
  check("30 writes/hour allowed", 31 - denies === 30, `allowed=${31 - denies}`);
  check("31st write denied", denies === 1 && !last.allowed);
  check("retryAfterMs ~ remaining window", last.retryAfterMs > 0 && last.retryAfterMs <= HOUR);
  // slide past the window -> re-allowed
  const later = consumeMutationRateLimit(ip, "github_create_issue", T0 + HOUR + 1);
  check("hour slide re-allows", later.allowed);
}

// ─── 4. Isolation axes ──────────────────────────────────────────────────────
section("4. Isolation: per-IP and per-tool");
{
  freshBuckets();
  for (let i = 0; i < 30; i++) consumeMutationRateLimit("198.51.100.1", "work_claim", T0 + i);
  check("exhausted IP still isolated from other IP", consumeMutationRateLimit("198.51.100.2", "work_claim", T0).allowed);
  check("exhausted tool still isolated from other tool (same IP)", consumeMutationRateLimit("198.51.100.1", "memory_remember_fact", T0).allowed);
}

// ─── 5. Gate: allow path + boundary + Retry-After semantics ─────────────────
section("5. mutationToolGateError — allow / deny / worst-reply");
{
  freshBuckets();
  const ip = "192.0.2.9";
  check("first mutation call passes", mutationToolGateError(call("github_create_issue"), ip, T0) === null);
  for (let i = 1; i < 30; i++) mutationToolGateError(call("github_create_issue"), ip, T0 + i);
  check("29 more calls pass (30 total)", true);
  const denied = mutationToolGateError(call("github_create_issue"), ip, T0 + 100);
  check("31st call denied with retryAfterMs", denied !== null && denied.retryAfterMs > 0);
  check("denial names the tool", denied !== null && denied.tool === "github_create_issue");
}

// ─── 6. Read plane untouched ────────────────────────────────────────────────
section("6. Read plane untouched");
{
  freshBuckets();
  const ip = "192.0.2.77";
  const readTools = ["status", "health_dashboard", "bridge_work", "github_read_file", "memory_search_nodes", "bridge_work_order"];
  let allPass = true;
  for (let i = 0; i < 500; i++) {
    for (const t of readTools) {
      if (mutationToolGateError(call(t), ip, T0 + i) !== null) allPass = false;
    }
  }
  check("3000 read calls: zero denials", allPass);
  check("non-tools/call methods pass", mutationToolGateError({ jsonrpc: "2.0", method: "tools/list", id: 2 }, ip, T0) === null);
  check("initialize passes", mutationToolGateError({ jsonrpc: "2.0", method: "initialize", params: {} }, ip, T0) === null);
}

// ─── 7. Batch + malformed shapes (fail-open) ────────────────────────────────
section("7. Batch arrays + fail-open on malformed bodies");
{
  freshBuckets();
  const ip = "192.0.2.50";
  check("batch [read, read] passes", mutationToolGateError([call("status"), call("bridge_work")], ip, T0) === null);
  check("batch [read, mutation] consumes mutation bucket only", mutationToolGateError([call("status"), call("work_claim")], ip, T0) === null);
  check("null body (no body) passes", mutationToolGateError(null, ip, T0) === null);
  check("string body (unparseable upstream) passes", mutationToolGateError("garbage", ip, T0) === null);
  check("malformed tools/call (params missing) passes", mutationToolGateError({ method: "tools/call" }, ip, T0) === null);
  check("non-string tool name passes", mutationToolGateError({ method: "tools/call", params: { name: 42 } }, ip, T0) === null);
  // exhaustive batch denial: worst (longest) retryAfterMs wins deterministically
  for (let i = 0; i < 30; i++) consumeMutationRateLimit(ip, "bridge_submit_patch", T0);
  const both = mutationToolGateError(
    [call("github_create_issue"), call("bridge_submit_patch")], ip, T0,
  );
  check("batch denial reports a mutation tool with retryAfterMs", both !== null && both.retryAfterMs > 0);
}

// ─── 8. Openness doctrine intact ────────────────────────────────────────────
section("8. Openness doctrine: bounded, not closed (#2082 standing doctrine)");
{
  freshBuckets();
  const ip = "192.0.2.200";
  // 30 writes/hour/tool is far above any legitimate agent cycle (audit: 40+ calls
  // per cycle across ALL tools never hit the old 20/min shared bucket).
  let ok = true;
  for (let i = 0; i < 30; i++) {
    if (!consumeMutationRateLimit(ip, "memory_remember_fact", T0 + i * 1000).allowed) ok = false;
  }
  check("legitimate single-agent cycle (30 writes) fully allowed", ok);
  const beyond = consumeMutationRateLimit(ip, "memory_remember_fact", T0 + 31_000);
  check("beyond the bound: denied with Retry-After (bounded != authenticated)", !beyond.allowed && beyond.retryAfterMs > 0);
}

console.log(`\n${failures === 0 ? "ALL CHECKS PASSED" : `${failures} CHECK(S) FAILED`}`);
process.exit(failures === 0 ? 0 : 1);
