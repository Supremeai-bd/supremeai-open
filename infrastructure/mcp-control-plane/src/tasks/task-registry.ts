/**
 * Central Task Queue & Lease State Machine (issue #2596).
 *
 * বাংলা মন্তব্য: এজেন্ট ফ্লিট এখন পর্যন্ত টাস্ক খোঁজা/ক্লেইম/স্ট্যাটাসের জন্য
 * সরাসরি GitHub API-তে নির্ভরশীল ছিল (`gh issue list` / `gh issue edit`) —
 * ফলে (১) ৫,০০০ রিকোয়েস্টের rate-limit মুহূর্তেই ফুরিয়ে যায়, (২) ক্র্যাশ করা
 * এজেন্টের `status:in-progress` লেবেল ইস্যুতে ঝুলে থাকে (ghost state), (৩)
 * কে কী নিয়ে কাজ করছে তার কোনো সেন্ট্রাল স্টেট মেশিন নেই।
 *
 * এই মডিউলটি Control Tower-এর ভেতরেই সেই সেন্ট্রাল কিউ দাঁড় করায়:
 *
 *   ┌────────────┬───────────────────────────────────────────────────────────┐
 *   │ State      │ Meaning                                                   │
 *   ├────────────┼───────────────────────────────────────────────────────────┤
 *   │ UNCLAIMED  │ কিউতে আছে, যেকোনো এজেন্ট ক্লেইম করতে পারে                  │
 *   │ LEASED     │ কোনো slot এর কাছে ২০-মিনিটের লিজ — heartbeat দিয়ে রিনিউ   │
 *   │ COMPLETED  │ টাস্ক শেষ — knowledge transaction (why/alternatives) সহ  │
 *   └────────────┴───────────────────────────────────────────────────────────┘
 *
 * Race-safety (লিজ লক):
 *   - Node ইভেন্ট-লুপ single-threaded → claim-এর check-and-set একই টিক-এ
 *     সম্পন্ন হয়, দুজন এজেন্ট একসাথে একই টাস্ক পেতে পারে না।
 *   - claim একটি ওয়ান-টাইম `claimToken` (UUID) ফেরায়; heartbeat/complete
 *     অবশ্যই সেই টোকেন পেশ করবে — লিজ expire হয়ে অন্য slot নিয়ে নিলে
 *     পুরনো এজেন্টের টোকেন মূল প্রমাণ হিসেবে বাতিল (stale-writer protection)।
 *   - Lease TTL ২০ মিনিট; expiry lazy-evaluation + sweep — ক্র্যাশ করা
 *     এজেন্টের টাস্ক অটো-রিলিজ হয়ে কিউতে ফিরে আসে (ghost state নির্মূল)।
 *
 * Storage (agent_heartbeat.ts-এর hash pattern অনুসরণে):
 *   Key:    supremeai:task-queue            (single hash)
 *   Field:  <issue-number>
 *   Value:  JSON TaskRecord
 *   মেমরি-first: in-process Map-ই authoritative; Redis হলো tower-restart
 *   durability (best-effort, chain-walking + quota cooldown)। Redis না থাকলে
 *   memory-only মোডে graceful ডিগ্রেডেশন (সংবিধান Rule ৩)।
 *
 * GitHub sync (#2596 scope item 5):
 *   টাওয়ার নিজেই ব্যাকগ্রাউন্ডে open issues টেনে কিউ ভরে রাখে — এজেন্টদের
 *   আর GitHub-এ list/edit করতে হয় না। লোকাল লিজ-স্টেট সবসময় GitHub-এর
 *   উপরে জেতে; GitHub-এ বন্ধ হয়ে যাওয়া ইস্যু external-complete হিসেবে
 *   চিহ্নিত হয়।
 */

import { randomUUID } from "node:crypto";
import {
  activeAccountChain,
  markAccountQuotaExhausted,
  responseIndicatesQuotaExhaustion,
  type RedisAccountConfig,
} from "../lib/redis_chain.js";
import { getAccountConfig, githubHeaders } from "../adapters/github/index.js";
import { httpRequest } from "../lib/http.js";
import { validateSlot } from "../registry/agent_heartbeat.js";

