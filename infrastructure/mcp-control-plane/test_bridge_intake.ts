/**
 * #69 — Bridge intake test suite (signature, filtering, idempotency,
 * durable outbox, retry/backoff, rate limiting, replay, latency).
 * House style: tsx script, hard asserts, exit code = verdict.
 */
import { mkdtempSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHmac } from "node:crypto";

import { hasWebhookSignature } from "./src/lib/webhook_signature.js";
import { BridgeIntakeService, type BridgeIntakeConfig, type DispatchFn, type OutboxEntry } from "./src/events/bridge_intake.js";
import { globalEventNormalizer } from "./src/events/normalizer.js";

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

function baseConfig(overrides: Partial<BridgeIntakeConfig> = {}): BridgeIntakeConfig {
  return {
    enabled: true,
    repo: "Supremeai-bd/supremeai-open",
    workflow: "pipeline.yml",
    ref: "main",
    minIntervalMs: 0,
    maxAttempts: 3,
    outboxPath: join(mkdtempSync(join(tmpdir(), "intake-")), "outbox.jsonl"),
    token: "test-token",
    ...overrides,
  };
}

function issueEvent(action: string, overrides: Record<string, any> = {}): any {
  return {
    source: "github",
    type: "issues",
    severity: "WARNING",
    message: "test",
    timestamp: new Date().toISOString(),
    payload: {
      action,
      repository: { full_name: "Supremeai-bd/supremeai-open" },
      sender: { login: "somehuman" },
      issue: { number: 77, title: "bridge work order" },
      ...overrides,
    },
  } as any;
}

async function drain(): Promise<void> {
  await new Promise((r) => setTimeout(r, 20));
}

// ─── 1. Signature verification (lib) ─────────────────────────────────────────
section("1. Webhook signature verification (fail-closed, raw-body HMAC)");
const SECRET = "whsec_test_123";
const RAW_BODY = JSON.stringify({ action: "opened", number: 1 });
const VALID = `sha256=${createHmac("sha256", SECRET).update(RAW_BODY).digest("hex")}`;

check("valid signature accepted", hasWebhookSignature(VALID, RAW_BODY, SECRET));
check("tampered body rejected (raw-byte sensitivity)", !hasWebhookSignature(VALID, RAW_BODY + " ", SECRET));
check("tampered signature rejected", !hasWebhookSignature(VALID.slice(0, -2) + "ff", RAW_BODY, SECRET));
check("missing secret fail-closed", !hasWebhookSignature(VALID, RAW_BODY, ""));
check("missing header fail-closed", !hasWebhookSignature(undefined, RAW_BODY, SECRET));
check("malformed prefix rejected", !hasWebhookSignature(`md5=${VALID.slice(7)}`, RAW_BODY, SECRET));

// ─── 2. Relevance policy ─────────────────────────────────────────────────────
section("2. Event relevance policy (accept relevant, drop the rest)");
const svc2 = new BridgeIntakeService(baseConfig());
const d = (e: any) => svc2.decide(e);
check("issues.opened accepted", d(issueEvent("opened")).accept);
check("issues.labeled accepted", d(issueEvent("labeled")).accept);
check("issues.closed dropped", !d(issueEvent("closed")).accept);
check("pr.synchronize accepted", d({ ...issueEvent("opened"), type: "pull_request", payload: { action: "synchronize", repository: { full_name: "Supremeai-bd/supremeai-open" }, sender: { login: "dev" }, pull_request: { number: 9 } } }).accept);
check("pr.closed dropped", !d({ ...issueEvent("opened"), type: "pull_request", payload: { action: "closed", repository: { full_name: "Supremeai-bd/supremeai-open" }, sender: { login: "dev" } } }).accept);
check("comment.created accepted", d({ ...issueEvent("opened"), type: "issue_comment", payload: { action: "created", repository: { full_name: "Supremeai-bd/supremeai-open" }, sender: { login: "dev" }, issue: { number: 5 } } }).accept);
check("push dropped", !d({ ...issueEvent("opened"), type: "push" }).accept);
check("wrong repo dropped", !d(issueEvent("opened", { repository: { full_name: "evil/repo" } })).accept);
check("missing repo dropped", !d(issueEvent("opened", { repository: undefined })).accept);
check("bot sender dropped", !d(issueEvent("opened", { sender: { login: "dependabot[bot]" } })).accept);
check("non-github source dropped", !d({ ...issueEvent("opened"), source: "cloudflare" }).accept);

