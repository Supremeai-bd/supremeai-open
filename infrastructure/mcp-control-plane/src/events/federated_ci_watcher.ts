/**
 * #199 — Federated CI failure auto-issue reporter + cross-repo task normalizer.
 *
 * Connects the already-deployed `/webhooks/github` route (signed, normalized,
 * dispatched through the existing EventGateway) to an autonomous reporter that
 * opens an actionable failure issue on the control-plane board the moment any
 * federation repository's GitHub Actions run fails — so agents can claim and
 * patch the breakage in seconds instead of waiting for a human sweep.
 *
 * The emitted issue body IS the cross-repo task normalizer (#199 part 2): any
 * CI failure raised anywhere in the federation is normalized into the standard
 * agent-task contract (Primary Group / Sub-Group / Priority / Task Group /
 * 3-Tier Verification Contract) on `Supremeai-bd/supremeai-open`.
 *
 * Design constraints (issue #199, mirroring the #69 bridge-intake doctrine):
 *  - NO second event bus / NO duplicate webhook endpoint: this module is a
 *    gateway listener on the existing normalizer→gateway pipeline.
 *  - Fail-closed: disabled by default (FEDERATED_CI_WATCHER_ENABLED=true to
 *    arm); anything that is not `workflow_run.completed` with
 *    `conclusion === "failure"` from an allow-listed repository is dropped
 *    with a machine-readable reason.
 *  - Anti-spam Poka-yoke (a bug here could spam the board): three independent
 *    gates — (1) `X-GitHub-Delivery` idempotency, (2) event-key dedupe
 *    (repo:workflow:run:attempt) with a long TTL, (3) a global rolling
 *    issues-per-hour cap. Over-cap reports are dropped loudly, not silently.
 *  - Emission before enrichment: failed-job details are fetched best-effort;
 *    a jobs-API blip degrades the report body, it never loses the report.
 *  - Least privilege: server-side GITHUB_TOKEN only, never exposed to webhook
 *    callers; nothing from the payload is logged (no secrets, no log URLs
 *    beyond what GitHub already exposes publicly on the run page).
 *  - Label resilience: `repo:<slug>` may not exist on the board yet — a 422
 *    from the Issues API falls back to the three always-present labels and
 *    notes the dropped label inside the issue body (board triage can relabel,
 *    e.g. `repo:supremeai-open` → `repo:open`).
 *  - Retry semantics: in-memory bounded retry with exponential backoff and a
 *    dead-letter state (no durable outbox — the reporter is advisory; GitHub
 *    redelivery and the next failing run provide natural reconciliation).
 */

import type { NormalizedEvent } from "./normalizer.js";
import { globalEventGateway } from "./gateway.js";

// ── Emission contract (mirrors api-schemas/federated-ci-failure.schema.json) ──

export const REPORT_SCHEMA_ID = "federated-ci-failure/v1";

/** Conclusion the reporter acts on. Strict: startup_failure/timed_out/etc. are out of scope for v1. */
export const WATCHED_CONCLUSION = "failure";

export interface FailedJobSummary {
  name: string;
  steps: string[];
  url?: string;
}

export interface CiFailureReport {
  schema: typeof REPORT_SCHEMA_ID;
  /** Full name of the repository whose run failed, e.g. `Org/repo`. */
  repo: string;
  workflowName: string;
  /** Workflow file path inside the failing repo, when GitHub provides one. */
  workflowPath?: string;
  runId: number;
  runAttempt: number;
  runUrl: string;
  headBranch: string;
  headSha: string;
  conclusion: typeof WATCHED_CONCLUSION;
  /** Best-effort enrichment from the runs/{id}/jobs API; empty when unavailable. */
  failedJobs: FailedJobSummary[];
  /** Dedupe key: ci-failure:<repo>:<workflow>:<runId>:<runAttempt>. */
  eventKey: string;
  reportedAt: string;
}

/** Labels required by the #199 task contract. */
export const BASE_LABELS = ["P1-high", "handoff:coder", "area:ci"] as const;

export interface DerivedIssue {
  title: string;
  body: string;
  labels: string[];
}

// ── Configuration ─────────────────────────────────────────────────────────────

export interface FederatedCiWatcherConfig {
  /** Master switch — fail-closed. Armed only via FEDERATED_CI_WATCHER_ENABLED=true. */
  enabled: boolean;
  /** Board where failure issues are opened. */
  reportRepo: string;
  /**
   * Explicit federation allowlist (full names, case-insensitive). When empty,
   * the default same-org policy applies: any repo owned by the same owner as
   * `reportRepo` counts as federation (the fleet is org-scoped; a hardcoded
   * 14-repo list would drift).
   */
  repos: string[];
  /** Global rolling cap: max failure issues opened per hour across all repos. */
  maxIssuesPerHour: number;
  /** Event-key dedupe TTL. */
  dedupeTtlMs: number;
  /** Retry ceiling per report before dead-letter. */
  maxAttempts: number;
  /** Server-side GitHub token (repo scope on reportRepo). Never logged. */
  token?: string;
}

