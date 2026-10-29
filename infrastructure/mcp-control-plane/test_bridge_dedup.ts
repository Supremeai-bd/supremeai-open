/**
 * #2136 — bridge.submit_patch ingress idempotency regression battery (pure, offline).
 * House style: tsx script, hard asserts, exit code = verdict.
 *
 * Replays the live false positive (2026-10-28, probes P1–P3): the Step-0 search
 * ANDed hyphen-split tokens, so the NOVEL taskId `bridge-20261028-radar-index-freshness-r2`
 * resolved to unrelated open WO #2094 (whose title contains bridge / 20261028 /
 * radar / index / freshness / r2 as separate tokens) and returned
 * bridge:idempotent-noop — silently blocking a legitimate rescue round.
 * The fix: quoted-phrase full-text query + authoritative-position verification
 * (title tail `(${taskId})` or body `### Task ID` field equality).
 */
import { isWorkOrderForTaskId, resolveIngressAction, taskIdSearchQuery } from "./src/lib/bridge_dedup.js";

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

// Real WO #2094 shapes (the false-positive magnet from the live probes).
const WO_2094_TITLE =
  "🌉 Bridge Work Order — docs(scout): Same-cycle registration per the freshness contract (pass 5/7's closing of the adoption-without-registration failure mode). R47 filed issue-side THIS cycle as #2091 (ecosystem-scout, Job 478318): the radar-index freshness gate itself — three same-day collision-imminent allocation occurrences (passes 3/4/6) falsify self-policing; check spec = the index's own §5 #1644-mirror (invariants A registry-completeness, B pointer-truth, C citation-existence), replayable negative fixtures from each logged collision, wiring options A pre-push agent-plane / B admin fast-lint per #1769/#1822. Index edits: next-free pointer R47->R48 (verified free repo-wide), drift-log pass 8, R47 row (open). Docs-only, scout boundary respected (no code edits). Refs #2091 #1644 #2074. (bridge-20261028-r47-index-pass8-2091-r2)";
const WO_2094_BODY = [
  "### Task ID",
  "bridge-20261028-r47-index-pass8-2091-r2",
  "",
  "### Patch Branch",
  "bridge/bridge-20261028-r47-index-pass8-2091-r2",
  "",
  "### Target Repo",
  "Supremeai-bd/supremeai-open",
  "",
  "### Summary (what + why)",
  "docs(scout): radar-index freshness gate registration lane.",
].join("\n");

// Real WO #2118 shape (P1: same-taskId resubmit must stay idempotent-noop).
const WO_2118_TITLE =
  "🌉 Bridge Work Order — feat(bridge): guard(ci): R48 radar-index freshness gate — the #2091 spec, #1644 script-index-gate mirror. (bridge-20261028-radar-index-freshness-r1)";
const NOVEL_R2 = "bridge-20261028-radar-index-freshness-r2";
const R1 = "bridge-20261028-radar-index-freshness-r1";
const R47 = "bridge-20261028-r47-index-pass8-2091-r2";

// ─── 1. Live false positive replay (P2) ─────────────────────────────────────
section("1. Novel taskId must NOT resolve to vocabulary-overlapping WO #2094");
check("P2 replay: novel r2 taskId rejected against #2094 title+body", !isWorkOrderForTaskId(WO_2094_TITLE, WO_2094_BODY, NOVEL_R2));
check("P2 replay: rejected on title alone (token-overlap trap)", !isWorkOrderForTaskId(WO_2094_TITLE, undefined, NOVEL_R2));
check("true owner accepted: #2094 matches its own taskId", isWorkOrderForTaskId(WO_2094_TITLE, WO_2094_BODY, R47));
check("P1 replay: r1 resubmit still idempotent against #2118", isWorkOrderForTaskId(WO_2118_TITLE, undefined, R1));

