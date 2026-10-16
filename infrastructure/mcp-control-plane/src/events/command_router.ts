/**
 * Command Router (#211 slice 1) — ChatOps commands + post-merge lifecycle
 * cleanup over the existing `/webhooks/github` → EventGateway flow.
 *
 * বাংলা নোট: এই slice টা #211-এর ৫টা কাজের মধ্যে সবচেয়ে ছোট নিরাপদ অংশ —
 * slash-command parsing (item 1-এর registry skeleton) আর post-merge
 * auto-close issue + auto-delete head branch (item 5, সম্পূর্ণ কার্যকর)।
 * Pre-flight check (item 2), polling diet (item 3, pipeline.yml) এবং
 * multi-channel dispatch (item 4) পরের slice-এ আসবে।
 *
 * Design doctrine (mirrors bridge_intake.ts):
 *  - Subscribes to the ALREADY-deployed webhook route via the shared
 *    EventGateway — no new HTTP surface, no new secrets, no protected paths.
 *  - Least privilege: uses the server-side GITHUB_TOKEN only, never exposed
 *    to the caller; tokenless boot degrades fail-honest (skip + log, never
 *    throw — the cron reconciliation poll remains the safety net).
 *  - Idempotent: 404/422 on close/delete means "already done" and counts as
 *    reconciled, so replayed webhook deliveries are safe.
 *  - Fail-safe guards: never deletes the base branch (main/master), never
 *    closes more than MAX_LIFECYCLE_ISSUES_PER_EVENT issues per event.
 */

import { NormalizedEvent } from "./normalizer.js";
import { globalEventGateway } from "./gateway.js";
import { env } from "../lib/env.js";

// ─────────────────────────────────────────────────────────────────────────────
// ChatOps slash commands (#211 item 1 — parse + registry skeleton)
// ─────────────────────────────────────────────────────────────────────────────

export interface SlashCommand {
  name: string;
  args: string[];
}

export type CommandHandler = (cmd: SlashCommand, event: NormalizedEvent) => void | Promise<void>;

const commandRegistry = new Map<string, CommandHandler>();

/** Canonical ChatOps command names (#211 item 1). Extend via registerCommand. */
export const CANONICAL_COMMANDS = ["claim", "verify", "cancel", "role"] as const;

/**
 * Registers (or replaces) a handler for a slash command. Handlers are wired
 * at composition time (src/index.ts) — the router itself stays side-effect
 * free so unmatched commands can never mutate anything.
 */
