/**
 * /health hollow-read guard — deploy-independent pin for the #2665 live-but-empty
 * residual (class filing #2673, remedy pt.1; fix issue #2681).
 *
 * What it asserts:
 *   1. EMPTY-TABLE HONESTY — the /health handler in src/http_server.ts derives a
 *      non-"ok" status ("starting") when the snapshot table is empty. The vacuous
 *      truth trap (`unhealthy === 0` over `services = []`) is exactly how the
 *      #2665 signature (status:"ok" + services{total:0} while the system runs
 *      work) survived the honest-aggregate fix (#2724 lineage).
 *   2. COLD-START FALLBACK HONESTY — the catch fallback never emits a bare "ok";
 *      an unreadable cache is not evidence that everything is healthy.
 *   3. SEMANTIC TRUTH TABLE — the intended derivation, re-stated as pure data:
 *      [] -> starting; all-healthy -> ok; mixed -> degraded; all-unhealthy -> outage.
 *
 * Static source scans follow the test_annotations_floor.ts precedent (deploy-
 * independent; the live-plane behavior is separately witnessed by hourly curl
 * readings, e.g. #2665's evidence series and the cycle-42/43 receipts).
 *
 * Run: tsx test_health_hollow_guard.ts  (wired as `test:health-hollow-guard` in test:unit)
 */
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(fileURLToPath(import.meta.url));
const SERVER_SRC = join(ROOT, "src", "http_server.ts");

let failed = false;
function check(name: string, ok: boolean, detail = "") {
  if (ok) {
    console.log(`[health-hollow-guard] ok — ${name}`);
  } else {
    failed = true;
    console.error(`[health-hollow-guard] FAIL — ${name}${detail ? ` (${detail})` : ""}`);
  }
}

const src = readFileSync(SERVER_SRC, "utf8");

/** Strip line comments and block comments so prose like `must NOT read "ok"` inside
 *  explanatory comments can never satisfy or defeat a code-shape assertion. */
function stripComments(s: string): string {
  let out = "";
  let i = 0;
  while (i < s.length) {
    if (s.startsWith("//", i)) {
      while (i < s.length && s[i] !== "\n") i++;
    } else if (s.startsWith("/*", i)) {
      const close = s.indexOf("*/", i + 2);
      i = close === -1 ? s.length : close + 2;
    } else if (s.startsWith('"', i) || s.startsWith("'", i) || s.startsWith("`", i)) {
      const q = s[i];
      out += s[i++];
      while (i < s.length && s[i] !== q) {
        if (s[i] === "\\") out += s[i++];
        out += s[i++] ?? "";
      }
      if (i < s.length) out += s[i++];
    } else {
      out += s[i++];
    }
  }
  return out;
}

// Isolate the /health handler region: from the route match to its terminating return.
const start = src.indexOf('url === "/health"');
if (start === -1) {
  console.error("[health-hollow-guard] FAIL — /health handler not found in src/http_server.ts");
  process.exit(1);
}
const end = src.indexOf("return;", start);
const region = stripComments(src.slice(start, end === -1 ? src.length : end));

// 1. Empty-table guard: "starting" must be derived BEFORE any "ok" can be reached,
//    keyed on the empty services array (not merely present somewhere in the file).
const emptyGuardIdx = region.indexOf('services.length === 0 ? "starting"');
check(
  "empty-table guard derives \"starting\" before \"ok\" (services.length === 0 ? \"starting\")",
  emptyGuardIdx !== -1 && emptyGuardIdx < region.indexOf('"ok"'),
  "status chain must test emptiness first"
);

// 2. Cold-start fallback: the catch branch must not emit bare "ok".
const catchIdx = region.indexOf("} catch {");
const catchTail = catchIdx === -1 ? "" : region.slice(catchIdx);
check(
  "cold-start catch fallback reports \"starting\" (not bare \"ok\")",
  catchTail.includes('status: "starting"') && !/status:\s*"ok"/.test(catchTail),
  "an unreadable cache is not all-healthy evidence"
);

// 3. Semantic truth table — the intended derivation, pinned as pure data so the
//    contract survives refactors of the inline expression.
type S = { status: string };
function derive(services: S[]): string {
  const unhealthy = services.filter((s) => s.status !== "healthy").length;
  return services.length === 0 ? "starting" : unhealthy === 0 ? "ok" : unhealthy < services.length ? "degraded" : "outage";
}
check("derive([]) = starting (boot state, not ok)", derive([]) === "starting");
check("derive([healthy]) = ok", derive([{ status: "healthy" }]) === "ok");
check("derive(mixed) = degraded", derive([{ status: "healthy" }, { status: "degraded" }]) === "degraded");
check("derive(all-unhealthy) = outage", derive([{ status: "unreachable" }, { status: "unreachable" }]) === "outage");

if (failed) {
  process.exit(1);
}
console.log("[health-hollow-guard] PASS — /health empty-table + cold-start honesty pinned (#2665 residual closed by #2681)");