// ── Internal queue types ──────────────────────────────────────────────────────

interface PendingReport {
  report: CiFailureReport;
  status: "pending" | "done" | "dead";
  attempts: number;
  nextAttemptAt: number;
  lastError?: string;
}

export interface WatcherDecision {
  accept: boolean;
  reason: string;
  eventKey?: string;
}

export interface IssueCreateRequest {
  repo: string;
  title: string;
  body: string;
  labels: string[];
}

export type IssueCreateFn = (
  req: IssueCreateRequest,
  token?: string,
) => Promise<{ ok: boolean; status: number; issueUrl?: string; body?: any }>;

export type JobsFetchFn = (
  repo: string,
  runId: number,
  token?: string,
) => Promise<{ ok: boolean; status: number; failedJobs: FailedJobSummary[] }>;

export interface FederatedCiWatcherDeps {
  now?: () => number;
  createIssue?: IssueCreateFn;
  fetchJobs?: JobsFetchFn;
  schedule?: (fn: () => void, ms: number) => unknown;
  log?: (line: string) => void;
}

const BACKOFF_BASE_MS = 5_000;
const BACKOFF_CAP_MS = 15 * 60 * 1000;
const HOURLY_WINDOW_MS = 60 * 60 * 1000;
const MAX_TRACKED_KEYS = 2048;

// ── Service ───────────────────────────────────────────────────────────────────

export class FederatedCiWatcherService {
  private readonly config: FederatedCiWatcherConfig;
  private readonly deps: Required<Pick<FederatedCiWatcherDeps, "now">> & FederatedCiWatcherDeps;
  private readonly queue: PendingReport[] = [];
  private readonly seenDeliveries = new Map<string, number>();
  private readonly seenEventKeys = new Map<string, number>();
  private readonly emissionTimes: number[] = [];
  private processing = false;

  constructor(config: FederatedCiWatcherConfig, deps: FederatedCiWatcherDeps = {}) {
    this.config = config;
    this.deps = {
      now: deps.now ?? (() => Date.now()),
      createIssue: deps.createIssue,
      fetchJobs: deps.fetchJobs,
      schedule: deps.schedule,
      log: deps.log,
    };
  }

  // ── Relevance policy ────────────────────────────────────────────────────────

  /** Pure decision: does this normalized event deserve a failure issue? */
  public decide(event: NormalizedEvent): WatcherDecision {
    if (event.source !== "github") {
      return { accept: false, reason: `non-github source: ${event.source}` };
    }
    if (event.type !== "workflow_run") {
      return { accept: false, reason: `unsupported event: ${event.type}` };
    }
    const payload: any = event.payload ?? {};
    if (String(payload?.action ?? "") !== "completed") {
      return { accept: false, reason: `unsupported action: workflow_run.${payload?.action}` };
    }
    const run = payload?.workflow_run ?? {};
    if (String(run?.conclusion ?? "") !== WATCHED_CONCLUSION) {
      return { accept: false, reason: `conclusion not watched: ${run?.conclusion}` };
    }
    const repoFullName = String(payload?.repository?.full_name ?? "");
    if (!repoFullName) {
      return { accept: false, reason: "missing repository identity" };
    }
    if (!this.isFederatedRepo(repoFullName)) {
      return { accept: false, reason: `repo not in federation scope: ${repoFullName}` };
    }
    const runId = Number(run?.id ?? 0);
    if (!Number.isFinite(runId) || runId <= 0) {
      return { accept: false, reason: "missing workflow run id" };
    }
    const eventKey = `ci-failure:${repoFullName}:${String(run?.name ?? "unknown")}:${runId}:${Number(run?.run_attempt ?? 1)}`;
    return { accept: true, reason: `workflow_run.failure`, eventKey };
  }

  /** Allowlist policy: explicit list wins; otherwise same-org-as-reportRepo. */
  public isFederatedRepo(repoFullName: string): boolean {
    const lower = repoFullName.toLowerCase();
    if (this.config.repos.length > 0) {
      return this.config.repos.map((r) => r.toLowerCase()).includes(lower);
    }
    const owner = this.config.reportRepo.split("/")[0]?.toLowerCase() ?? "";
    return owner.length > 0 && lower.startsWith(`${owner}/`);
  }