// ─── Constants ─────────────────────────────────────────────────────────────

export const TASK_QUEUE_HASH_KEY = "supremeai:task-queue";
/** বাংলা: লিজের আয়ু — claim/heartbeat প্রতিবার এই মেয়াদ পুনরায় সেট করে। */
export const LEASE_TTL_MS = 20 * 60 * 1000;
/** বাংলা: GET /tasks যত পুরনো হলে ব্যাকগ্রাউন্ড GitHub সিঙ্ক ছোড়া হয়। */
export const SYNC_STALE_MS = 60 * 1000;
/** বাংলা: COMPLETED রেকর্ড Redis-এ এই মেয়াদ পরে prune হয় (স্প্রল রোধ)। */
export const PRUNE_COMPLETED_MS = 24 * 60 * 60 * 1000;
/** বাংলা: সিঙ্ক একবারে যত পৃষ্ঠা (১০০/পৃষ্ঠা) টানতে পারে। */
const SYNC_MAX_PAGES = 3;

// ─── Types ─────────────────────────────────────────────────────────────────

export type TaskState = "UNCLAIMED" | "LEASED" | "COMPLETED";

export type TaskKnowledge = {
  why: string;
  alternatives_rejected: string[];
};

export type TaskRecord = {
  issue: number;
  title: string;
  priority: string; // মূল লেবেল (যেমন "P1-high") — র‍্যাংকিং parsePriority দিয়ে হয়
  labels: string[];
  url?: string;
  state: TaskState;
  /** লিজ-মালিক slot id (যেমন "agent-3")। */
  claimedBy?: string;
  /** claim-এ জারি করা ওয়ান-টাইম লিজ টোকেন — heartbeat/complete পেশ করতে হবে। */
  claimToken?: string;
  claimedAt?: string; // ISO-8601
  claimedAtMs?: number;
  lastHeartbeatAt?: string; // ISO-8601
  leaseExpiresAtMs?: number;
  completedAt?: string; // ISO-8601
  /** external = GitHub-এ ইস্যু বন্ধ হয়ে যাওয়া (PR merge ইত্যাদি); local = টাওয়ারের /tasks/complete। */
  completedBy?: string;
  completionKind?: "local" | "external";
  knowledge?: TaskKnowledge;
  updatedAtMs: number;
  updatedAt: string; // ISO-8601
};

/** GitHub সিঙ্ক থেকে আসা ইস্যুর ন্যূনতম আকৃতি (REST /issues আইটেমের সাবসেট)। */
export type GitHubIssueSnapshot = {
  number: number;
  title: string;
  labels?: string[] | Array<{ name?: string }>;
  html_url?: string;
  pull_request?: unknown;
};

export type ClaimInput = {
  issue: number;
  slot: string;
  agent?: string;
};

export type ClaimResult =
  | {
      ok: true;
      task: TaskRecord;
      claimToken: string;
      leaseExpiresAtMs: number;
      /** true হলে একই slot-এর পুনরায় ক্লেইম — idempotent refresh, টোকেন অপরিবর্তিত। */
      idempotentReclaim: boolean;
    }
  | {
      ok: false;
      reason: "not-found" | "github-locked" | "lease-held" | "completed";
      /** lease-held কেসে বর্তমান মালিকের তথ্য (ডিবাগ/ব্যাকঅফের জন্য)। */
      heldBy?: { slot: string; claimedAt: string; leaseExpiresAtMs: number };
      error: string;
    };

export type HeartbeatInput = {
  issue: number;
  slot: string;
  claimToken: string;
};

export type CompleteInput = {
  issue: number;
  slot: string;
  claimToken: string;
  knowledge?: TaskKnowledge;
};

export type HeartbeatResult =
  | { ok: true; task: TaskRecord; leaseExpiresAtMs: number }
  | { ok: false; reason: "not-found" | "not-leased" | "token-mismatch" | "slot-mismatch" | "lease-lost"; error: string };