export function registerCommand(name: string, handler: CommandHandler): void {
  const normalized = name.trim().toLowerCase().replace(/^\//, "");
  if (!normalized) throw new Error("registerCommand: command name required");
  commandRegistry.set(normalized, handler);
}

export function getRegisteredCommands(): string[] {
  return [...commandRegistry.keys()].sort();
}

/**
 * Parses a comment body into a slash command. Returns null for non-commands
 * (the overwhelming majority of comments) so the hot path stays cheap.
 * `/role coder` → { name: "role", args: ["coder"] }
 */
export function parseSlashCommand(text: string | undefined | null): SlashCommand | null {
  if (!text) return null;
  const m = /^\s*\/([A-Za-z][A-Za-z0-9_-]*)(?:\s+(.*))?\s*$/.exec(text);
  if (!m) return null;
  const name = m[1].toLowerCase();
  const args = (m[2] ?? "").split(/\s+/).filter(Boolean);
  return { name, args };
}

// ─────────────────────────────────────────────────────────────────────────────
// Post-merge lifecycle cleanup (#211 item 5 — auto-close issue + auto-delete
// head branch)
// ─────────────────────────────────────────────────────────────────────────────

/** Closing-keyword scan over the PR body (GitHub auto-close grammar). */
export const CLOSE_KEYWORD_RE =
  /\b(?:close[sd]?|fix(?:es)?|resolve[sd]?)\s+(?:([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+))?#(\d+)\b/gi;

/** Branch-name linkage: contributor/issue-N, bridge-*-issue-N, task-N. */
export const BRANCH_ISSUE_RE = /(?:^|\/)(?:contributor\/issue-|bridge-[a-z0-9-]*-issue-|task-)(\d+)(?:$|[^0-9])/;

/** Never close more than this many issues from a single PR (runaway guard). */
export const MAX_LIFECYCLE_ISSUES_PER_EVENT = 10;

/** Base branches are never deleted, no matter what the head ref says. */
const PROTECTED_BRANCHES = new Set(["main", "master"]);

export interface LifecycleResult {
  issuesClosed: number[];
  issuesAlreadyClosed: number[];
  branchDeleted: string | null;
  branchAlreadyGone: boolean;
  skipped: string[];
}

export interface PullRequestLike {
  merged?: boolean;
  merged_at?: string | null;
  body?: string | null;
  head?: { ref?: string; repo?: { full_name?: string } | null };
  base?: { ref?: string; repo?: { full_name?: string } | null };
  number?: number;
}

/**
 * Extracts issue numbers a merged PR claims: body closing keywords (same-repo
 * `#N` and cross-repo `owner/repo#N` — cross-repo entries carry their own
 * target and are closed there) plus branch-name linkage. Deduplicated,
 * capped at MAX_LIFECYCLE_ISSUES_PER_EVENT.
 */
export function extractLinkedIssues(
  pr: PullRequestLike,
): Array<{ repo: string | null; number: number }> {
  const out: Array<{ repo: string | null; number: number }> = [];
  const seen = new Set<string>();
  const push = (repo: string | null, num: number) => {
    const key = `${repo || ""}#${num}`;
    if (seen.has(key) || !Number.isFinite(num) || num <= 0) return;
    seen.add(key);
    out.push({ repo, number: num });
  };

  const body = pr.body || "";
  for (const m of body.matchAll(CLOSE_KEYWORD_RE)) {
    push(m[1] && m[2] ? `${m[1]}/${m[2]}` : null, parseInt(m[3], 10));
  }
  const branchRef = pr.head?.ref || "";
  const bm = BRANCH_ISSUE_RE.exec(branchRef);
  if (bm) push(null, parseInt(bm[1], 10));

  return out.slice(0, MAX_LIFECYCLE_ISSUES_PER_EVENT);
}

interface FetchImpl {
  (url: string, init?: Record<string, unknown>): Promise<{ status: number; ok: boolean }>;
}

/**
 * Runs the post-merge cleanup for a `pull_request.closed && merged` payload:
 *  1. PATCH each linked issue → state:closed (idempotent on already-closed).
 *  2. DELETE the PR head branch unless it is a protected base branch
 *     (GitHub usually already deleted it — 404 counts as reconciled).
 *
 * Fail-honest: missing GITHUB_TOKEN → every action is recorded in `skipped`
 * and nothing throws (the pipeline reconciliation poll stays the safety net).
 * `fetchImpl` is injectable for offline tests.
 */
export async function runLifecycleCleanup(
  payload: Record<string, any>,
  opts: { fetchImpl?: FetchImpl; token?: string; log?: (msg: string) => void } = {},
): Promise<LifecycleResult> {
  const result: LifecycleResult = {
    issuesClosed: [],
    issuesAlreadyClosed: [],
    branchDeleted: null,
    branchAlreadyGone: false,
    skipped: [],
  };
  const log = opts.log ?? ((msg: string) => console.log(`[COMMAND ROUTER] ${msg}`));

  const pr: PullRequestLike | undefined = payload?.pull_request;
  if (!pr || pr.merged !== true) {
    result.skipped.push("not a merged pull_request.closed payload");
    return result;
  }

  const webhookRepo = payload?.repository?.full_name;
  if (!webhookRepo) {
    result.skipped.push("repository.full_name missing from payload");
    return result;
  }

  const token = opts.token ?? env.github.token;
  const doFetch: FetchImpl = opts.fetchImpl ?? (globalThis.fetch as unknown as FetchImpl);
  if (!token) {
    result.skipped.push(
      "GITHUB_TOKEN absent — lifecycle cleanup degraded to notify-only (fail-honest)",
    );
    log("GITHUB_TOKEN absent — skipping issue close + branch delete (reconciliation poll remains the safety net)");
    return result;
  }
  if (typeof doFetch !== "function") {
    result.skipped.push("no fetch implementation available");
    return result;
  }

  const authHeaders = {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "Content-Type": "application/json",
    "User-Agent": "supremeai-mcp-tower-command-router",
  };

  // 1. Auto-close linked issues (idempotent).
  const linked = extractLinkedIssues(pr);
  for (const { repo, number } of linked) {
    const targetRepo = repo || webhookRepo;
    try {
      const res = await doFetch(`https://api.github.com/repos/${targetRepo}/issues/${number}`, {
        method: "PATCH",
        headers: authHeaders,
        body: JSON.stringify({ state: "closed", state_reason: "completed" }),
      });
      if (res.status === 200 || res.ok) {
        result.issuesClosed.push(number);
        log(`closed issue ${targetRepo}#${number} (merged PR cleanup)`);
      } else if (res.status === 404 || res.status === 422) {
        // 404: issue gone · 422: already closed / shard race — reconciled.
        result.issuesAlreadyClosed.push(number);
        log(`issue ${targetRepo}#${number} already closed or absent (HTTP ${res.status}) — reconciled`);
      } else {
        result.skipped.push(`close ${targetRepo}#${number}: HTTP ${res.status}`);
        log(`unexpected HTTP ${res.status} closing ${targetRepo}#${number} — left for reconciliation poll`);
      }
    } catch (err) {
      result.skipped.push(`close ${targetRepo}#${number}: ${(err as Error).message}`);
    }
  }

  // 2. Auto-delete the head branch (never a protected base branch).
  const headRef = pr.head?.ref || "";
  const headRepo = pr.head?.repo?.full_name || webhookRepo;
  if (!headRef || PROTECTED_BRANCHES.has(headRef) || headRef === pr.base?.ref) {
    log(`head branch '${headRef || "(none)"}' is protected or missing — delete skipped`);
  } else {
    try {
      const res = await doFetch(
        `https://api.github.com/repos/${headRepo}/git/refs/heads/${encodeURIComponent(headRef)}`,
        { method: "DELETE", headers: authHeaders },
      );
      if (res.status === 204 || res.ok) {
        result.branchDeleted = headRef;
        log(`deleted merged head branch ${headRepo}:${headRef}`);
      } else if (res.status === 404 || res.status === 422 || res.status === 409) {
        // 404: already deleted (delete_branch_on_merge / fork branch) — fine.
        result.branchAlreadyGone = true;
        log(`head branch ${headRepo}:${headRef} already gone (HTTP ${res.status}) — reconciled`);
      } else {
        result.skipped.push(`delete ${headRepo}:${headRef}: HTTP ${res.status}`);
        log(`unexpected HTTP ${res.status} deleting ${headRepo}:${headRef} — left for reconciliation poll`);
      }
    } catch (err) {
      result.skipped.push(`delete ${headRepo}:${headRef}: ${(err as Error).message}`);
    }
  }

  return result;
}

// ─────────────────────────────────────────────────────────────────────────────
// Router registration — one EventGateway subscription, idempotent.
// ─────────────────────────────────────────────────────────────────────────────

let registered = false;

interface GatewayLike {
  subscribe(listener: (event: NormalizedEvent) => void | Promise<void>): void;
}

/**
 * Arms the router on the shared EventGateway:
 *  - `pull_request` closed+merged → post-merge lifecycle cleanup (#211 item 5)
 *  - `issue_comment` / `pull_request_review_comment` → slash-command parse +
 *    registry dispatch (no default handlers ⇒ unmatched commands are logged,
 *    never executed — side-effect free by construction)
 *  - everything else → ignored (single router, zero duplicate dispatch)
 */
export function registerCommandRouter(gateway: GatewayLike = globalEventGateway): void {
  if (registered) return;
  registered = true;

  gateway.subscribe(async (event: NormalizedEvent) => {
    if (event.source !== "github") return;
    const payload = event.payload as Record<string, any> | undefined;
    if (!payload) return;

    if (event.type === "pull_request") {
      if (payload.action === "closed" && payload.pull_request?.merged === true) {
        try {
          const result = await runLifecycleCleanup(payload);
          if (result.skipped.length) {
            console.warn(`[COMMAND ROUTER] lifecycle cleanup incomplete: ${result.skipped.join("; ")}`);
          }
        } catch (err) {
          // Gateway already catches listener rejections; this is belt & braces.
          console.error(`[COMMAND ROUTER] lifecycle cleanup error: ${(err as Error).message}`);
        }
      }
      return;
    }

    if (event.type === "issue_comment" || event.type === "pull_request_review_comment") {
      const comment = payload.comment?.body as string | undefined;
      const cmd = parseSlashCommand(comment);
      if (!cmd) return;
      const handler = commandRegistry.get(cmd.name);
      if (!handler) {
        console.log(`[COMMAND ROUTER] unmatched command /${cmd.name} (${getRegisteredCommands().join(", ") || "none registered"}) — no-op`);
        return;
      }
      await handler(cmd, event);
    }
  });

  console.log("[COMMAND ROUTER] armed — post-merge cleanup + ChatOps command parsing active");
}