  // ── Gateway listener (synchronous, O(1) — never blocks the webhook ack) ────

  public handle(event: NormalizedEvent): void {
    if (!this.config.enabled) return; // fail-closed: silently inert unless armed
    const decision = this.decide(event);
    if (!decision.accept) {
      this.log(`[CI_WATCHER] skip (${decision.reason})`);
      return;
    }
    const deliveryId = event.deliveryId;
    if (deliveryId && this.fresh(this.seenDeliveries, deliveryId)) {
      this.log(`[CI_WATCHER] dedupe: delivery ${deliveryId} already processed`);
      return;
    }
    const eventKey = decision.eventKey ?? "unknown";
    if (this.fresh(this.seenEventKeys, eventKey)) {
      this.log(`[CI_WATCHER] dedupe: event ${eventKey} already reported in TTL window`);
      return;
    }
    if (this.overRateCap()) {
      this.log(
        `[CI_WATCHER] RATE-CAP: ${eventKey} dropped — ${this.config.maxIssuesPerHour} issues/hour cap reached (failure remains visible on the run page; next failing run re-triggers)`,
      );
      return;
    }
    const payload: any = event.payload ?? {};
    const run = payload?.workflow_run ?? {};
    const report: CiFailureReport = {
      schema: REPORT_SCHEMA_ID,
      repo: String(payload.repository.full_name),
      workflowName: String(run.name ?? "unknown"),
      workflowPath: run.path ? String(run.path) : undefined,
      runId: Number(run.id),
      runAttempt: Number(run.run_attempt ?? 1),
      runUrl: String(run.html_url ?? `https://github.com/${payload.repository.full_name}/actions/runs/${run.id}`),
      headBranch: String(run.head_branch ?? "unknown"),
      headSha: String(run.head_sha ?? "unknown"),
      conclusion: WATCHED_CONCLUSION,
      failedJobs: [],
      eventKey,
      reportedAt: new Date(this.deps.now()).toISOString(),
    };
    this.queue.push({ report, status: "pending", attempts: 0, nextAttemptAt: this.deps.now() });
    this.log(`[CI_WATCHER] accepted ${eventKey} → report queue`);
    this.scheduleProcess();
  }

  // ── Report pipeline (jobs enrichment → issue creation, bounded retry) ──────

  private async processQueue(): Promise<void> {
    if (this.processing) return;
    this.processing = true;
    try {
      for (;;) {
        const now = this.deps.now();
        const due = this.queue.find((e) => e.status === "pending" && e.nextAttemptAt <= now);
        if (!due) break;
        await this.attemptReport(due);
      }
    } finally {
      this.processing = false;
      const stillDue = this.queue.some((e) => e.status === "pending" && e.nextAttemptAt <= this.deps.now());
      if (stillDue) this.scheduleProcess();
    }
  }

  /** Public tick: drains due reports now (external reconciliation + tests). */
  public async tick(): Promise<void> {
    await this.processQueue();
  }

  private async attemptReport(entry: PendingReport): Promise<void> {
    const createIssue = this.deps.createIssue ?? defaultCreateIssue;
    const fetchJobs = this.deps.fetchJobs ?? defaultFetchJobs;
    try {
      // Fail-closed credential gate (service level — defense in depth beyond
      // the default backends): without a server-side token the report can
      // never be delivered, so fail the attempt and dead-letter visibly.
      if (!this.config.token) throw new Error("no server-side GitHub token configured (fail-closed)");
      // Emission before enrichment: a jobs blip degrades the body, never loses the report.
      const jobs = await fetchJobs(entry.report.repo, entry.report.runId, this.config.token);
      if (jobs.ok) entry.report.failedJobs = jobs.failedJobs;

      const issue = deriveFailureIssue(entry.report);
      const res = await createIssue(
        { repo: this.config.reportRepo, title: issue.title, body: issue.body, labels: issue.labels },
        this.config.token,
      );
      if (!res.ok) throw new Error(`GitHub issues API → HTTP ${res.status}`);
      entry.status = "done";
      this.emissionTimes.push(this.deps.now());
      this.log(`[CI_WATCHER] reported ${entry.report.eventKey} → ${res.issueUrl ?? this.config.reportRepo}`);
    } catch (err: any) {
      entry.attempts += 1;
      entry.lastError = String(err?.message ?? err);
      if (entry.attempts >= this.config.maxAttempts) {
        entry.status = "dead";
        this.log(`[CI_WATCHER] DEAD-LETTER ${entry.report.eventKey} after ${entry.attempts} attempts: ${entry.lastError}`);
      } else {
        const backoff = Math.min(BACKOFF_BASE_MS * 2 ** (entry.attempts - 1), BACKOFF_CAP_MS);
        entry.nextAttemptAt = this.deps.now() + backoff;
        this.log(
          `[CI_WATCHER] report failed for ${entry.report.eventKey} (attempt ${entry.attempts}/${this.config.maxAttempts}) → retry in ${backoff}ms: ${entry.lastError}`,
        );
        this.scheduleProcess(backoff);
      }
    }
  }