const disabledSvc = new BridgeIntakeService(baseConfig({ enabled: false }), { dispatch: async () => ({ ok: true, status: 204 }), log: () => {} });
disabledSvc.handle(issueEvent("opened") as any);
check("disabled service is inert (fail-closed)", disabledSvc.getStatus().pending === 0 && disabledSvc.getStatus().done === 0);

// ─── 3. Idempotency ──────────────────────────────────────────────────────────
section("3. Idempotency (delivery id + event key, TTL window)");
let clock = 1_000_000;
const dispatched3: any[] = [];
const dispatchOk3: DispatchFn = async (req) => { dispatched3.push(req); return { ok: true, status: 204 }; };
const svc3 = new BridgeIntakeService(baseConfig(), { now: () => clock, dispatch: dispatchOk3, log: () => {} });

svc3.handle({ ...issueEvent("opened"), deliveryId: "delivery-A" } as any);
svc3.handle({ ...issueEvent("opened"), deliveryId: "delivery-A" } as any); // same delivery redelivered
await drain();
check("same delivery id → exactly one dispatch", dispatched3.length === 1, `got ${dispatched3.length}`);

clock += 5 * 60 * 1000; // still inside 30-min TTL
svc3.handle({ ...issueEvent("opened"), deliveryId: "delivery-B" } as any); // different delivery, same event key
await drain();
check("same event key inside TTL → deduped", dispatched3.length === 1, `got ${dispatched3.length}`);

clock += 31 * 60 * 1000; // TTL expired
svc3.handle({ ...issueEvent("opened"), deliveryId: "delivery-C" } as any);
await drain();
check("same event key after TTL → processed again", dispatched3.length === 2, `got ${dispatched3.length}`);

// ─── 4. Fast ack + async dispatch ────────────────────────────────────────────
section("4. Acknowledgement never waits on dispatch (sync accept, async work)");
let releaseDispatch: () => void = () => {};
let slowDispatchCalls = 0;
const slowDispatch: DispatchFn = async () => {
  slowDispatchCalls += 1;
  await new Promise<void>((r) => { releaseDispatch = r; });
  return { ok: true, status: 204 };
};
const svc4 = new BridgeIntakeService(baseConfig(), { dispatch: slowDispatch, log: () => {} });
svc4.handle(issueEvent("opened") as any);
await drain();
check("handle() returned before dispatch resolved (outbox has pending entry)", slowDispatchCalls === 1 && svc4.getStatus().pending === 1);
releaseDispatch();
await drain();
check("dispatch completes after release", svc4.getStatus().done === 1);

// ─── 5. Retry / backoff / dead-letter ────────────────────────────────────────
section("5. Dispatch failure → bounded retry → dead-letter (observable)");
const dispatchFail: DispatchFn = async () => ({ ok: false, status: 500 });
clock = 5_000_000;
const logLines: string[] = [];
const svc5 = new BridgeIntakeService(baseConfig({ maxAttempts: 3 }), { now: () => clock, dispatch: dispatchFail, log: (l) => logLines.push(l) });
svc5.handle(issueEvent("opened") as any);
await drain();
const s5 = svc5.getStatus();
check("first failure → still pending (retry scheduled)", s5.pending === 1 && s5.dead === 0);
clock += 20 * 60 * 1000; await svc5.tick(); // attempt 2
clock += 20 * 60 * 1000; await svc5.tick(); // attempt 3 → ceiling
check("dead-letter after maxAttempts", svc5.getStatus().dead === 1);
check("dead-letter is logged (observable failure)", logLines.some((l) => l.includes("DEAD-LETTER")));

