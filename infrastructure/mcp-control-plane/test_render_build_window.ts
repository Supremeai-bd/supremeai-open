/**
 * #2811 window class — Render month-window build-minute accounting battery
 * (pure, offline). House style: tsx script, hard asserts, exit code = verdict.
 *
 * Witness #2811 (platform-guardian cycle-47): render_service_health ledger
 * readings moved DOWNWARD during the retry-fail deploy loop, once with an
 * exact dual-account mirror (ΔbuildMin == −ΔfreeLimit on both accounts).
 * Usage cannot decrease — the drops were the adapter's own truncated deploy
 * window sliding: old long builds scrolled out of the fixed first page, the
 * computed month-to-date total fell, and freeLimitRemaining (500 − the same
 * variable) rose by exactly that amount. The discriminator pinned here: a
 * 120-deploy month must sum to 120 minutes, not to whatever fits the old
 * window; a pre-month deploy both excludes itself and flags saturation (the
 * cursor stop rule).
 */
import {
  BUILD_WINDOW_MAX_PAGES,
  BUILD_WINDOW_PAGE_SIZE,
  monthStartUtc,
  nextCursor,
  sumMonthBuildSeconds,
  unwrapDeploy,
  windowSaturated,
} from "./src/lib/render_build_window.js";

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

const MONTH_START = new Date(Date.UTC(2026, 9, 1)); // 2026-10-01T00:00:00Z

function dep(id: string, createdIso: string, durationSeconds: number): { deploy: Record<string, string> } {
  const created = new Date(createdIso);
  return {
    deploy: {
      id,
      createdAt: created.toISOString(),
      finishedAt: new Date(created.getTime() + durationSeconds * 1000).toISOString(),
    },
  };
}

function main(): void {
  section("P1 constants: Render page envelope");
  check("page size = 100 (Render cap)", BUILD_WINDOW_PAGE_SIZE === 100);
  check("max pages = 12 (1200-deploy coverage)", BUILD_WINDOW_MAX_PAGES === 12);

  section("P2 monthStartUtc calendar boundary");
  const ms = monthStartUtc(new Date(Date.UTC(2026, 9, 15, 12, 30)));
  check("mid-October -> 2026-10-01T00:00:00.000Z", ms.getTime() === Date.UTC(2026, 9, 1), ms.toISOString());
  const msYearEdge = monthStartUtc(new Date(Date.UTC(2027, 0, 2)));
  check("January -> Jan 1 (year rollover)", msYearEdge.getTime() === Date.UTC(2027, 0, 1), msYearEdge.toISOString());

  section("P3 the #2811 discriminator: a 120-deploy month sums fully");
  const deploys120: unknown[] = [];
  for (let i = 0; i < 120; i++) {
    deploys120.push(dep(`d${i}`, "2026-10-15T00:00:00Z", 60));
  }
  const s120 = sumMonthBuildSeconds(deploys120, MONTH_START);
  check("120 × 1 min = 120.0 min (old fixed window counted 50)", Math.round((s120.totalSeconds / 60) * 10) / 10 === 120, String(s120.totalSeconds));
  check("count = 120", s120.count === 120, String(s120.count));
  check("no pre-month -> not saturated", s120.sawPreMonth === false);

  section("P4 pre-month exclusion + saturation flag (stop rule)");
  const mixed = [dep("old", "2026-09-20T10:00:00Z", 600), ...deploys120];
  const sm = sumMonthBuildSeconds(mixed, MONTH_START);
  check("pre-month build excluded from the sum", sm.count === 120 && Math.round(sm.totalSeconds / 60) === 120);
  check("sawPreMonth flagged", sm.sawPreMonth === true);
  check("windowSaturated honors the flag", windowSaturated(mixed, MONTH_START) === true);

  section("P5 calendar boundary: exactly-at-start counts, 1s earlier does not");
  const sb = sumMonthBuildSeconds(
    [dep("at", "2026-10-01T00:00:00Z", 60), dep("before", "2026-09-30T23:59:59Z", 60)],
    MONTH_START,
  );
  check("exactly-at-month-start deploy counts", sb.count === 1 && Math.round(sb.totalSeconds / 60) === 1);
  check("1s-earlier deploy flags saturation", sb.sawPreMonth === true);

  section("P6 junk tolerance: no crash, no fabricated burn");
  const sj = sumMonthBuildSeconds(
    [
      { deploy: { id: "j1", createdAt: "not-a-date", finishedAt: "junk" } },
      { deploy: { id: "j2" } },
      "garbage-item",
      null,
      dep("zero", "2026-10-02T00:00:00Z", 0),
      dep("neg", "2026-10-03T00:00:00Z", -5),
      dep("ok", "2026-10-04T00:00:00Z", 30),
    ],
    MONTH_START,
  );
  check("only the valid 30s deploy counts", sj.count === 1 && Math.round(sj.totalSeconds) === 30, JSON.stringify(sj));
  check("no saturation signal from junk", sj.sawPreMonth === false);

  section("P7 stop rules");
  const fullPage: unknown[] = [];
  for (let i = 0; i < BUILD_WINDOW_PAGE_SIZE; i++) fullPage.push(dep(`p${i}`, "2026-10-10T00:00:00Z", 1));
  check("full in-month page -> keep paging", windowSaturated(fullPage, MONTH_START) === false);
  check("short page -> saturated", windowSaturated(fullPage.slice(0, 99), MONTH_START) === true);
  check("nextCursor reads the last deploy id", nextCursor(fullPage) === "p99");
  check("nextCursor tolerates empty page", nextCursor([]) === undefined);

  section("P8 envelope tolerance: bare deploy objects unwrap");
  const bare = [{ id: "b1", createdAt: "2026-10-05T00:00:00Z", finishedAt: "2026-10-05T00:02:00Z" }];
  check("bare object sums like the wrapped form", sumMonthBuildSeconds(bare, MONTH_START).totalSeconds === 120);
  check("unwrapDeploy unwraps the {deploy:{...}} envelope", unwrapDeploy(dep("w", "2026-10-05T00:00:00Z", 1)).id === "w");
  check("unwrapDeploy tolerates junk", typeof unwrapDeploy(null) === "object" && unwrapDeploy("junk") !== undefined);

  console.log(failures === 0 ? "\nrender_build_window battery: PASS" : `\nrender_build_window battery: ${failures} FAILURE(S)`);
  process.exit(failures === 0 ? 0 : 1);
}

main();
