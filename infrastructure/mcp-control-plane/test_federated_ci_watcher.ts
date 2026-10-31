/**
 * #199 — Federated CI failure watcher test suite (offline, deterministic).
 *
 * House style (see test_bridge_intake.ts): tsx script, hard asserts, exit
 * code = verdict. Covers: relevance policy, allowlist scope, dedupe gates,
 * hourly rate cap, emission contract (title/labels/body = the cross-repo
 * task normalizer), defaultCreateIssue 422 repo-label fallback (stubbed
 * fetch), defaultFetchJobs enrichment extraction, retry/backoff,
 * dead-letter, token fail-closed, disabled master switch, and normalizer
 * integration.
 */
import { globalEventNormalizer } from "./src/events/normalizer.js";
import {
  FederatedCiWatcherService,
  defaultCreateIssue,
  defaultFetchJobs,
  deriveFailureIssue,
  linkSubIssue,
  type CiFailureReport,
  type FederatedCiWatcherConfig,
  type IssueCreateFn,
  type JobsFetchFn,
} from "./src/events/federated_ci_watcher.js";

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

// Deterministic clock: manual advance, no real timers anywhere.
function makeClock(start = 1_700_000_000_000) {
  let now = start;
  return {
    now: () => now,
    advance: (ms: number) => {
      now += ms;
    },
  };
}
const NO_SCHEDULE = (fn: () => void) => {
  void fn;
  return undefined;
}; // never auto-run; tests drive tick()

function baseConfig(overrides: Partial<FederatedCiWatcherConfig> = {}): FederatedCiWatcherConfig {
  return {
    enabled: true,
    reportRepo: "Supremeai-bd/supremeai-open",
    repos: [],
    maxIssuesPerHour: 6,
    dedupeTtlMs: 24 * 60 * 60 * 1000,
    maxAttempts: 3,
    token: "test-token",
    ...overrides,
  };
}

/** Canonical workflow_run.completed(failure) webhook payload. */
function failurePayload(overrides: Record<string, any> = {}): Record<string, any> {
  const { workflow_run: runOverrides, ...topOverrides } = overrides;
  return {
    action: "completed",
    repository: { full_name: "Supremeai-bd/supremeai-api" },
    sender: { login: "some-actor" },
    workflow_run: {
      id: 4242,
      name: "CI",
      path: ".github/workflows/ci.yml",
      run_attempt: 1,
      conclusion: "failure",
      event: "push",
      head_branch: "main",
      head_sha: "a".repeat(40),
      html_url: "https://github.com/Supremeai-bd/supremeai-api/actions/runs/4242",
      ...(runOverrides ?? {}),
    },
    ...topOverrides,
  };
}

function normalizedGithub(payload: Record<string, any>, deliveryId = "d-1") {
  return globalEventNormalizer.normalizeGitHubEvent("workflow_run", payload, deliveryId);
}

const okIssueCreate: IssueCreateFn = async () => ({ ok: true, status: 201, issueUrl: "https://github.com/Supremeai-bd/supremeai-open/issues/999" });
const noJobs: JobsFetchFn = async () => ({ ok: true, status: 200, failedJobs: [] });

// ── 1. Relevance policy ───────────────────────────────────────────────────────
section("Relevance policy (decide)");
{
  const svc = new FederatedCiWatcherService(baseConfig(), { now: makeClock().now, schedule: NO_SCHEDULE });

  const d1 = svc.decide(normalizedGithub(failurePayload()));
  check("accepts workflow_run.completed(failure)", d1.accept && d1.eventKey === "ci-failure:Supremeai-bd/supremeai-api:CI:4242:1", JSON.stringify(d1));

  const d2 = svc.decide(globalEventNormalizer.normalizeGitHubEvent("push", failurePayload()));
  check("rejects non-workflow_run event", !d2.accept && d2.reason.includes("unsupported event"));

  const d3 = svc.decide(normalizedGithub({ ...failurePayload(), action: "requested" }));
  check("rejects non-completed action", !d3.accept && d3.reason.includes("unsupported action"));

  const d4 = svc.decide(normalizedGithub(failurePayload({ workflow_run: { id: 1, name: "CI", conclusion: "success", run_attempt: 1 } })));
  check("rejects conclusion=success", !d4.accept && d4.reason.includes("conclusion not watched"));

  const d5 = svc.decide(normalizedGithub({ ...failurePayload(), repository: undefined }));
  check("rejects missing repository identity", !d5.accept && d5.reason.includes("missing repository"));

  const d6 = svc.decide(normalizedGithub(failurePayload({ repository: { full_name: "Other-org/some-repo" } })));
  check("default same-org policy rejects foreign org", !d6.accept && d6.reason.includes("not in federation scope"));

  const d7 = svc.decide(normalizedGithub(failurePayload({ workflow_run: { id: 0, name: "CI", conclusion: "failure" } })));
  check("rejects missing run id", !d7.accept && d7.reason.includes("run id"));

  const d8 = svc.decide({ source: "cloudflare", type: "ping_failed", severity: "CRITICAL", message: "x", payload: {}, timestamp: "t" });
  check("rejects non-github source", !d8.accept && d8.reason.includes("non-github"));
}

