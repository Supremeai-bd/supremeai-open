/**
 * #2311 / R62 — GitHub list-tool per_page alias regression battery (pure, offline).
 * House style: tsx script, hard asserts, exit code = verdict.
 *
 * Replays the live probe (2026-10-29, R62): the three list-tool schemas
 * (github.list_prs, github.workflow_runs, github.actions_op list_runs)
 * exposed `limit` only, while GitHub-REST-conventional callers send
 * `per_page` — zod strips unknown keys, so the value was silently
 * discarded and every call degraded to the default 5-row window with
 * zero truncation signal (per_page=1 -> 5 rows was the discriminator:
 * discarded, not clamped). resolvePerPage is the shared precedence rule:
 * per_page ?? limit ?? fallback, clamped to GitHub's 1..100 envelope,
 * junk falls back (a window preference is never a hard failure).
 */
import { resolvePerPage } from "./src/lib/github_pagination.js";

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
  console.log(`\n── ${title} ──`);
}

function main(): void {
  section("P1 precedence: per_page wins over limit");
  check("per_page=25, limit=5 -> 25", resolvePerPage(25, 5) === 25, String(resolvePerPage(25, 5)));
  check("per_page=1, limit=50 -> 1 (the R62 discriminator)", resolvePerPage(1, 50) === 1, String(resolvePerPage(1, 50)));
  check("per_page=0 with limit set -> clamp to 1 (zod blocks int<=0; defensive path)", resolvePerPage(0, 5) === 1, String(resolvePerPage(0, 5)));

  section("P2 limit is honored when per_page absent");
  check("limit=50 alone -> 50", resolvePerPage(undefined, 50) === 50, String(resolvePerPage(undefined, 50)));
  check("limit=25 alone -> 25", resolvePerPage(undefined, 25) === 25, String(resolvePerPage(undefined, 25)));

  section("P3 fallback: neither knob (or junk) -> default 5");
  check("both undefined -> 5", resolvePerPage(undefined, undefined) === 5, String(resolvePerPage(undefined, undefined)));
  check("both null -> 5", resolvePerPage(null, null) === 5, String(resolvePerPage(null, null)));
  check("empty string -> 5", resolvePerPage("", 5) === 5, String(resolvePerPage("", 5)));
  check("NaN string junk -> 5", resolvePerPage("lots", undefined) === 5, String(resolvePerPage("lots", undefined)));
  check("explicit fallback honored", resolvePerPage(undefined, undefined, 10) === 10, String(resolvePerPage(undefined, undefined, 10)));

  section("P4 GitHub 1..100 envelope clamp");
  check("per_page=500 -> 100", resolvePerPage(500, undefined) === 100, String(resolvePerPage(500, undefined)));
  check("limit=500 (legacy unconstrained knob) -> 100", resolvePerPage(undefined, 500) === 100, String(resolvePerPage(undefined, 500)));
  check("per_page=0.5 -> 1", resolvePerPage(0.5, undefined) === 1, String(resolvePerPage(0.5, undefined)));
  check("per_page=12.7 -> 12 (truncate, never round up)", resolvePerPage(12.7, undefined) === 12, String(resolvePerPage(12.7, undefined)));
  check("per_page=100 boundary kept", resolvePerPage(100, undefined) === 100, String(resolvePerPage(100, undefined)));

  section("P5 honesty: the alias must not regress to silent discard");
  check("per_page=5, limit=5 -> 5 (identity)", resolvePerPage(5, 5) === 5, String(resolvePerPage(5, 5)));
  check("per_page=2 -> 2 (NOT the 5-row hard window)", resolvePerPage(2, undefined) === 2, String(resolvePerPage(2, undefined)));

  console.log("\n=============================================");
  if (failures === 0) {
    console.log("ALL GITHUB PAGINATION TESTS PASSED (#2311/R62)");
  } else {
    console.error(`${failures} TEST(S) FAILED (#2311/R62)`);
  }
  process.exit(failures === 0 ? 0 : 1);
}

main();