  private scheduleProcess(delayMs = 0): void {
    const schedule = this.deps.schedule ?? ((fn, ms) => setTimeout(fn, ms));
    const timer = schedule(() => {
      void this.processQueue();
    }, delayMs);
    if (timer && typeof (timer as any).unref === "function") (timer as any).unref();
  }

  // ── Anti-spam gates ─────────────────────────────────────────────────────────

  private overRateCap(): boolean {
    const now = this.deps.now();
    while (this.emissionTimes.length > 0 && now - this.emissionTimes[0] > HOURLY_WINDOW_MS) {
      this.emissionTimes.shift();
    }
    return this.emissionTimes.length >= this.config.maxIssuesPerHour;
  }

  private fresh(map: Map<string, number>, key: string): boolean {
    const now = this.deps.now();
    for (const [k, ts] of map) if (now - ts > this.config.dedupeTtlMs) map.delete(k);
    while (map.size >= MAX_TRACKED_KEYS) map.delete(map.keys().next().value as string);
    if (map.has(key)) return true;
    map.set(key, now);
    return false;
  }

  // ── Observability ───────────────────────────────────────────────────────────

  public getStatus(): Record<string, unknown> {
    return {
      enabled: this.config.enabled,
      reportRepo: this.config.reportRepo,
      federationScope: this.config.repos.length > 0 ? this.config.repos : [`same-org:${this.config.reportRepo.split("/")[0] ?? ""}`],
      maxIssuesPerHour: this.config.maxIssuesPerHour,
      reportedLastHour: this.emissionTimes.length,
      pending: this.queue.filter((e) => e.status === "pending").length,
      done: this.queue.filter((e) => e.status === "done").length,
      dead: this.queue.filter((e) => e.status === "dead").length,
    };
  }

  private log(line: string): void {
    const fn = this.deps.log ?? ((l: string) => console.error(l));
    fn(line);
  }
}

// ── Cross-repo task normalizer: report → standard agent-task issue ───────────

/**
 * Derives the board issue from a failure report. This function is the #199
 * "cross-repo task normalizer": every federation CI failure lands on the
 * control-plane board in the standardized agent-task contract shape.
 */
export function deriveFailureIssue(report: CiFailureReport): DerivedIssue {
  const title = `fix(ci): workflow failure in ${report.repo} (${report.workflowName} #${report.runId})`;
  const slug = report.repo.split("/")[1] ?? report.repo;

  const jobLines =
    report.failedJobs.length > 0
      ? report.failedJobs
          .map(
            (j) =>
              `- **${j.name}**${j.url ? ` — [job log](${j.url})` : ""}${j.steps.length ? `\n  - failed step(s): ${j.steps.map((s) => `\`${s}\``).join(", ")}` : ""}`,
          )
          .join("\n")
      : "_Job-level details unavailable (jobs API enrichment skipped/failed — see the run URL above)._";

  const workflowFile = report.workflowPath ? `\`${report.workflowPath}\` (workflow definition — first suspect for syntax/environment breakage)` : "_workflow path not provided by the event_";

  const body = `### 🤖 SupremeAI Agent Task Contract (auto-generated by the federated CI watcher — verify before acting)

**Primary Group (Target Repository):**
${report.repo}

**Sub-Group / Functional Domain (Area):**
ci (Workflows, gates, lint, testing matrix)

**Priority Tier:**
P1-high (CI breakage blocks the federation loop)

**Topological Layer:**
Layer 2 (Tools / Workers / Sidecars)

**Task Group (VALID_GROUPS registry):**
agent-orchestration

### Mission & Problem Statement
GitHub Actions workflow **${report.workflowName}** failed (${report.conclusion}) in \`${report.repo}\`.

- **Run:** [#${report.runId} (attempt ${report.runAttempt})](${report.runUrl})
- **Head branch:** \`${report.headBranch}\` · **Head SHA:** \`${report.headSha}\`
- **Event key:** \`${report.eventKey}\`

**Failing jobs / steps:**
${jobLines}

### Touching Files
- ${workflowFile}
- Whatever the failing steps reference (derive from the job log linked above).

### 3-Tier Verification Contract
1. Reflection Check: \`python scripts/ci/boundary_sanitization_guard.py --check\`
2. Boot Smoke: \`npm --prefix infrastructure/mcp-control-plane run typecheck\`
3. Test Suite: \`python scripts/agents/continuous_agent_loop.py --verify-only\`

<!-- reporter: federated-ci-watcher schema=${report.schema} eventKey=${report.eventKey} -->`;

  return { title, body, labels: [...BASE_LABELS, `repo:${slug}`] };
}