// ── 2. Explicit allowlist ─────────────────────────────────────────────────────
section("Explicit allowlist scope");
{
  const svc = new FederatedCiWatcherService(baseConfig({ repos: ["Supremeai-bd/supremeai-api"] }), { now: makeClock().now, schedule: NO_SCHEDULE });
  check("explicit allowlist accepts listed repo (case-insensitive)", svc.isFederatedRepo("supremeai-bd/SUPREMEAI-API"));
  check("explicit allowlist rejects same-org unlisted repo", !svc.isFederatedRepo("Supremeai-bd/supremeai-open"));
}

// ── 3. Dedupe gates ───────────────────────────────────────────────────────────
section("Dedupe (deliveryId + eventKey with TTL)");
{
  const clock = makeClock();
  const created: any[] = [];
  const svc = new FederatedCiWatcherService(baseConfig(), {
    now: clock.now,
    schedule: NO_SCHEDULE,
    createIssue: async (req) => {
      created.push(req);
      return { ok: true, status: 201 };
    },
    fetchJobs: noJobs,
  });

  svc.handle(normalizedGithub(failurePayload(), "delivery-A"));
  svc.handle(normalizedGithub(failurePayload(), "delivery-B")); // same eventKey, different delivery → collapsed
  await svc.tick();
  check("eventKey dedupe collapses redeliveries", created.length === 1, `created=${created.length}`);

  clock.advance(25 * 60 * 60 * 1000); // past TTL → the same refailure may report again
  svc.handle(normalizedGithub(failurePayload(), "delivery-C"));
  await svc.tick();
  check("post-TTL refailure re-reports", created.length === 2, `created=${created.length}`);
}

// ── 4. Hourly rate cap (fresh service: no prior emissions) ────────────────────
section("Hourly rate cap (rolling window)");
{
  const clock = makeClock();
  const created: any[] = [];
  const svc = new FederatedCiWatcherService(baseConfig(), {
    now: clock.now,
    schedule: NO_SCHEDULE,
    createIssue: async (req) => {
      created.push(req);
      return { ok: true, status: 201 };
    },
    fetchJobs: noJobs,
  });
  // 6 distinct failures within one rolling hour → all emitted.
  for (let i = 0; i < 6; i++) {
    clock.advance(60_000);
    const p = failurePayload({
      workflow_run: { id: 5000 + i, name: "CI", conclusion: "failure", run_attempt: 1, head_branch: "main", head_sha: "b".repeat(40), html_url: `https://github.com/x/actions/runs/${5000 + i}` },
    });
    svc.handle(normalizedGithub(p, `delivery-cap-${i}`));
  }
  await svc.tick();
  check("cap allows exactly maxIssuesPerHour within the window", created.length === 6, `created=${created.length}`);

  // 7th failure still inside the window → dropped loudly.
  clock.advance(60_000);
  svc.handle(normalizedGithub(failurePayload({ workflow_run: { id: 9999, name: "CI", conclusion: "failure", run_attempt: 1 } }), "delivery-over-cap"));
  await svc.tick();
  check("over-cap report dropped (not emitted)", created.length === 6, `created=${created.length}`);

  // Window slides past the hour → cap resets.
  clock.advance(61 * 60_000);
  svc.handle(normalizedGithub(failurePayload({ workflow_run: { id: 10_000, name: "CI", conclusion: "failure", run_attempt: 1 } }), "delivery-post-window"));
  await svc.tick();
  check("cap resets after the rolling window slides", created.length === 7, `created=${created.length}`);
}