// ─── 2. Authoritative positions ─────────────────────────────────────────────
section("2. Authoritative positions (title tail / body Task ID field)");
check("title tail `(taskId)` accepted", isWorkOrderForTaskId(`🌉 Bridge Work Order — some summary (${NOVEL_R2})`, undefined, NOVEL_R2));
check("body Task ID field accepted (title-truncation edge)", isWorkOrderForTaskId("🌉 Bridge Work Order — long summary", "### Task ID\n" + NOVEL_R2 + "\n\n### Patch Branch\nbridge/x", NOVEL_R2));
check("prose quotation in body rejected (probe B: the #2136 report quotes the taskId)", !isWorkOrderForTaskId("guard(tower): dedup false-positive", "evidence table cites `bridge-20261028-radar-index-freshness-r2` as the probe taskId", NOVEL_R2));
check("Task ID field with different value rejected", !isWorkOrderForTaskId("🌉 Bridge Work Order — x", "### Task ID\nbridge-20261028-other-task\n", NOVEL_R2));
check("missing Task ID heading rejected", !isWorkOrderForTaskId("🌉 Bridge Work Order — x", "some body without the heading", NOVEL_R2));

// ─── 3. Boundary collisions (H2 suffix class) ───────────────────────────────
section("3. Boundary collisions (round-suffix class)");
check("title tail is exact: `(…-r2)` does not match a `(…-r22)` WO", !isWorkOrderForTaskId("🌉 Bridge Work Order — y (bridge-20261028-x-r22)", undefined, "bridge-20261028-x-r2"));
check("body field is exact: -r22 field rejected for -r2 query", !isWorkOrderForTaskId(undefined as unknown as string, "### Task ID\nbridge-20261028-x-r22\n", "bridge-20261028-x-r2"));
check("prefix taskId does not match longer field value", !isWorkOrderForTaskId("", "### Task ID\nbridge-20261028-x-r2-extra\n", "bridge-20261028-x-r2"));

// ─── 4. Tolerant inputs ─────────────────────────────────────────────────────
section("4. Tolerant inputs");
check("undefined body tolerated", !isWorkOrderForTaskId("no tail here", undefined, NOVEL_R2));
check("null body tolerated", !isWorkOrderForTaskId("no tail here", null, NOVEL_R2));
check("field value whitespace tolerated", isWorkOrderForTaskId("t", "### Task ID\n  " + NOVEL_R2 + "  \n", NOVEL_R2));

// ─── 5. Query shape ─────────────────────────────────────────────────────────
section("5. Step-0 query shape (quoted phrase, full-text, open issues)");
const q = taskIdSearchQuery("Supremeai-bd/supremeai-open", NOVEL_R2);
check("query scopes the open repo", q.startsWith("repo:Supremeai-bd/supremeai-open+is:issue+is:open+"), q);
check("taskId is phrase-quoted", q.includes(`%22${encodeURIComponent(NOVEL_R2)}%22`), q);
check("no in:title (body Task ID field is authoritative)", !q.includes("in:title"), q);
check("hyphen-split token-AND form is gone", !q.includes("+bridge-20261028"), q);

// ─── 6. #2227 branch-aware ingress resolution ───────────────────────────────
section("6. #2227 branch-aware ingress resolution (restores #2112 semantics)");
// Live repro shape (WO #2205 casualty): manually-filed WO active, patch branch
// never landed (bridge/bridge-20261029-health-staleness-guard = 404). The old
// whole-run noop stranded the solver's completed work with nothing on origin.
const pairAndLand = resolveIngressAction(false);
check("WO active + branch MISSING -> pair-and-land (the #2227 fix)", pairAndLand.action === "pair-and-land");
check("pair-and-land carries the wo-active-branch-missing reason", pairAndLand.reason === "wo-active-branch-missing");
check("pair-and-land records branchExists=false", pairAndLand.branchExists === false);
const inFlight = resolveIngressAction(true);
check("WO active + branch EXISTS -> idempotent-noop (resubmit protection kept)", inFlight.action === "idempotent-noop");
check("noop carries the wo-active-branch-in-flight reason", inFlight.reason === "wo-active-branch-in-flight");
check("noop records branchExists=true", inFlight.branchExists === true);
check("decisions are discriminated on action (exhaustive switch shape)", pairAndLand.action !== inFlight.action);
// The #2136 precision layer still gates entry into the branch-aware decision:
// a WO for a DIFFERENT taskId must never reach it (verified in sections 1-3);
// resolveIngressAction only decides WHAT to do once authority is established.

// ─── Verdict ────────────────────────────────────────────────────────────────
console.log("\n=============================================");
if (failures === 0) {
  console.log("ALL BRIDGE DEDUP TESTS PASSED (#2136+#2227)");
} else {
  console.error(`${failures} TEST(S) FAILED (#2136+#2227)`);
}
process.exit(failures === 0 ? 0 : 1);
