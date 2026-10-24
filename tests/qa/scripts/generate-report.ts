/**
 * generate-report.ts — Part 6 of the QA engine plan: QA report aggregator + RELEASE GATE.
 *
 * Input : a Playwright JSON reporter results file (default qa/results/results.json;
 *         override via `--results <path>`). The reporter shape is
 *         { suites: [ { title, suites?: [...], specs?: [ { title, ok?, tests?: [ { results?: [ { status } ] } ] } ] } ], stats? }.
 *         A flat array of { title, status } entries is also accepted.
 * Check  : checklist ids are matched from test titles (plan convention: titles
 *          start with the id, e.g. "G-01: ..."), joined against
 *          qa/checklist/{guest,customer,admin,security}.yaml for severity.
 * Output : markdown report (stdout, plus --out <path> when given).
 * Gate   : any failed P0/P1  -> verdict "STOP RELEASE",               exit 1
 *          failed P2 only    -> verdict "WARNING — human decides",    exit 0
 *          failed P3 only    -> verdict "LOG ONLY",                   exit 0
 *          nothing failed    -> verdict "PASS",                       exit 0
 *          (exit 1 is what blocks the deploy job in CI.)
 *
 * --self-test runs built-in fixture result sets (all-pass, P1-fail, P2-fail,
 * P3-fail) through the SAME aggregation + verdict code and prints PASS/FAIL
 * per fixture; exits non-zero if any fixture assertion fails.
 *
 * Runs under bun:  bun qa/scripts/generate-report.ts [--results <path>] [--out <path>] | --self-test
 */
import { readFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import YAML from "yaml";

// ── checklist loading ────────────────────────────────────────────────────────
const ROLE_FILES = [
  { file: "guest.yaml", label: "Guest" },
  { file: "customer.yaml", label: "Customer" },
  { file: "admin.yaml", label: "Admin" },
  { file: "security.yaml", label: "Security" },
] as const;

type Severity = "P0" | "P1" | "P2" | "P3";
type Item = { id: string; name: string; severity: Severity; role: string };
type Checklists = Map<string, Item>;

function loadChecklists(repoRoot: string): Checklists {
  const map: Checklists = new Map();
  for (const { file } of ROLE_FILES) {
    const items = YAML.parse(readFileSync(join(repoRoot, "qa", "checklist", file), "utf8")) as Array<
      Record<string, unknown>
    >;
    for (const i of items) {
      map.set(String(i.id), {
        id: String(i.id),
        name: String(i.name),
        severity: String(i.severity) as Severity,
        role: String(i.role),
      });
    }
  }
  return map;
}

// ── results parsing (Playwright JSON reporter shape, tolerant) ───────────────
type TestOutcome = { title: string; status: "passed" | "failed" | "skipped" | "unknown" };

function statusToOutcome(status: unknown): TestOutcome["status"] {
  if (status === "passed" || status === "expected") return "passed";
  if (status === "failed" || status === "timedOut" || status === "unexpected") return "failed";
  if (status === "skipped" || status === "fixtureSkipped") return "skipped";
  return "unknown";
}

function walkSuites(node: unknown, out: TestOutcome[]): void {
  if (!node || typeof node !== "object") return;
  const n = node as Record<string, unknown>;
  const suiteTitle = typeof n.title === "string" ? n.title : "";
  for (const spec of (n.specs as unknown[] | undefined) ?? []) {
    const s = spec as Record<string, unknown>;
    const title = typeof s.title === "string" ? s.title : "";
    let status: unknown = s.status;
    if (status === undefined && Array.isArray(s.tests)) {
      // playwright JSON reporter: spec.tests[].results[].status — worst result wins
      const results: unknown[] = [];
      for (const t of s.tests as Array<Record<string, unknown>>) {
        for (const r of (t.results as Array<Record<string, unknown>> | undefined) ?? []) {
          results.push(r.status);
        }
      }
      const order = ["failed", "timedOut", "unexpected", "interrupted", "skipped", "expected", "passed"];
      status = results.find((r) => order.includes(r as string));
      if (status === undefined && results.length > 0) status = results[0];
    }
    out.push({ title: `${suiteTitle} ${title}`.trim(), status: statusToOutcome(status) });
  }
  for (const child of (n.suites as unknown[] | undefined) ?? []) walkSuites(child, out);
}

export function parseResults(raw: unknown): TestOutcome[] {
  const out: TestOutcome[] = [];
  if (Array.isArray(raw)) {
    for (const entry of raw) {
      const e = entry as Record<string, unknown>;
      out.push({ title: String(e.title ?? ""), status: statusToOutcome(e.status) });
    }
    return out;
  }
  const root = raw as Record<string, unknown>;
  for (const suite of (root.suites as unknown[] | undefined) ?? []) walkSuites(suite, out);
  // fallback: specs at the root level
  for (const spec of (root.specs as unknown[] | undefined) ?? []) walkSuites({ specs: [spec] }, out);
  return out;
}

const QA_ID_RE = /\b(?:G|C|A|S)-\d{2}\b/;

export function extractQaId(title: string): string | null {
  const m = title.match(QA_ID_RE);
  return m ? m[0] : null;
}

// ── aggregation + verdict ────────────────────────────────────────────────────
export type Verdict = "PASS" | "STOP RELEASE" | "WARNING — human decides" | "LOG ONLY";

export type Aggregation = {
  roleStats: Map<string, { total: number; pass: number; fail: number; skipped: number }>;
  failuresBySeverity: Record<Severity, string[]>;
  unknownIds: string[];
  failedIds: string[];
  verdict: Verdict;
  exitCode: 0 | 1;
};

export function aggregate(
  outcomes: TestOutcome[],
  checklists: Checklists,
): Aggregation {
  const roleStats = new Map<string, { total: number; pass: number; fail: number; skipped: number }>();
  const failuresBySeverity: Record<Severity, string[]> = { P0: [], P1: [], P2: [], P3: [] };
  const unknownIds: string[] = [];
  const failedIds: string[] = [];

  for (const o of outcomes) {
    const id = extractQaId(o.title);
    const item = id ? checklists.get(id) : undefined;
    const label = id ?? "(no qa-id)";
    const role = item?.role ?? "unmapped";
    const stats = roleStats.get(role) ?? { total: 0, pass: 0, fail: 0, skipped: 0 };
    roleStats.set(role, stats);
    stats.total += 1;
    if (o.status === "passed") stats.pass += 1;
    else if (o.status === "failed") {
      stats.fail += 1;
      if (item) {
        failuresBySeverity[item.severity].push(`${id}: ${item.name}`);
        failedIds.push(id);
      } else if (id) unknownIds.push(id);
    } else stats.skipped += 1; // skipped/unknown (includes test.fixme)
  }

  let verdict: Verdict = "PASS";
  let exitCode: 0 | 1 = 0;
  if (failuresBySeverity.P0.length > 0 || failuresBySeverity.P1.length > 0) {
    verdict = "STOP RELEASE";
    exitCode = 1;
  } else if (failuresBySeverity.P2.length > 0) {
    verdict = "WARNING — human decides";
  } else if (failuresBySeverity.P3.length > 0) {
    verdict = "LOG ONLY";
  }

  return { roleStats, failuresBySeverity, unknownIds, failedIds, verdict, exitCode };
}

// ── markdown report ──────────────────────────────────────────────────────────
export function renderMarkdown(
  agg: Aggregation,
  opts: { commit?: string; environment?: string; date?: string },
): string {
  const now = opts.date ?? new Date().toISOString();
  const lines: string[] = [];
  lines.push("# SupremeAI QA Report");
  lines.push("");
  lines.push(`- Commit: ${opts.commit ?? process.env.GITHUB_SHA ?? "(local)"}`);
  lines.push(`- Environment: ${opts.environment ?? process.env.QA_BASE_URL ?? "local"}`);
  lines.push(`- Date: ${now}`);
  lines.push("");
  lines.push("| Role | Total | Pass | Fail | Skipped/Fixme | Score |");
  lines.push("|------|-------|------|------|---------------|-------|");
  let t = 0, p = 0, f = 0, s = 0;
  for (const [role, st] of agg.roleStats) {
    const score = st.total === 0 ? "—" : `${Math.round((st.pass / st.total) * 100)}%`;
    lines.push(`| ${role} | ${st.total} | ${st.pass} | ${st.fail} | ${st.skipped} | ${score} |`);
    t += st.total; p += st.pass; f += st.fail; s += st.skipped;
  }
  const score = t === 0 ? "—" : `${Math.round((p / t) * 100)}%`;
  lines.push(`| **TOTAL** | ${t} | ${p} | ${f} | ${s} | **${score}** |`);
  lines.push("");
  lines.push(`- P0 failures: ${agg.failuresBySeverity.P0.length}`);
  lines.push(`- P1 failures: ${agg.failuresBySeverity.P1.length}`);
  lines.push(`- P2 failures: ${agg.failuresBySeverity.P2.length}`);
  lines.push(`- P3 failures: ${agg.failuresBySeverity.P3.length}`);
  const allFailures = [...agg.failuresBySeverity.P0, ...agg.failuresBySeverity.P1, ...agg.failuresBySeverity.P2, ...agg.failuresBySeverity.P3];
  if (allFailures.length > 0) {
    lines.push("");
    lines.push("### Failures");
    for (const fl of allFailures) lines.push(`- ${fl}`);
  }
  if (agg.unknownIds.length > 0) {
    lines.push("");
    lines.push(`### Results without a known checklist id: ${agg.unknownIds.join(", ")}`);
  }
  lines.push("");
  lines.push(`## RELEASE DECISION: ${agg.verdict}`);
  if (agg.verdict === "STOP RELEASE") {
    lines.push(`Reason: ${agg.failuresBySeverity.P0.length + agg.failuresBySeverity.P1.length} P0/P1 failure(s) (${[...agg.failuresBySeverity.P0, ...agg.failuresBySeverity.P1].join("; ")})`);
  } else if (agg.verdict === "WARNING — human decides") {
    lines.push(`Reason: ${agg.failuresBySeverity.P2.length} P2 failure(s) — a human signs off or defers.`);
  } else if (agg.verdict === "LOG ONLY") {
    lines.push("Reason: only P3 (cosmetic) failures — log and continue.");
  }
  return lines.join("\n");
}

// ── self-test ────────────────────────────────────────────────────────────────
function spec(id: string, status: unknown): Record<string, unknown> {
  return { title: `${id}: fixture item`, tests: [{ results: [{ status }] }] };
}

function fixtureSuite(specs: Array<Record<string, unknown>>): unknown {
  return {
    suites: [
      { title: "qa-fixture", suites: [{ title: "fixture", specs }], specs: [] },
    ],
  };
}

export function runSelfTest(checklists: Checklists): boolean {
  const fixtures: Array<{ name: string; results: unknown; wantVerdict: Verdict; wantExit: 0 | 1 }> = [
    {
      name: "all-pass",
      results: fixtureSuite([spec("G-01", "passed"), spec("C-04", "passed"), spec("A-04", "passed"), spec("S-01", "passed"), spec("G-06", "skipped")]),
      wantVerdict: "PASS",
      wantExit: 0,
    },
    {
      name: "p1-fail",
      results: fixtureSuite([spec("G-01", "passed"), spec("C-04", "failed"), spec("S-01", "passed")]),
      wantVerdict: "STOP RELEASE",
      wantExit: 1,
    },
    {
      name: "p2-fail",
      results: fixtureSuite([spec("G-01", "passed"), spec("S-07", "failed")]),
      wantVerdict: "WARNING — human decides",
      wantExit: 0,
    },
    {
      name: "p3-fail",
      results: fixtureSuite([spec("G-09", "failed")]),
      wantVerdict: "LOG ONLY",
      wantExit: 0,
    },
  ];

  let ok = true;
  console.log("generate-report self-test");
  for (const fx of fixtures) {
    const agg = aggregate(parseResults(fx.results), checklists);
    const pass = agg.verdict === fx.wantVerdict && agg.exitCode === fx.wantExit;
    console.log(`  ${pass ? "PASS" : "FAIL"}  fixture=${fx.name.padEnd(9)} verdict="${agg.verdict}" exit=${agg.exitCode} (want "${fx.wantVerdict}", exit ${fx.wantExit})`);
    if (!pass) ok = false;
  }
  console.log(ok ? "Self-test: ALL FIXTURES PASS" : "Self-test: FAILURES PRESENT");
  return ok;
}

// ── CLI ──────────────────────────────────────────────────────────────────────
function main(): void {
  const repoRoot = process.cwd();
  const args = process.argv.slice(2);
  const selfTest = args.includes("--self-test");
  const resultsIdx = args.indexOf("--results");
  const outIdx = args.indexOf("--out");
  const resultsPath = resultsIdx >= 0 ? args[resultsIdx + 1] : join(repoRoot, "qa", "results", "results.json");
  const outPath = outIdx >= 0 ? args[outIdx + 1] : undefined;

  const checklists = loadChecklists(repoRoot);

  if (selfTest) {
    const ok = runSelfTest(checklists);
    process.exit(ok ? 0 : 1);
  }

  const abs = resolve(resultsPath);
  if (!existsSync(abs)) {
    console.error(`Results file not found: ${abs}`);
    console.error("Run Playwright first: npx playwright test -c qa/playwright.config.qa.ts (JSON reporter writes qa/results/results.json)");
    process.exit(2);
  }
  let raw: unknown;
  try {
    raw = JSON.parse(readFileSync(abs, "utf8"));
  } catch (err) {
    console.error(`Results file is not valid JSON: ${(err as Error).message}`);
    process.exit(2);
  }

  const outcomes = parseResults(raw);
  if (outcomes.length === 0) {
    console.error("No test outcomes found in results file (unexpected reporter shape).");
    process.exit(2);
  }
  const agg = aggregate(outcomes, checklists);
  const markdown = renderMarkdown(agg, {});
  console.log(markdown);
  if (outPath) {
    const absOut = resolve(outPath);
    mkdirSync(dirname(absOut), { recursive: true });
    writeFileSync(absOut, markdown + "\n");
    console.log(`\nMarkdown report written to ${absOut}`);
  }
  process.exit(agg.exitCode);
}

if (import.meta.main) main();