// ── 5. Emission contract ──────────────────────────────────────────────────────
section("Emission contract (title, labels, body = cross-repo task normalizer)");
{
  const clock = makeClock();
  let captured: any;
  const svc = new FederatedCiWatcherService(baseConfig(), {
    now: clock.now,
    schedule: NO_SCHEDULE,
    createIssue: async (req) => {
      captured = req;
      return { ok: true, status: 201 };
    },
    fetchJobs: async () => ({
      ok: true,
      status: 200,
      failedJobs: [{ name: "build", steps: ["npm run typecheck"], url: "https://github.com/x/job/1" }],
    }),
  });
  svc.handle(normalizedGithub(failurePayload(), "d-emission"));
  await svc.tick();

  check("issue opened", !!captured);
  check("repo = reportRepo", captured.repo === "Supremeai-bd/supremeai-open");
  check("title exact format per #199", captured.title === "fix(ci): workflow failure in Supremeai-bd/supremeai-api (CI #4242)", captured.title);
  check("labels carry core set + repo:<slug>", JSON.stringify(captured.labels) === JSON.stringify(["P1-high", "handoff:coder", "area:ci", "repo:supremeai-api"]), JSON.stringify(captured.labels));
  check("body contains run URL", captured.body.includes("https://github.com/Supremeai-bd/supremeai-api/actions/runs/4242"));
  check("body contains head SHA anchor", captured.body.includes("a".repeat(40)));
  check("body contains failed job + step", captured.body.includes("**build**") && captured.body.includes("`npm run typecheck`"));
  check("body is the standardized task contract", captured.body.includes("Primary Group") && captured.body.includes("3-Tier Verification Contract"));
  check("body carries verification commands", captured.body.includes("boundary_sanitization_guard.py --check") && captured.body.includes("--verify-only"));

  // Degraded enrichment path: jobs fetch fails → report still emitted with a note.
  let emitted = false;
  const svcDegrade = new FederatedCiWatcherService(baseConfig(), {
    now: clock.now,
    schedule: NO_SCHEDULE,
    createIssue: async (req) => {
      emitted = req.body.includes("Job-level details unavailable");
      return { ok: true, status: 201 };
    },
    fetchJobs: async () => ({ ok: false, status: 503, failedJobs: [] }),
  });
  svcDegrade.handle(normalizedGithub(failurePayload(), "d-degrade"));
  await svcDegrade.tick();
  check("emission survives jobs-API failure (degraded body note)", emitted);
}

// ── 6. defaultCreateIssue — 422 repo-label fallback (stubbed fetch) ───────────
section("defaultCreateIssue: 422 fallback + token fail-closed (stubbed fetch)");
{
  const calls: any[] = [];
  const origFetch = globalThis.fetch;
  globalThis.fetch = (async (_url: any, init: any) => {
    const parsed = JSON.parse(init.body);
    calls.push(parsed);
    if (parsed.labels.includes("repo:supremeai-api")) {
      return new Response("Label does not exist", { status: 422 });
    }
    return new Response(JSON.stringify({ html_url: "https://github.com/Supremeai-bd/supremeai-open/issues/1", number: 1 }), { status: 201, headers: { "content-type": "application/json" } });
  }) as any;
  try {
    const res = await defaultCreateIssue(
      { repo: "Supremeai-bd/supremeai-open", title: "t", body: "b", labels: ["P1-high", "handoff:coder", "area:ci", "repo:supremeai-api"] },
      "tok",
    );
    check("two HTTP calls (422 then fallback)", calls.length === 2, `calls=${calls.length}`);
    check("second call dropped the repo:<slug> label", Array.isArray(calls[1]?.labels) && !calls[1].labels.some((l: string) => l.startsWith("repo:")));
    check("fallback result ok", res.ok && res.status === 201);
    check("issueUrl and issueNumber captured", res.issueNumber === 1 && res.issueUrl === "https://github.com/Supremeai-bd/supremeai-open/issues/1");

    const noToken = await defaultCreateIssue({ repo: "r/x", title: "t", body: "b", labels: ["a"] }, undefined);
    check("missing token → fail-closed (status 0, not ok)", !noToken.ok && noToken.status === 0);
  } finally {
    globalThis.fetch = origFetch;
  }
}

// ── 6b. linkSubIssue — attach as sub-issue under CI Failure Hub #761 ──────────
section("linkSubIssue: link under anchor hub (stubbed fetch)");
{
  const origFetch = globalThis.fetch;
  globalThis.fetch = (async (url: any) => {
    if (String(url).endsWith("/issues/100")) {
      return new Response(JSON.stringify({ id: 555001, number: 100 }), { status: 200, headers: { "content-type": "application/json" } });
    }
    if (String(url).endsWith("/sub-issues")) {
      return new Response(JSON.stringify({ success: true }), { status: 201 });
    }
    return new Response("Not found", { status: 404 });
  }) as any;
  try {
    const linked = await linkSubIssue(100, "Supremeai-bd/supremeai-open", "tok");
    check("linkSubIssue succeeds with 201", linked === true);

    const noTok = await linkSubIssue(100, "Supremeai-bd/supremeai-open", undefined);
    check("linkSubIssue returns false without token", noTok === false);
  } finally {
    globalThis.fetch = origFetch;
  }
}