export type CompleteResult =
  | { ok: true; task: TaskRecord }
  | { ok: false; reason: "not-found" | "token-mismatch" | "slot-mismatch" | "already-completed"; error: string };

// ─── Priority ranking (P0-critical → P3-low, তারপর oldest-first) ─────────

const PRIORITY_ORDER: Record<string, number> = {
  "P0-critical": 0,
  "P1-high": 1,
  "P2-medium": 2,
  "P3-low": 3,
};

/** লেবেল-তালিকা থেকে priority লেবেল বের করে (না থাকলে null)। */
export function extractPriorityLabel(labels: string[]): string | null {
  for (const label of labels) {
    if (label in PRIORITY_ORDER) return label;
  }
  return null;
}

/** Priority → সংখ্যা; অজানা/অনুপস্থিত = সবচেয়ে নিচে, কিন্তু কিউ থেকে বাদ নয়। */
export function parsePriority(labels: string[]): number {
  const label = extractPriorityLabel(labels);
  return label === null ? PRIORITY_ORDER["P3-low"] + 1 : PRIORITY_ORDER[label];
}

/** র‍্যাংকিং: priority asc, তারপর issue-number asc (oldest-first)। */
export function rankTasks(tasks: TaskRecord[]): TaskRecord[] {
  return [...tasks].sort((a, b) => {
    const byPriority = parsePriority(a.labels) - parsePriority(b.labels);
    if (byPriority !== 0) return byPriority;
    return a.issue - b.issue;
  });
}

// ─── Lease expiry (pure — টেস্টে সরাসরি প্রমাণযোগ্য) ────────────────────────

export function isLeaseExpired(task: TaskRecord, nowMs: number = Date.now()): boolean {
  if (task.state !== "LEASED") return false;
  if (typeof task.leaseExpiresAtMs !== "number") return true; // অসঙ্গত রেকর্ড — নিরাপদ দিকে expire
  return nowMs >= task.leaseExpiresAtMs;
}

/**
 * বাংলা: GitHub-এর legacy ক্লেইম-মেকানিজম (`atomic_claim.sh` → status:in-progress
 * লেবেল / has-pr) এখনো প্রচলিত — সেই ইস্যুগুলো টাওয়ারের দৃষ্টিতে locked:
 * কিউতে দেখা যাবে, কিন্তু টাওয়ার-লিজ নেওয়া যাবে না (ডাবল-ক্লেইম রোধ)।
 */
export function isGithubLocked(task: TaskRecord): boolean {
  return task.labels.includes("status:in-progress") || task.labels.includes("has-pr");
}

// ─── In-memory registry (authoritative) ────────────────────────────────────

/** issue-number → record। প্রসেস-লুপে single-threaded অ্যাক্সেস = atomic CAS। */
const registry = new Map<number, TaskRecord>();

// ─── Redis persistence (best-effort durability, chain-walking) ─────────────

type TaskQueueRedisClient = {
  account: string;
  hset: (field: string, value: string) => Promise<void>;
  hgetall: () => Promise<Record<string, string>>;
  hdel: (field: string) => Promise<void>;
};

let memoryOnlyMode = false;
let memoryOnlyWarned = false;
let writeClient: TaskQueueRedisClient | null = null;

