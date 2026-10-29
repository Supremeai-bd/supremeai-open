/**
 * #2444 — bridge.submit_patch test-wiring checkpoint regression battery (pure, offline).
 * House style: tsx script, hard asserts, exit code = verdict.
 *
 * Replays the recurring live failure class (2nd occurrence 2026-10-29 ~04:08Z):
 * filers add a new test file to their payload without wiring it into the
 * package's npm scripts. The #116 wiring guard then fails the PR gate AFTER
 * the branch + PR exist — #2404 r1 (test_mcp_mutation_rate_limit.ts unwired,
 * run 40803525030) and #2440 r2 (test_c29_dual_emission.ts unwired, run
 * 40816022722). The checkpoint refuses such payloads at submit-time with the
 * exact fix (UNWIRED_TEST_ERROR), before any branch/PR artifact is minted.
 */
import {
  isTestWired,
  payloadTestWiringGroups,
  unwiredTestErrorText,
  UNWIRED_TEST_ERROR_PREFIX,
} from "./src/lib/bridge_test_wiring.js";

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

// The two live witnesses, verbatim paths from the incidents.
const WITNESS_2404 = "infrastructure/mcp-control-plane/test_mcp_mutation_rate_limit.ts";
const WITNESS_2440 = "infrastructure/mcp-control-plane/test_c29_dual_emission.ts";
// A wiring authority shaped like the real package.json scripts blob (excerpt).
const REAL_BLOB = [
  '"test:unit": "npm run test:unified-diff-eof && npm run test:http-retry',
  ' && tsx test_registry.ts && npm run test:bridge-staleness',
  ' && npm run test:mcp-mutation-rate-limit && npm run test:bridge-verdicts"',
  '"test:bridge-staleness": "tsx test_bridge_staleness.ts"',
  '"test:mcp-mutation-rate-limit": "tsx test_mcp_mutation_rate_limit.ts"',
].join("\n");

// ─── 1. Candidate scoping (zero false-positive surface) ─────────────────────
section("1. Only the guarded package's guard-shaped files are candidates");
const g1 = payloadTestWiringGroups([WITNESS_2440]);
check("root-level test_*.ts under the guarded package is a candidate", g1.length === 1 && g1[0].testPaths.length === 1 && g1[0].testPaths[0] === WITNESS_2440);
check("group packageDir is the guarded package", g1.length === 1 && g1[0].packageDir === "infrastructure/mcp-control-plane");
const g2 = payloadTestWiringGroups(["infrastructure/mcp-control-plane/test/c29_dual.test.ts"]);
check("test/*.test.ts folder shape is a candidate too", g2.length === 1 && g2[0].testPaths[0] === "infrastructure/mcp-control-plane/test/c29_dual.test.ts");
const g3 = payloadTestWiringGroups([
  "src/index.ts",
  "package.json",
  "infrastructure/mcp-control-plane/src/lib/bridge_test_wiring.ts",
  "core/tests/test_helper.ts",
  "scripts/test-runner.ts",
  "test_bridge_staleness.ts",
  "docs/bridge/bridge-20261029-ci2405-closure-receipt.md",
]);
check("non-test / other-package / repo-root files are never candidates", g3.length === 0);
const g4 = payloadTestWiringGroups(["infrastructure/mcp-control-plane/src/tools/test_fixture.ts"]);
check("test_-prefixed file OUTSIDE the package root is not a candidate (nested)", g4.length === 0);
const g5 = payloadTestWiringGroups(["infrastructure/mcp-control-plane/test/nested/deep.test.ts"]);
check("deeper-than-test/ .test.ts is not a candidate (guard is non-recursive)", g5.length === 0);
const g6 = payloadTestWiringGroups([WITNESS_2404, "infrastructure/mcp-control-plane/test/a.test.ts", "infrastructure/mcp-control-plane/test/b.test.ts"]);
check("multiple candidates sort deterministically (test/ dir before root-level: '/' < '_')", g6.length === 1 && g6[0].testPaths.join("|") === ["infrastructure/mcp-control-plane/test/a.test.ts", "infrastructure/mcp-control-plane/test/b.test.ts", WITNESS_2404].join("|"));

