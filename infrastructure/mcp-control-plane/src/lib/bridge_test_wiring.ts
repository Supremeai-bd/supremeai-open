/**
 * #2444 — bridge.submit_patch test-wiring checkpoint: pre-land wiring proof.
 *
 * Pure, offline helpers (no network, no env) so the regression battery
 * (test_bridge_test_wiring.ts) can replay the live failures deterministically —
 * same discipline as bridge_staleness.ts (#2333) and bridge_dedup.ts
 * (#2136/#2227).
 *
 * Failure being fixed (class recurrence, 2nd occurrence in ~2h):
 * filers add a new root-level test file to their payload without wiring it
 * into the package's npm scripts. The branch + PR land fine, then the #116
 * wiring guard (`scripts/test-runner.ts --guard`) fails the PR gate — every
 * time, deterministically, AFTER the stranded-PR artifacts already exist:
 * - #2404 r1 (anon-mutation-bound): test_mcp_mutation_rate_limit.ts unwired →
 *   gate red on run 40803525030 (#2405/#2413); superseded by r2 #2407.
 * - #2440 r2 (R65 structured content): test_c29_dual_emission.ts unwired →
 *   gate red on run 40816022722 (#2441; #2443 triage reproduced locally at
 *   97f97dbf: tsc exit 0, every suite passes EXCEPT the guard).
 * Each occurrence costs a red CI run, a stranded PR, a triage WO, and an
 * author-lane rescue round-trip. The checkpoint shifts the same proof left to
 * submit-time: refuse the payload BEFORE branch creation with the exact fix.
 *
 * Contract (pure decision, wiring in bridge.tools.ts pre-Step-B):
 * - Scope is exactly the package the guard governs: files under
 *   `infrastructure/mcp-control-plane/` matching the guard's collection
 *   shapes (root-level `test_*.ts`, or `test/*.test.ts`). Nothing else is
 *   ever refused — zero false-positive surface outside the guarded package.
 * - A payload test file that already exists on main is a MODIFICATION: main's
 *   own wiring guard guarantees it is wired, so it skips.
 * - A payload test file ABSENT from main is NEW: it must be referenced by the
 *   wiring authority — the payload's own package.json override when present,
 *   else main's package.json (the same blob the guard will read post-land).
 * - Unwired new test file -> fail-closed UNWIRED_TEST_ERROR naming the file
 *   and the exact fix (register + chain in the package scripts), the same
 *   recovery style as STALE_BASE_ERROR — no guard-dodging advice.
 * - Manifest absent (404), manifest read error, or diff-mode override that
 *   cannot be evaluated -> fail-open with a per-file disclosure; Tower-side
 *   API health must never block legitimate submissions (staleness precedent).
 */

/** One package-dir group of payload test files, keyed by the governing package. */
export interface WiringGroup {
  /** Directory holding the governing package.json (guard's pkgRoot analogue). */
  packageDir: string;
  /** Payload test-file paths in this group, sorted for deterministic errors. */
  testPaths: string[];
}

/** The guard's root-level shape: `test_*.ts` directly inside the package dir. */
function isRootLevelTestFile(base: string): boolean {
  return base.startsWith("test_") && base.endsWith(".ts");
}

/** The guard's folder shape: `*.test.ts` directly inside the package's `test/` dir. */
function isTestDirTestFile(dir: string, base: string): boolean {
  return dir.endsWith("/test") && base.endsWith(".test.ts");
}

/**
 * Group payload paths into wiring-check candidates. Everything outside the
 * guarded package (`infrastructure/mcp-control-plane/`) is ignored — the
 * checkpoint must be impossible to false-positive on unrelated layouts.
 */
export function payloadTestWiringGroups(paths: readonly string[]): WiringGroup[] {
  const GUARDED_DIR = "infrastructure/mcp-control-plane";
  const byDir = new Map<string, string[]>();
  for (const p of paths) {
    if (typeof p !== "string" || p.length === 0) continue;
    const slash = p.lastIndexOf("/");
    const dir = slash === -1 ? "" : p.slice(0, slash);
    const base = slash === -1 ? p : p.slice(slash + 1);
    // Normalize the guard's two collection shapes to the package dir.
    let packageDir: string | null = null;
    if (dir === GUARDED_DIR && isRootLevelTestFile(base)) {
      packageDir = GUARDED_DIR;
    } else if (dir === `${GUARDED_DIR}/test` && isTestDirTestFile(dir, base)) {
      packageDir = GUARDED_DIR;
    }
    if (!packageDir) continue;
    const bucket = byDir.get(packageDir) ?? [];
    bucket.push(p);
    byDir.set(packageDir, bucket);
  }
  return [...byDir.entries()]
    .map(([packageDir, testPaths]) => ({ packageDir, testPaths: [...testPaths].sort() }))
    .sort((a, b) => (a.packageDir < b.packageDir ? -1 : a.packageDir > b.packageDir ? 1 : 0));
}

/**
 * Mirrors the guard's wired test exactly (`scriptBlob.includes(rel) ||
 * scriptBlob.includes(base)` — basename match against the raw scripts blob).
 */
export function isTestWired(testPath: string, wiredBlob: string): boolean {
  const slash = testPath.lastIndexOf("/");
  const base = slash === -1 ? testPath : testPath.slice(slash + 1);
  return wiredBlob.includes(base);
}

/**
 * Machine-readable rejection prefix (mirrors STALE_BASE_ERROR). The full text
 * names each unwired file and the exact one-line fix so the filer recovers
 * without human help — and without any guard-dodging advice.
 */
export const UNWIRED_TEST_ERROR_PREFIX = "UNWIRED_TEST_ERROR";

export function unwiredTestErrorText(unwired: readonly string[], packageJsonPath: string): string {
  const lines = unwired.map((p) => `  - ${p}`).join("\n");
  return (
    `${UNWIRED_TEST_ERROR_PREFIX}: new test file(s) referenced by NO npm script — the #116 wiring ` +
    `guard would fail this PR's gate after landing (recurring class: #2404 r1, #2440 r2, proposal #2444):\n` +
    `${lines}\n` +
    `Fix before resubmitting: in ${packageJsonPath}, register each suite ` +
    `(\`test:<slug>: tsx <file>.ts\`) and chain it into the test:unit sequence, then include the ` +
    `updated package.json in this payload (full_file). New test suites must not rot silently (#116).`
  );
}
