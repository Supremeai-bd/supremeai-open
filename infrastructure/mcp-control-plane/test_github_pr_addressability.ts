/**
 * #3368 / R81 — PR read-plane addressability regression battery (pure, offline).
 * House style: tsx script, hard asserts, exit code = verdict.
 *
 * Root cause it prevents: github.list_prs exposed only (state, per_page,
 * limit) over a creation-desc window, so "what is the state of PR N?" was
 * unanswerable for any PR outside the newest ~100 creation ranks. Every
 * #2547/#2567-class audit re-verification hit the wall and fell back to the
 * 403-budget anonymous REST (shared egress IP — 8/8 reads failed live,
 * 2026-10-30 12:45Z). GitHub-REST already guarantees single-PR GET
 * (/pulls/{number} -> state/merged/merged_at/closed_at) and window sort
 * (created|updated|long-running + asc|desc) — the remedy surfaces both
 * through pure helpers pinned here, so the URL contract can never silently
 * drift from the schema promise (the #2614 schema-text-drift class).
 */
import { pullsEndpoint, pullsQuery, resolvePerPage } from "./src/lib/github_pagination.js";

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

const BASE = "https://api.github.com/repos/Supremeai-bd/supremeai-open";

function main(): void {
  section("A1 single-PR addressability: /pulls/{N} at any creation rank");
  check("pull_number=3277 -> /pulls/3277 (the 12:21Z own-submission probe)",
    pullsEndpoint(BASE, 3277) === `${BASE}/pulls/3277`, pullsEndpoint(BASE, 3277));
  check("deep-rank PR reachable the same way (no window semantics)",
    pullsEndpoint(BASE, 1777) === `${BASE}/pulls/1777`, pullsEndpoint(BASE, 1777));
  check("no pull_number -> list plane /pulls",
    pullsEndpoint(BASE, undefined) === `${BASE}/pulls`, pullsEndpoint(BASE, undefined));
  check("null pull_number -> list plane (explicit absence)",
    pullsEndpoint(BASE, null) === `${BASE}/pulls`, pullsEndpoint(BASE, null));

  section("A2 honesty: junk pull_number never fabricates a single-PR URL");
  check("NaN falls back to the list plane (never /pulls/NaN)",
    pullsEndpoint(BASE, Number("junk") as unknown as number) === `${BASE}/pulls`,
    pullsEndpoint(BASE, Number("junk") as unknown as number));
  check("zero/negative never yields /pulls/0 or /pulls/-1",
    pullsEndpoint(BASE, 0) === `${BASE}/pulls` && pullsEndpoint(BASE, -3) === `${BASE}/pulls`);
  check("fractional truncates (12.7 -> /pulls/12, never /pulls/12.7)",
    pullsEndpoint(BASE, 12.7) === `${BASE}/pulls/12`, pullsEndpoint(BASE, 12.7));

  section("A3 window re-sort: sort/direction ride the query string");
  check("sort=updated rides with state+per_page",
    pullsQuery("all", 100, "updated") === "state=all&per_page=100&sort=updated",
    pullsQuery("all", 100, "updated"));
  check("direction alone rides (REST default sort created applies)",
    pullsQuery("closed", 5, undefined, "asc") === "state=closed&per_page=5&direction=asc",
    pullsQuery("closed", 5, undefined, "asc"));
  check("sort+direction together in REST order",
    pullsQuery("all", 50, "updated", "desc") === "state=all&per_page=50&sort=updated&direction=desc",
    pullsQuery("all", 50, "updated", "desc"));
  check("neither knob -> legacy query shape unchanged (byte-compat)",
    pullsQuery("open", 5) === "state=open&per_page=5", pullsQuery("open", 5));

  section("A4 resolved page-size flows into the query (R62 alias intact)");
  check("resolvePerPage(per_page=100) -> per_page=100 in query",
    pullsQuery("all", resolvePerPage(100, undefined)) === "state=all&per_page=100",
    pullsQuery("all", resolvePerPage(100, undefined)));
  check("default window still 5 when no knob given",
    pullsQuery("open", resolvePerPage(undefined, undefined)) === "state=open&per_page=5");

  console.log("\n=============================================");
  if (failures === 0) {
    console.log("ALL PR ADDRESSABILITY TESTS PASSED (#3368/R81)");
  } else {
    console.error(`${failures} TEST(S) FAILED (#3368/R81)`);
  }
  process.exit(failures === 0 ? 0 : 1);
}

main();
