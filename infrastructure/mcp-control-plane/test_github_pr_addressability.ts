/**
 * #3368 / R81 — github.list_prs single-PR addressability + sort passthrough
 * regression battery (pure, offline). House style: tsx script, hard asserts,
 * exit code = verdict.
 *
 * Root cause it prevents: the tower's only PR read plane answered only the
 * creation-desc list window (5 props: accountId/repo/state/per_page/limit),
 * so "what is the state of PR N?" was unanswerable for any PR outside the
 * window — every #2547/#2567-census-class audit hit the wall (live receipt
 * 2026-10-30 12:45Z: 5 capability PRs ~3200 ranks deep; anon-REST fallback
 * 403x8 on the shared egress IP). The remedy surfaces what GitHub REST
 * already guarantees server-side: GET /pulls/{n} and sort/direction —
 * surfaced through ONE pure URL SSOT (buildPullsUrl) so the list dialect and
 * the one-PR dialect cannot fork (the R62 per_page trap was exactly such a
 * fork). Backward compatibility is pinned byte-for-byte: a default list call
 * must produce the same URL the pre-#3368 code produced.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { buildPullsUrl } from "./src/adapters/github/index.js";

const here = dirname(fileURLToPath(import.meta.url));
const adapterSrc = readFileSync(join(here, "src/adapters/github/index.ts"), "utf8");
const toolsSrc = readFileSync(join(here, "src/tools/github.tools.ts"), "utf8");
const packageJson = JSON.parse(readFileSync(join(here, "package.json"), "utf8"));

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
  const base = "https://api.github.com/repos/Supremeai-bd/supremeai";

  section("P1 backward compatibility: the pre-#3368 list URL is byte-identical");
  check(
    "default list (state=open, per_page=5)",
    buildPullsUrl(base, { state: "open", perPage: 5 }) === `${base}/pulls?state=open&per_page=5`,
    buildPullsUrl(base, { state: "open", perPage: 5 }),
  );
  check(
    "state=all + per_page=100 (the census probe shape)",
    buildPullsUrl(base, { state: "all", perPage: 100 }) === `${base}/pulls?state=all&per_page=100`,
    buildPullsUrl(base, { state: "all", perPage: 100 }),
  );
  check(
    "state default: omitted -> open",
    buildPullsUrl(base, {}) === `${base}/pulls?state=open&per_page=5`,
    buildPullsUrl(base, {}),
  );

  section("P2 single-PR addressability (the #3368 census path)");
  check(
    "pull_number=3328 -> /pulls/3328 (no query string)",
    buildPullsUrl(base, { pullNumber: 3328 }) === `${base}/pulls/3328`,
    buildPullsUrl(base, { pullNumber: 3328 }),
  );
  check(
    "string pull_number accepted ('1787')",
    buildPullsUrl(base, { pullNumber: "1787" }) === `${base}/pulls/1787`,
    buildPullsUrl(base, { pullNumber: "1787" }),
  );
  check(
    "pull_number wins over list knobs (never silently re-windowed)",
    buildPullsUrl(base, { pullNumber: 2119, state: "closed", perPage: 100, sort: "updated" }) ===
      `${base}/pulls/2119`,
    buildPullsUrl(base, { pullNumber: 2119, state: "closed", perPage: 100, sort: "updated" }),
  );

  section("P3 pull_number junk falls back to the list dialect (fail-open, not a crash)");
  check(
    "pull_number=null -> list URL",
    buildPullsUrl(base, { pullNumber: null, state: "open", perPage: 5 }) ===
      `${base}/pulls?state=open&per_page=5`,
    buildPullsUrl(base, { pullNumber: null, state: "open", perPage: 5 }),
  );
  check(
    "pull_number='' -> list URL",
    buildPullsUrl(base, { pullNumber: "", state: "open", perPage: 5 }) ===
      `${base}/pulls?state=open&per_page=5`,
    buildPullsUrl(base, { pullNumber: "", state: "open", perPage: 5 }),
  );
  check(
    "pull_number=undefined -> list URL",
    buildPullsUrl(base, { state: "open", perPage: 5 }) === `${base}/pulls?state=open&per_page=5`,
    buildPullsUrl(base, { state: "open", perPage: 5 }),
  );

  section("P4 sort/direction passthrough: appended only when provided");
  check(
    "sort=updated, direction=asc",
    buildPullsUrl(base, { state: "all", perPage: 100, sort: "updated", direction: "asc" }) ===
      `${base}/pulls?state=all&per_page=100&sort=updated&direction=asc`,
    buildPullsUrl(base, { state: "all", perPage: 100, sort: "updated", direction: "asc" }),
  );
  check(
    "sort alone (direction omitted) — no empty params",
    buildPullsUrl(base, { state: "open", perPage: 5, sort: "updated" }) ===
      `${base}/pulls?state=open&per_page=5&sort=updated`,
    buildPullsUrl(base, { state: "open", perPage: 5, sort: "updated" }),
  );
  check(
    "neither provided — URL stays byte-identical (no sort=undefined garbage)",
    !buildPullsUrl(base, { state: "open", perPage: 5 }).includes("undefined"),
    buildPullsUrl(base, { state: "open", perPage: 5 }),
  );

  section("P5 schema surface: the #3368 falsification clause (tools/list gains the props)");
  check("schema exposes pull_number", toolsSrc.includes("pull_number: z.number().int().min(1)"));
  check("schema exposes sort enum", toolsSrc.includes('sort: z.enum(["created", "updated", "long-running"])'));
  check("schema exposes direction enum", toolsSrc.includes('direction: z.enum(["asc", "desc"])'));
  check(
    "handler routes single-PR when pull_number present",
    toolsSrc.includes("? await getPullRequest(target, pull_number)"),
  );
  check(
    "handler still routes the list path through resolvePerPage (R62 alias kept)",
    toolsSrc.includes("resolvePerPage(per_page, limit)"),
  );
  check(
    "tool description names the single-PR path (AI callers must discover it)",
    toolsSrc.includes("pull_number to fetch exactly one PR"),
  );

  section("P6 adapter SSOT: both endpoints route through buildPullsUrl (no dialect fork)");
  check("adapter exports buildPullsUrl", adapterSrc.includes("export function buildPullsUrl"));
  check(
    "listPullRequests builds its URL via the SSOT",
    /listPullRequests[\s\S]{0,600}buildPullsUrl\(baseUrl, \{ state, perPage: limit, sort, direction \}\)/.test(
      adapterSrc,
    ),
  );
  check(
    "getPullRequest builds its URL via the SSOT",
    /getPullRequest[\s\S]{0,600}buildPullsUrl\(baseUrl, \{ pullNumber \}\)/.test(adapterSrc),
  );
  check(
    "getPullRequest returns the verdict-plane fields incl. closedAt",
    adapterSrc.includes("closedAt: data.closed_at"),
  );
  check(
    "no raw template-literal /pulls? query re-introduced in the adapter",
    !adapterSrc.includes("/pulls?state="),
  );

  section("P7 wiring: the battery is chained into test:unit (#116 poka-yoke)");
  const unitScript: string = packageJson.scripts["test:unit"] || "";
  check(
    "package.json has test:github-pr-addressability",
    typeof packageJson.scripts["test:github-pr-addressability"] === "string",
  );
  check("test:unit chains test:github-pr-addressability", unitScript.includes("test:github-pr-addressability"));

  console.log("\n=============================================");
  if (failures === 0) {
    console.log("ALL GITHUB PR-ADDRESSABILITY TESTS PASSED (#3368/R81)");
    process.exit(0);
  }
  console.error(`${failures} CHECK(S) FAILED (#3368/R81)`);
  process.exit(1);
}

main();