// ── 7. defaultFetchJobs — enrichment extraction (stubbed fetch) ────────────────
section("defaultFetchJobs: failed-job/step extraction (stubbed fetch)");
{
  const origFetch = globalThis.fetch;
  globalThis.fetch = (async () =>
    new Response(
      JSON.stringify({
        jobs: [
          { name: "build", conclusion: "failure", html_url: "https://github.com/x/job/1", steps: [{ name: "checkout", conclusion: "success" }, { name: "typecheck", conclusion: "failure" }] },
          { name: "lint", conclusion: "success", html_url: "https://github.com/x/job/2", steps: [] },
          { name: "deploy", conclusion: null, html_url: "https://github.com/x/job/3", steps: [] },
        ],
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    )) as any;
  try {
    const res = await defaultFetchJobs("Supremeai-bd/supremeai-api", 4242, "tok");
    check("only failure jobs extracted", res.ok && res.failedJobs.length === 1 && res.failedJobs[0].name === "build", JSON.stringify(res.failedJobs));
    check("failed step extracted", res.failedJobs[0].steps.length === 1 && res.failedJobs[0].steps[0] === "typecheck");
  } finally {
    globalThis.fetch = origFetch;
  }
}

// ── 8. Retry / backoff / dead-letter ──────────────────────────────────────────
section("Retry, backoff, dead-letter");
{
  const clock = makeClock();
  let calls = 0;
  const svc = new FederatedCiWatcherService(baseConfig({ maxAttempts: 2 }), {
    now: clock.now,
    schedule: NO_SCHEDULE,
    createIssue: async () => {
      calls += 1;
      return { ok: false, status: 500 };
    },
    fetchJobs: noJobs,
  });
  svc.handle(normalizedGithub(failurePayload(), "d-retry"));
  await svc.tick();
  check("attempt 1 made", calls === 1);
  clock.advance(6_000); // past 5s backoff
  await svc.tick();
  check("attempt 2 after backoff", calls === 2);
  clock.advance(60_000);
  await svc.tick();
  check("dead-letter stops retries", calls === 2 && svc.getStatus().dead === 1, JSON.stringify(svc.getStatus()));
}

// ── 9. Token fail-closed (service level) + disabled switch ────────────────────
section("Token fail-closed (service level) + disabled master switch");
{
  const svcNoToken = new FederatedCiWatcherService(baseConfig({ token: undefined, maxAttempts: 1 }), {
    now: makeClock().now,
    schedule: NO_SCHEDULE,
    createIssue: async () => ({ ok: true, status: 201 }),
    fetchJobs: noJobs,
  });
  svcNoToken.handle(normalizedGithub(failurePayload(), "d-notoken"));
  await svcNoToken.tick();
  check("missing token → fail-closed dead-letter (no silent success)", svcNoToken.getStatus().dead === 1, JSON.stringify(svcNoToken.getStatus()));

  const svcDisabled = new FederatedCiWatcherService(baseConfig({ enabled: false }), {
    now: makeClock().now,
    schedule: NO_SCHEDULE,
    createIssue: okIssueCreate,
    fetchJobs: noJobs,
  });
  svcDisabled.handle(normalizedGithub(failurePayload(), "d-disabled"));
  await svcDisabled.tick();
  check("disabled watcher is fully inert", svcDisabled.getStatus().pending === 0 && svcDisabled.getStatus().done === 0 && svcDisabled.getStatus().dead === 0);
}

// ── 10. Normalizer integration + derivation contract ──────────────────────────
section("Normalizer integration + derivation contract");
{
  const report: CiFailureReport = {
    schema: "federated-ci-failure/v1",
    repo: "Supremeai-bd/supremeai-api",
    workflowName: "Release",
    workflowPath: ".github/workflows/release.yml",
    runId: 77,
    runAttempt: 3,
    runUrl: "https://github.com/Supremeai-bd/supremeai-api/actions/runs/77",
    headBranch: "release/v2",
    headSha: "c".repeat(40),
    conclusion: "failure",
    failedJobs: [],
    eventKey: "ci-failure:Supremeai-bd/supremeai-api:Release:77:3",  // gitleaks:allow
    reportedAt: "2026-10-16T00:00:00.000Z",
  };
  const issue = deriveFailureIssue(report);
  check("deriveFailureIssue title matches #199 format", issue.title === "fix(ci): workflow failure in Supremeai-bd/supremeai-api (Release #77)", issue.title);
  check("schema envelope id carried", report.schema === "federated-ci-failure/v1");
  check("eventKey composite includes attempt", report.eventKey.endsWith(":77:3"));

  // End-to-end through the real normalizer (as the webhook route feeds it).
  const normalized = globalEventNormalizer.normalizeGitHubEvent("workflow_run", failurePayload(), "d-e2e");
  check("normalized event rides source=github type=workflow_run", normalized.source === "github" && normalized.type === "workflow_run" && normalized.deliveryId === "d-e2e");
}

console.log(`\n${failures === 0 ? "✅ ALL CHECKS PASSED" : `❌ ${failures} CHECK(S) FAILED`}`);
process.exit(failures === 0 ? 0 : 1);