// ─── 2. Wired evaluation (guard semantics mirrored) ──────────────────────────
section("2. isTestWired mirrors the guard's basename-in-blob semantics");
check("file wired via chained script reference is WIRED", isTestWired(WITNESS_2404, REAL_BLOB));
check("file wired via its own script entry is WIRED", isTestWired("infrastructure/mcp-control-plane/test_bridge_staleness.ts", REAL_BLOB));
check("unwired witness #2440 is NOT wired in the same blob", !isTestWired(WITNESS_2440, REAL_BLOB));
check("empty blob wires nothing", !isTestWired(WITNESS_2404, ""));
check("substring of a longer name does not false-wire", !isTestWired("infrastructure/mcp-control-plane/test_rate_limit.ts", '"test:mcp-mutation-rate-limit": "tsx test_mcp_mutation_rate_limit.ts"'));

// ─── 3. #2404 replay (wired filer passes through untouched) ─────────────────
section("3. #2404 replay: r1 unwired would be refused, r2's payload passes");
const r1Groups = payloadTestWiringGroups([WITNESS_2404, "src/http_server.ts", "src/lib/env.ts"]);
check("r1 payload groups exactly one guarded group", r1Groups.length === 1);
const r1Unwired = r1Groups[0].testPaths.filter((p) => !isTestWired(p, REAL_BLOB_WITHOUT(WITNESS_2404)));
check("r1 (no wiring) evaluates unwired", r1Unwired.length === 1 && r1Unwired[0] === WITNESS_2404);
const r2Unwired = r1Groups[0].testPaths.filter((p) => !isTestWired(p, REAL_BLOB));
check("r2 (wired in same payload's package.json) evaluates clean — zero behavior change for correct filers", r2Unwired.length === 0);

function REAL_BLOB_WITHOUT(wiredPath: string): string {
  const base = wiredPath.slice(wiredPath.lastIndexOf("/") + 1);
  return REAL_BLOB.split("\n").filter((line) => !line.includes(base)).join("\n");
}

// ─── 4. Error text contract (recovery without human help, no bypass teaching) ──
section("4. UNWIRED_TEST_ERROR text: names files + exact fix, never teaches guard-dodging");
const errText = unwiredTestErrorText([WITNESS_2440], "infrastructure/mcp-control-plane/package.json");
check("error carries the machine-readable prefix", errText.startsWith(UNWIRED_TEST_ERROR_PREFIX) && UNWIRED_TEST_ERROR_PREFIX === "UNWIRED_TEST_ERROR");
check("error names the unwired path verbatim", errText.includes(WITNESS_2440));
check("error names the governing package.json", errText.includes("infrastructure/mcp-control-plane/package.json"));
check("error states the deterministic consequence (#116 guard, post-land)", errText.includes("#116") && errText.includes("wiring guard"));
check("error gives the exact registration fix (tsx entry + test:unit chain)", errText.includes("test:unit") && errText.includes("tsx"));
check("error demands the manifest ride the same payload (full_file)", errText.includes("this payload") && errText.includes("full_file"));
check("error cites the recurrence lineage (#2404/#2440/#2444)", errText.includes("#2404") && errText.includes("#2440") && errText.includes("#2444"));
check("no EXEMPT-map dodging advice in the error", !errText.includes("EXEMPT"));
check("no guard-skip or disable advice in the error", !errText.toLowerCase().includes("skip the guard") && !errText.toLowerCase().includes("disable the guard"));
const multiText = unwiredTestErrorText([WITNESS_2404, WITNESS_2440], "infrastructure/mcp-control-plane/package.json");
check("multiple unwired files are each named", multiText.includes(WITNESS_2404) && multiText.includes(WITNESS_2440));

// ─── 5. Group determinism (stable errors across runs) ───────────────────────
section("5. Grouping is deterministic and sorted");
const a = payloadTestWiringGroups([WITNESS_2440, WITNESS_2404]);
const b = payloadTestWiringGroups([WITNESS_2404, WITNESS_2440]);
check("input order does not change the grouped output", JSON.stringify(a) === JSON.stringify(b));
check("paths inside a group are sorted", JSON.stringify(a[0].testPaths) === JSON.stringify([...a[0].testPaths].sort()));
check("empty payload yields no groups (legacy callers untouched)", payloadTestWiringGroups([]).length === 0);

// ─── 6. Discriminant shape (callers can branch on the verdict) ───────────────
section("6. Verdict discriminants");
check("groups expose packageDir + testPaths and nothing else", JSON.stringify(Object.keys(a[0])) === JSON.stringify(["packageDir", "testPaths"]));
check("isTestWired returns a strict boolean", typeof isTestWired(WITNESS_2404, REAL_BLOB) === "boolean");

console.log(`\n${failures === 0 ? "ALL CHECKS PASSED" : `${failures} CHECK(S) FAILED`}`);
process.exit(failures === 0 ? 0 : 1);