// ─── 6. Rate limiting ────────────────────────────────────────────────────────
section("6. Rate limit between dispatches (extras queued, not dropped)");
clock = 9_000_000;
const dispatched6: any[] = [];
const dispatchOk6: DispatchFn = async (req) => { dispatched6.push(req); return { ok: true, status: 204 }; };
const svc6 = new BridgeIntakeService(baseConfig({ minIntervalMs: 60_000 }), { now: () => clock, dispatch: dispatchOk6, log: () => {} });
svc6.handle(issueEvent("opened", { issue: { number: 1 } }) as any);
await drain();
svc6.handle(issueEvent("opened", { issue: { number: 2 } }) as any);
await drain();
check("first event dispatched immediately", dispatched6.length === 1);
check("second event rate-limited into pending queue", svc6.getStatus().pending === 1 && dispatched6.length === 1);
clock += 61_000;
await svc6.tick();
check("queued event dispatched after interval elapses", dispatched6.length === 2, `got ${dispatched6.length}`);

// ─── 7. Outbox durability + boot replay ─────────────────────────────────────
section("7. Durable outbox survives restart (replay pending)");
const outboxPath = join(mkdtempSync(join(tmpdir(), "intake-")), "outbox.jsonl");
clock = 12_000_000;
let failFirst = true;
const dispatchFlaky: DispatchFn = async () => {
  if (failFirst) { failFirst = false; throw new Error("transient network"); }
  return { ok: true, status: 204 };
};
const svc7a = new BridgeIntakeService(baseConfig({ outboxPath }), { now: () => clock, dispatch: dispatchFlaky, log: () => {} });
svc7a.handle(issueEvent("opened", { issue: { number: 42 } }) as any);
await drain();
check("transient failure → entry pending in outbox", svc7a.getStatus().pending === 1);
check("outbox file exists on disk", existsSync(outboxPath));
const rawDisk = readFileSync(outboxPath, "utf8");
check("outbox file contains no secrets", !rawDisk.includes("test-token"));

// New process, same outbox → replay delivers the pending entry (clock past backoff).
const svc7b = new BridgeIntakeService(baseConfig({ outboxPath }), { now: () => clock + 10_000, dispatch: async () => ({ ok: true, status: 204 }), log: () => {} });
const replayed = svc7b.replayPending();
await drain();
check("replayPending() picks up the persisted entry", replayed === 1);
check("replayed entry reaches done", svc7b.getStatus().done === 1 && svc7b.getStatus().pending === 0);

// ─── 8. Latency measurement ─────────────────────────────────────────────────
section("8. Webhook-to-dispatch latency recorded");
clock = 15_000_000;
const svc8 = new BridgeIntakeService(baseConfig(), {
  now: () => clock,
  dispatch: async () => { clock += 120; return { ok: true, status: 204 }; },
  log: () => {},
});
svc8.handle(issueEvent("opened") as any);
await drain();
const lastLine = readFileSync((svc8 as any).config.outboxPath, "utf8").trim().split("\n").pop()!;
const doneEntry = JSON.parse(lastLine) as OutboxEntry;
check("done entry records latencyMs", typeof doneEntry.latencyMs === "number" && doneEntry.latencyMs >= 0, `latencyMs=${doneEntry.latencyMs}`);

// ─── 9. Normalizer delivery passthrough ──────────────────────────────────────
section("9. Normalizer passes X-GitHub-Delivery through");
const norm = globalEventNormalizer.normalizeGitHubEvent("issues", { action: "opened", repository: { full_name: "x/y" } }, "delivery-XYZ");
check("deliveryId lands on normalized event", norm.deliveryId === "delivery-XYZ");

// ─── Verdict ─────────────────────────────────────────────────────────────────
console.log("\n=============================================");
if (failures === 0) {
  console.log("ALL BRIDGE INTAKE TESTS PASSED (#69)");
} else {
  console.error(`${failures} TEST(S) FAILED (#69)`);
}
process.exit(failures === 0 ? 0 : 1);