/** বাংলা: chain-এর প্রথম ব্যবহারযোগ্য account-এ REST ক্লায়েন্ট বাঁধি। */
function resolveWriteClient(): TaskQueueRedisClient | null {
  if (writeClient) return writeClient;
  const chain = activeAccountChain();
  const account = chain[0] as (RedisAccountConfig & { restUrl?: string; restToken?: string }) | undefined;
  if (!account || !account.restUrl || !account.restToken) {
    memoryOnlyMode = true;
    if (!memoryOnlyWarned) {
      memoryOnlyWarned = true;
      console.warn(
        "[task-registry] No Redis configuration found — task queue running in memory-only mode (restarts lose lease state; constitution Rule ৩ graceful degradation)",
      );
    }
    return null;
  }
  const restUrl = account.restUrl;
  const auth = `Bearer ${account.restToken}`;
  const label = account.label;
  const call = async (body: unknown[]): Promise<unknown> => {
    const res = await fetch(restUrl, {
      method: "POST",
      headers: { Authorization: auth, "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) {
      const errText = await res.text().catch(() => "");
      // বাংলা: কোটা শেষ হলে account-কে cooldown-এ ফেলি — পরের লেখায় chain এটা skip করবে।
      if (responseIndicatesQuotaExhaustion(res.status, errText)) {
        markAccountQuotaExhausted(label);
        writeClient = null; // পরের লেখায় নতুন account বাছাই
      }
      throw new Error(`Upstash REST [${label}] returned HTTP ${res.status}`);
    }
    const payload = (await res.json()) as { result?: unknown; error?: string };
    if (payload.error) {
      if (responseIndicatesQuotaExhaustion(res.status, String(payload.error))) {
        markAccountQuotaExhausted(label);
        writeClient = null;
      }
      throw new Error(`Upstash error [${label}]: ${payload.error}`);
    }
    return payload.result;
  };
  // বাংলা: ক্লায়েন্ট বাঁধা গেলে memory-only মোড প্রত্যাহার (status-সততা)।
  memoryOnlyMode = false;
  memoryOnlyWarned = true;
  writeClient = {
    account: label,
    hset: async (field, value) => {
      await call(["HSET", TASK_QUEUE_HASH_KEY, field, value]);
    },
    hgetall: async () => {
      const raw = (await call(["HGETALL", TASK_QUEUE_HASH_KEY])) as unknown;
      const result: Record<string, string> = {};
      if (!raw) return result;
      if (Array.isArray(raw)) {
        for (let i = 0; i < raw.length; i += 2) {
          const k = String(raw[i]);
          const v = String(raw[i + 1] ?? "");
          if (k) result[k] = v;
        }
      } else if (typeof raw === "object") {
        for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
          if (v != null) result[k] = typeof v === "string" ? v : JSON.stringify(v);
        }
      }
      return result;
    },
    hdel: async (field) => {
      await call(["HDEL", TASK_QUEUE_HASH_KEY, field]);
    },
  };
  return writeClient;
}

export function redisAvailable(): boolean {
  return !memoryOnlyMode;
}

/** Best-effort persist — ব্যর্থ হলে শুধু লগ (মেমরি-ই authoritative)। */
async function persist(task: TaskRecord): Promise<void> {
  try {
    const client = resolveWriteClient();
    if (!client) return;
    await client.hset(String(task.issue), JSON.stringify(task));
  } catch (err) {
    console.warn(`[task-registry] persist(${task.issue}) skipped: ${(err as Error).message}`);
  }
}

async function persistDelete(issue: number): Promise<void> {
  try {
    const client = resolveWriteClient();
    if (!client) return;
    await client.hdel(String(issue));
  } catch (err) {
    console.warn(`[task-registry] hdel(${issue}) skipped: ${(err as Error).message}`);
  }
}

// ─── Core state machine ────────────────────────────────────────────────────

function nowIso(nowMs: number): string {
  return new Date(nowMs).toISOString();
}

/**
 * Lazy expiry: প্রতিটি পাঠে LEASED রেকর্ডের মেয়াদ পরীক্ষা করে বাসি লিজ
 * অটো-রিলিজ করি (ghost state নির্মূল — #2596-এর মূল লক্ষ্য)। প্রসেস-লুপের
 * single-thread হওয়ায় এই মিউটেশনও claim-এর মতোই race-safe।
 */
function releaseExpiredLeases(nowMs: number = Date.now()): number {
  let released = 0;
  for (const task of registry.values()) {
    if (isLeaseExpired(task, nowMs)) {
      const ghostSlot = task.claimedBy;
      task.state = "UNCLAIMED";
      task.claimedBy = undefined;
      task.claimToken = undefined;
      task.claimedAt = undefined;
      task.claimedAtMs = undefined;
      task.lastHeartbeatAt = undefined;
      task.leaseExpiresAtMs = undefined;
      task.updatedAtMs = nowMs;
      task.updatedAt = nowIso(nowMs);
      released += 1;
      console.log(
        `[task-registry] lease expired → auto-release issue #${task.issue} (ghost owner: ${ghostSlot ?? "unknown"})`,
      );
      void persist(task);
    }
  }
  return released;
}

export function getTask(issue: number): TaskRecord | undefined {
  releaseExpiredLeases();
  return registry.get(issue);
}

/** র‍্যাংক করা পূর্ণ কিউ-স্ন্যাপশট (UNCLAIMED + LEASED + COMPLETED — ক্লায়েন্ট ফিল্টার করবে)। */
export function listTasks(): TaskRecord[] {
  releaseExpiredLeases();
  return rankTasks([...registry.values()]);
}

/** কিউ-স্বাস্থ্যের সারসংক্ষেপ — GET /tasks-এর status অংশে যায়। */
export function taskQueueStatus(nowMs: number = Date.now()) {
  releaseExpiredLeases(nowMs);
  const tasks = [...registry.values()];
  const leased = tasks.filter((t) => t.state === "LEASED");
  return {
    total: tasks.length,
    unclaimed: tasks.filter((t) => t.state === "UNCLAIMED").length,
    leased: leased.length,
    completed: tasks.filter((t) => t.state === "COMPLETED").length,
    githubLocked: tasks.filter((t) => t.state !== "COMPLETED" && isGithubLocked(t)).length,
    memoryOnly: memoryOnlyMode,
    leaseTtlMs: LEASE_TTL_MS,
    lastSyncAt: lastSyncAtMs ? nowIso(lastSyncAtMs) : null,
    lastSyncOk: lastSyncOk,
  };
}

/**
 * বাংলা: রেস-সেফ এটমিক ক্লেইম। ইভেন্ট-লুপের একই টিক-এ check-and-set হয়।
 * একই slot পুনরায় ক্লেইম করলে idempotent — একই টোকেন ফেরত পায় (রিট্রাই-সেফ)।
 */
export function claimTask(input: ClaimInput, nowMs: number = Date.now()): ClaimResult {
  releaseExpiredLeases(nowMs);
  const issue = input.issue;
  if (!Number.isInteger(issue) || issue <= 0) {
    return { ok: false, reason: "not-found", error: "issue must be a positive integer" };
  }
  const slotError = validateSlot(input.slot);
  if (slotError) {
    return { ok: false, reason: "not-found", error: `invalid slot: ${slotError}` };
  }
  const task = registry.get(issue);
  if (!task) {
    return { ok: false, reason: "not-found", error: `task #${issue} is not in the queue (run a GitHub sync first)` };
  }
  if (task.state === "COMPLETED") {
    return { ok: false, reason: "completed", error: `task #${issue} is already completed` };
  }
  if (isGithubLocked(task)) {
    // বাংলা: legacy atomic_claim.sh মেকানিজম ইতিমধ্যে ইস্যুটি ধরে রেখেছে —
    // টাওয়ার-লিজ নেওয়া ডাবল-ওয়ার্ক হবে।
    return {
      ok: false,
      reason: "github-locked",
      error: `task #${issue} carries status:in-progress/has-pr label on GitHub (legacy claim active)`,
    };
  }
  if (task.state === "LEASED") {
    if (task.claimedBy === input.slot) {
      // idempotent re-claim — একই টোকেন, মেয়াদ রিনিউ
      task.leaseExpiresAtMs = nowMs + LEASE_TTL_MS;
      task.updatedAtMs = nowMs;
      task.updatedAt = nowIso(nowMs);
      void persist(task);
      return {
        ok: true,
        task,
        claimToken: task.claimToken as string,
        leaseExpiresAtMs: task.leaseExpiresAtMs,
        idempotentReclaim: true,
      };
    }
    return {
      ok: false,
      reason: "lease-held",
      heldBy: {
        slot: task.claimedBy as string,
        claimedAt: task.claimedAt as string,
        leaseExpiresAtMs: task.leaseExpiresAtMs as number,
      },
      error: `task #${issue} is leased by ${task.claimedBy} until ${nowIso(task.leaseExpiresAtMs as number)}`,
    };
  }
  const claimToken = randomUUID();
  task.state = "LEASED";
  task.claimedBy = input.slot;
  task.claimToken = claimToken;
  task.claimedAt = nowIso(nowMs);
  task.claimedAtMs = nowMs;
  task.lastHeartbeatAt = nowIso(nowMs);
  task.leaseExpiresAtMs = nowMs + LEASE_TTL_MS;
  task.completedBy = undefined;
  task.completionKind = undefined;
  task.updatedAtMs = nowMs;
  task.updatedAt = nowIso(nowMs);
  void persist(task);
  console.log(`[task-registry] issue #${issue} leased by ${input.slot}${input.agent ? ` (${input.agent})` : ""} — TTL ${LEASE_TTL_MS / 60000}min`);
  return { ok: true, task, claimToken, leaseExpiresAtMs: task.leaseExpiresAtMs, idempotentReclaim: false };
}

/** লিজ-টোকেন প্রমাণ সহ heartbeat — মেয়াদ রিনিউ করে। */
export function heartbeatTask(input: HeartbeatInput, nowMs: number = Date.now()): HeartbeatResult {
  releaseExpiredLeases(nowMs);
  const task = registry.get(input.issue);
  if (!task) {
    return { ok: false, reason: "not-found", error: `task #${input.issue} is not in the queue` };
  }
  if (task.state === "COMPLETED") {
    return { ok: false, reason: "not-leased", error: `task #${input.issue} is already completed` };
  }
  if (task.state !== "LEASED") {
    return { ok: false, reason: "not-leased", error: `task #${input.issue} has no active lease` };
  }
  if (task.claimedBy !== input.slot) {
    return { ok: false, reason: "slot-mismatch", error: `lease owned by ${task.claimedBy}, not ${input.slot}` };
  }
  if (task.claimToken !== input.claimToken) {
    // বাংলা: টোকেন না মিললে লিজ হাতবদল হয়েছে (expiry → reclaim) — পুরনো এজেন্ট stale।
    return { ok: false, reason: "token-mismatch", error: "claimToken does not match current lease (lease may have been reclaimed after expiry)" };
  }
  task.lastHeartbeatAt = nowIso(nowMs);
  task.leaseExpiresAtMs = nowMs + LEASE_TTL_MS;
  task.updatedAtMs = nowMs;
  task.updatedAt = nowIso(nowMs);
  void persist(task);
  return { ok: true, task, leaseExpiresAtMs: task.leaseExpiresAtMs };
}

/**
 * সমাপ্তি + knowledge push একই ট্রানজেকশনে (why / alternatives_rejected —
 * AGENTS.md knowledge-sharing স্কিমা)।
 */
export function completeTask(input: CompleteInput, nowMs: number = Date.now()): CompleteResult {
  releaseExpiredLeases(nowMs);
  const task = registry.get(input.issue);
  if (!task) {
    return { ok: false, reason: "not-found", error: `task #${input.issue} is not in the queue` };
  }
  if (task.state === "COMPLETED") {
    return { ok: false, reason: "already-completed", error: `task #${input.issue} is already completed (${task.completionKind ?? "unknown"} by ${task.completedBy ?? "unknown"})` };
  }
  if (task.claimedBy !== input.slot) {
    return { ok: false, reason: "slot-mismatch", error: `lease owned by ${task.claimedBy ?? "nobody"}, not ${input.slot}` };
  }
  if (task.claimToken !== input.claimToken) {
    return { ok: false, reason: "token-mismatch", error: "claimToken does not match current lease" };
  }
  task.state = "COMPLETED";
  task.completedAt = nowIso(nowMs);
  task.completedBy = input.slot;
  task.completionKind = "local";
  if (input.knowledge) {
    task.knowledge = {
      why: String(input.knowledge.why ?? ""),
      alternatives_rejected: Array.isArray(input.knowledge.alternatives_rejected)
        ? input.knowledge.alternatives_rejected.map(String)
        : [],
    };
  }
  task.updatedAtMs = nowMs;
  task.updatedAt = nowIso(nowMs);
  void persist(task);
  console.log(`[task-registry] issue #${input.issue} completed by ${input.slot}${task.knowledge ? " (+knowledge transaction)" : ""}`);
  return { ok: true, task };
}

// ─── GitHub sync (#2596 scope-৫: এজেন্টদের GitHub নির্ভরতা সরিয়ে টাওয়ারে) ───

let lastSyncAtMs: number | null = null;
let lastSyncOk: boolean | null = null;
let syncInFlight: Promise<{ ok: boolean; error?: string }> | null = null;

function normalizeLabels(raw: GitHubIssueSnapshot["labels"]): string[] {
  if (!raw) return [];
  return raw
    .map((l) => (typeof l === "string" ? l : (l?.name ?? "")))
    .filter((l): l is string => Boolean(l));
}

/**
 * Pure merge — GitHub-এর open-issue স্ন্যাপশটকে লোকাল রেজিস্ট্রিতে ভেজালে:
 *   - নতুন ইস্যু → UNCLAIMED রেকর্ড
 *   - পুরনো ইস্যু → title/labels/priority রিফ্রেশ (লিজ-স্টেট অক্ষুণ্ণ)
 *   - GitHub-এ আর নেই (বন্ধ হয়েছে) → LEASED/UNCLAIMED হলে external-complete
 * টেস্ট সরাসরি এই ফাংশনটি নকল স্ন্যাপশট দিয়ে চালাতে পারে (নেটওয়ার্ক লাগে না)।
 */
export function applyGitHubSnapshot(issues: GitHubIssueSnapshot[], nowMs: number = Date.now()): {
  added: number;
  updated: number;
  externallyCompleted: number;
} {
  releaseExpiredLeases(nowMs);
  const openIssues = new Set(issues.map((i) => i.number));
  let added = 0;
  let updated = 0;
  let externallyCompleted = 0;

  for (const issue of issues) {
    if (typeof issue.number !== "number" || issue.pull_request) continue; // PR এন্ট্রি বাদ
    const labels = normalizeLabels(issue.labels);
    const priority = extractPriorityLabel(labels) ?? "unlabeled";
    const existing = registry.get(issue.number);
    if (!existing) {
      registry.set(issue.number, {
        issue: issue.number,
        title: issue.title,
        priority,
        labels,
        url: issue.html_url,
        state: "UNCLAIMED",
        updatedAtMs: nowMs,
        updatedAt: nowIso(nowMs),
      });
      added += 1;
    } else {
      existing.title = issue.title;
      existing.labels = labels;
      existing.priority = priority;
      existing.url = issue.html_url ?? existing.url;
      existing.updatedAtMs = nowMs;
      existing.updatedAt = nowIso(nowMs);
      updated += 1;
      void persist(existing);
    }
  }

  // বাংলা: GitHub-এ বন্ধ হয়ে যাওয়া ইস্যু — লোকাল লিজ থাকলেও কাজ শেষ
  // (PR merge হয়েছে বলেই তো বন্ধ) → external-complete চিহ্নিত।
  for (const task of registry.values()) {
    if (!openIssues.has(task.issue) && task.state !== "COMPLETED") {
      task.state = "COMPLETED";
      task.completedAt = nowIso(nowMs);
      task.completionKind = "external";
      task.completedBy = task.completedBy ?? "github";
      task.claimToken = undefined;
      task.updatedAtMs = nowMs;
      task.updatedAt = nowIso(nowMs);
      externallyCompleted += 1;
      void persist(task);
    }
  }

  // COMPLETED-প্রুন: ২৪ ঘণ্টার পুরনো সম্পন্ন রেকর্ড মেমরি+Redis থেকে সরাই।
  for (const [issue, task] of [...registry.entries()]) {
    if (task.state === "COMPLETED" && nowMs - task.updatedAtMs > PRUNE_COMPLETED_MS) {
      registry.delete(issue);
      void persistDelete(issue);
    }
  }

  return { added, updated, externallyCompleted };
}

/** GitHub REST থেকে open issues টানে (pagination-সহ, PR ফিল্টার applyGitHubSnapshot-এ)। */
async function fetchOpenIssues(): Promise<GitHubIssueSnapshot[]> {
  const accountId = process.env["TASKS_GITHUB_ACCOUNT"] ?? "github-primary";
  const { apiKey: token, baseUrl } = getAccountConfig(accountId);
  const collected: GitHubIssueSnapshot[] = [];
  for (let page = 1; page <= SYNC_MAX_PAGES; page += 1) {
    const res = await httpRequest<GitHubIssueSnapshot[]>(`${baseUrl}/issues?state=open&per_page=100&page=${page}`, {
      headers: githubHeaders(token),
    });
    const items = Array.isArray(res.data) ? res.data : [];
    collected.push(...items);
    if (items.length < 100) break;
  }
  return collected;
}

/**
 * বাংলা: পূর্ণ সিঙ্ক-চক্র — GitHub টানে → pure merge চালায়। ব্যর্থ হলে
 * graceful (লোকাল স্টেট অক্ষুণ্ণ, lastSyncOk=false হয়ে status-এ দেখা যায়)।
 */
export async function refreshFromGitHub(): Promise<{ ok: boolean; error?: string }> {
  if (syncInFlight) return syncInFlight;
  syncInFlight = (async () => {
    try {
      const issues = await fetchOpenIssues();
      const result = applyGitHubSnapshot(issues);
      lastSyncAtMs = Date.now();
      lastSyncOk = true;
      console.log(
        `[task-registry] GitHub sync ok — +${result.added} added, ${result.updated} refreshed, ${result.externallyCompleted} externally completed`,
      );
      return { ok: true };
    } catch (err) {
      lastSyncAtMs = Date.now();
      lastSyncOk = false;
      const message = (err as Error).message;
      console.warn(`[task-registry] GitHub sync failed (queue keeps last known state): ${message}`);
      return { ok: false, error: message };
    } finally {
      syncInFlight = null;
    }
  })();
  return syncInFlight;
}

/** GET /tasks-এর হুক: ক্যাশ বাসি হলে ব্যাকগ্রাউন্ডে সিঙ্ক ছোড়ে (non-blocking)। */
export function ensureFreshSync(): void {
  if (lastSyncAtMs === null || Date.now() - lastSyncAtMs > SYNC_STALE_MS) {
    void refreshFromGitHub();
  }
}

// ─── Boot hydration (tower restart-এ লিজ-স্টেট ফিরিয়ে আনা) ─────────────────

/**
 * বাংলা: boot-এ Redis hash থেকে রেকর্ড হাইড্রেট করি — tower restart-এর
 * পরেও চালু লিজ হারায় না। ব্যর্থ হলে memory-only চালু থাকে (Rule ৩)।
 */
export async function initTaskRegistry(): Promise<{ hydrated: number; memoryOnly: boolean }> {
  try {
    const client = resolveWriteClient();
    if (!client) return { hydrated: 0, memoryOnly: true };
    const raw = await client.hgetall();
    let hydrated = 0;
    const nowMs = Date.now();
    for (const [field, value] of Object.entries(raw)) {
      try {
        const record = JSON.parse(value) as TaskRecord;
        if (typeof record.issue === "number" && record.state) {
          registry.set(record.issue, { ...record, updatedAtMs: record.updatedAtMs ?? nowMs, updatedAt: record.updatedAt ?? nowIso(nowMs) });
          hydrated += 1;
        }
      } catch {
        console.warn(`[task-registry] hydrate: corrupt record for field ${field} — skipped`);
      }
    }
    releaseExpiredLeases();
    console.log(`[task-registry] hydrated ${hydrated} task record(s) from Redis`);
    return { hydrated, memoryOnly: false };
  } catch (err) {
    console.warn(`[task-registry] hydrate failed (memory-only continues): ${(err as Error).message}`);
    return { hydrated: 0, memoryOnly: true };
  }
}
