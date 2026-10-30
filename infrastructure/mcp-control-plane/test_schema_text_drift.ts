/**
 * #2614 — Schema-text drift guard (pure, offline).
 * House style: tsx script, hard asserts, exit code = verdict.
 *
 * Root cause it prevents: the R62 per_page remedy (#2379) landed the
 * resolvePerPage fix + regression battery, but the tool-schema DESCRIPTIONS
 * kept the historical "per_page-only callers were silently dropped to the
 * default 5-row window" note. Every AI caller reads that schema text: it
 * claimed the alias was still ignored AFTER it was honored, so agents kept
 * filing false "tower page-lock" outages — the exact dispute #2614 had to
 * falsify with a live probe (2026-10-30: per_page=2 returns 2 rows).
 *
 * The guard keeps the schema text welded to the code reality:
 *  1. No tool-schema description may claim the alias is silently dropped.
 *  2. Every per_page-exposing tool must route through resolvePerPage
 *     (per_page ?? limit ?? fallback) — a schema that promises honoring
 *     without the call-site honoring it is the next drift instance.
 *  3. The precedence source of truth in github_pagination.ts stays intact.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const toolsSrc = readFileSync(join(here, "src/tools/github.tools.ts"), "utf8");
const paginationSrc = readFileSync(
  join(here, "src/lib/github_pagination.ts"),
  "utf8"
);

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
  section("S1 stale-note ban: no schema description may claim silent drop");
  const staleNote = "silently dropped to the default 5-row window";
  check(
    "github.tools.ts carries zero stale R62 drop-notes",
    !toolsSrc.includes(staleNote),
    `found ${toolsSrc.split(staleNote).length - 1} occurrence(s) — the alias is honored since #2379; the text must describe reality (#2614)`
  );

  section("S2 honoring promise: per_page schema text states the alias works");
  const honorNotes = toolsSrc.split("fully honored").length - 1;
  const perPageProps = toolsSrc.split("per_page: z.number()").length - 1;
  check(
    `per_page schema property count == per_page: z.number() count (${perPageProps})`,
    perPageProps > 0,
  );
  check(
    `every per_page-exposing schema describes full honoring (${honorNotes} honor notes)`,
    honorNotes >= perPageProps,
    `${honorNotes} < ${perPageProps} — a per_page property without an honoring description re-introduces the #2614 drift`,
  );

  section("S3 wiring: promise must meet the honoring call-site");
  // "resolvePerPage(" matches call sites only — the import line carries no
  // call parens, so no import subtraction is needed (3 schemas -> 3 calls).
  const resolveCalls = toolsSrc.split("resolvePerPage(").length - 1;
  check(
    "resolvePerPage call sites >= per_page-exposing schemas",
    resolveCalls >= perPageProps,
    `${resolveCalls} call-site(s) < ${perPageProps} schema(s) — a tool that exposes per_page without routing through resolvePerPage silently discards it again`,
  );

  section("S4 precedence SSOT: github_pagination.ts keeps per_page ?? limit");
  check(
    "precedence expression `perPage ?? limit` intact",
    paginationSrc.includes("const raw = perPage ?? limit;"),
    "resolvePerPage precedence changed — update the tool descriptions in the same commit or the schema text drifts again",
  );
  check(
    "1..100 envelope clamp intact",
    paginationSrc.includes("Math.min(Math.max(Math.trunc(n), 1), 100)"),
    "clamp removed — callers could get unbounded windows",
  );

  console.log("\n=============================================");
  if (failures === 0) {
    console.log("ALL SCHEMA-TEXT DRIFT GUARD TESTS PASSED (#2614)");
  } else {
    console.error(`${failures} TEST(S) FAILED (#2614)`);
  }
  process.exit(failures === 0 ? 0 : 1);
}

main();