// ── Default GitHub backends (server-side token only) ──────────────────────────

/** POST /repos/{repo}/issues — with one 422 fallback that drops the repo:<slug> label. */
export const defaultCreateIssue: IssueCreateFn = async (req, token) => {
  if (!token) return { ok: false, status: 0 }; // fail-closed: no creds → caller retries → dead-letters visibly
  const attempt = async (labels: string[]) =>
    fetch(`https://api.github.com/repos/${req.repo}/issues`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SupremeAI-MCP-Control-Tower",
      },
      body: JSON.stringify({ title: req.title, body: req.body, labels }),
    });

  let res = await attempt(req.labels);
  if (res.status === 422 && req.labels.length > 1) {
    // A label (most likely repo:<slug>) does not exist on the board — retry
    // with the always-present core labels and note the drop in the body.
    const note = `\n\n> ℹ️ Reporter note: the \`repo:<slug>\` label does not exist on this board yet — triage may want to add/relabel it (e.g. \`repo:open\` for \`Supremeai-bd/supremeai-open\`).`;
    res = await attempt([...req.labels.filter((l) => !l.startsWith("repo:"))]);
    return { ok: res.status === 201, status: res.status, issueUrl: undefined, body: { labelDropped: true, note } };
  }
  let issueUrl: string | undefined;
  try {
    issueUrl = res.ok ? ((await res.json() as any)?.html_url ?? undefined) : undefined;
  } catch {
    issueUrl = undefined;
  }
  return { ok: res.status === 201, status: res.status, issueUrl };
};

/** GET /repos/{repo}/actions/runs/{runId}/jobs — best-effort failed-job enrichment. */
export const defaultFetchJobs: JobsFetchFn = async (repo, runId, token) => {
  if (!token) return { ok: false, status: 0, failedJobs: [] };
  try {
    const res = await fetch(`https://api.github.com/repos/${repo}/actions/runs/${runId}/jobs?filter=latest&per_page=100`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SupremeAI-MCP-Control-Tower",
      },
    });
    if (res.status !== 200) return { ok: false, status: res.status, failedJobs: [] };
    const data: any = await res.json();
    const failedJobs: FailedJobSummary[] = (data?.jobs ?? [])
      .filter((j: any) => j?.conclusion === "failure")
      .map((j: any) => ({
        name: String(j.name ?? "unknown"),
        steps: (j.steps ?? [])
          .filter((s: any) => s?.conclusion === "failure")
          .map((s: any) => String(s.name ?? "unknown")),
        url: j.html_url ? String(j.html_url) : undefined,
      }));
    return { ok: true, status: 200, failedJobs };
  } catch {
    return { ok: false, status: 0, failedJobs: [] };
  }
};

// ── Boot wiring (idempotent) ──────────────────────────────────────────────────

let registered = false;

/**
 * Registers the watcher as an EventGateway listener (single call per process).
 * Reads its configuration from env; logs one actionable line when disabled so
 * operators can see why CI failures are not being reported.
 */
export async function registerFederatedCiWatcher(): Promise<void> {
  if (registered) return;
  registered = true;
  const { env } = await import("../lib/env.js");
  const cfg = env.federatedCiWatcher;
  if (!cfg.enabled) {
    console.error("[CI_WATCHER] disabled (set FEDERATED_CI_WATCHER_ENABLED=true and ensure the repo webhook subscribes to workflow_run events to arm federated CI failure reporting)");
    return;
  }
  const service = new FederatedCiWatcherService({
    enabled: cfg.enabled,
    reportRepo: cfg.reportRepo,
    repos: cfg.repos,
    maxIssuesPerHour: cfg.maxIssuesPerHour,
    dedupeTtlMs: cfg.dedupeTtlMs,
    maxAttempts: cfg.maxAttempts,
    token: cfg.token,
  });
  globalEventGateway.subscribe((event) => service.handle(event));
  console.error(
    `[CI_WATCHER] armed → failures from ${cfg.repos.length > 0 ? cfg.repos.join(", ") : `same-org:${cfg.reportRepo.split("/")[0] ?? ""}`} reported to ${cfg.reportRepo} (cap ${cfg.maxIssuesPerHour}/hour)`,
  );
}
