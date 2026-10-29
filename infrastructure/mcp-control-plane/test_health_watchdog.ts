/**
 * #2665 watchdog increment guard — deploy-independent pin for the monitoring-lane
 * remedies (#2710; #2673 remedy pt.2; follows the #2681 hollow-guard precedent).
 *
 * What it asserts:
 *   1. COMPLETION STAMPING — HealthCache exposes markSweepCompleted() telemetry
 *      (lastCompletedSweepMs + sweepCompletions) and HealthEngine.runFullSweep
 *      stamps it on the SUCCESS path, after the durable history append.
 *   2. /health STALENESS TELEMETRY — the /health response carries additive
 *      lastCompletedSweepAt / sweepCompletions / stale keys (both the main and
 *      the cold-start fallback branches), so consumers can distinguish
 *      "all-clear" from "no data / data too old".
 *   3. SWEEP-GAP ALARM (anti-false-clear) — a 60s watchdog interval alarms on
 *      the RISING EDGE only (>10min without any completion, past boot grace)
 *      and RE-ARMS when a fresh completion lands: a one-off manual sweep buys
 *      exactly one silence window, never a permanent all-clear.
 *   4. SEMANTIC TRUTH TABLE — deriveWatchdog() is imported and pinned as pure
 *      data: null-completion / grace / fresh / boundary (exactly 10min is still
 *      fresh — strictly-greater comparison) / stale-rearm.
 *
 * Static source scans follow the test_annotations_floor.ts /
 * test_health_hollow_guard.ts precedent (deploy-independent; live-plane
 * behavior is separately witnessed by hourly curl readings, e.g. #2665's
 * evidence series and the cycle-42/43/44 receipts).
 *
 * Run: tsx test_health_watchdog.ts  (wired as `test:health-watchdog` in test:unit)
 */
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { deriveWatchdog, SWEEP_STALE_AFTER_MS, WATCHDOG_BOOT_GRACE_MS } from "./src/health/watchdog.js";

const ROOT = dirname(fileURLToPath(import.meta.url));
const SERVER_SRC = join(ROOT, "src", "http_server.ts");
const CACHE_SRC = join(ROOT, "src", "health", "snapshot.ts");
const ENGINE_SRC = join(ROOT, "src", "health", "engine.ts");

let failed = false;
function check(name: string, ok: boolean, detail = "") {
  if (ok) {
    console.log(`[health-watchdog] ok — ${name}`);
  } else {
    failed = true;
    console.error(`[health-watchdog] FAIL — ${name}${detail ? ` (${detail})` : ""}`);
  }
}

/** Strip line comments and block comments so prose inside explanatory comments
 *  can never satisfy or defeat a code-shape assertion (#2681 precedent). */
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

// ── 1. Completion stamping (snapshot.ts + engine.ts) ──────────────────────────
const cacheSrc = stripComments(readFileSync(CACHE_SRC, "utf8"));
check(
  "HealthCache.markSweepCompleted stamps lastCompletedSweepMs",
  /markSweepCompleted\([\s\S]{0,60}?\)\s*\{[\s\S]{0,200}?this\.lastCompletedSweepMs\s*=\s*atMs/.test(cacheSrc),
);
check(
  "markSweepCompleted increments sweepCompletions",
  /this\.sweepCompletions\s*\+=\s*1/.test(cacheSrc),
);
check(
  "HealthCache exposes getLastCompletedSweepMs + getSweepCompletions",
  cacheSrc.includes("getLastCompletedSweepMs(): number | null") && cacheSrc.includes("getSweepCompletions(): number"),
);

const engineSrc = stripComments(readFileSync(ENGINE_SRC, "utf8"));
const stampIdx = engineSrc.indexOf("globalHealthCache.markSweepCompleted()");
const histIdx = engineSrc.indexOf('provider: "__sweep__"');
check(
  "engine.runFullSweep stamps completion on the success path",
  stampIdx !== -1,
  "markSweepCompleted() call missing from engine.ts",
);
check(
  "stamping happens AFTER the durable history append (telemetry never outruns persistence)",
  stampIdx !== -1 && histIdx !== -1 && stampIdx > histIdx,
);

// ── 2. /health staleness telemetry (http_server.ts) ───────────────────────────
const rawServer = readFileSync(SERVER_SRC, "utf8");
const serverSrc = stripComments(rawServer);
const hStart = rawServer.indexOf('url === "/health"');
if (hStart === -1) {
  check("/health handler present in src/http_server.ts", false, "route anchor not found");
} else {
  const hEnd = rawServer.indexOf("return;", hStart);
  const region = stripComments(rawServer.slice(hStart, hEnd === -1 ? rawServer.length : hEnd));
  check(
    "/health response carries lastCompletedSweepAt",
    region.includes("lastCompletedSweepAt:"),
  );
  check(
    "/health response carries sweepCompletions",
    region.includes("sweepCompletions:"),
  );
  check(
    "/health response carries stale flag",
    region.includes("stale:"),
  );
  const catchIdx = region.indexOf("} catch {");
  const catchTail = catchIdx === -1 ? "" : region.slice(catchIdx);
  check(
    "cold-start fallback also reports stale:true + null telemetry",
    catchTail.includes("stale: true") && catchTail.includes("lastCompletedSweepAt: null"),
    "an unreadable cache is not all-clear evidence",
  );
}

// ── 3. Sweep-gap alarm with rising edge + re-arm (anti-false-clear) ──────────
const timerIdx = serverSrc.indexOf("healthWatchdogTimer");
check(
  "watchdog interval exists in http_server.ts",
  timerIdx !== -1 && /const\s+healthWatchdogTimer\s*=\s*setInterval/.test(serverSrc),
);
const timerAnchor = serverSrc.indexOf("healthWatchdogTimer = setInterval");
check(
  "watchdog interval cadence is 60s",
  timerAnchor !== -1 && /\},\s*60_000\)/.test(serverSrc.slice(timerAnchor, timerAnchor + 2500)),
);
check(
  "rising-edge alarm: alarmDue && !healthWatchdogAlarmActive",
  /view\.alarmDue\s*&&\s*!healthWatchdogAlarmActive/.test(serverSrc),
);
check(
  "re-arm branch: fresh completion clears the alarm latch",
  /!\s*view\.stale\s*\)?\s*\{[\s\S]{0,200}?healthWatchdogAlarmActive\s*=\s*false/.test(serverSrc),
);
const watchdogModuleSrc = stripComments(readFileSync(join(ROOT, "src", "health", "watchdog.ts"), "utf8"));
check(
  "alarm mirrors into durable history (__watchdog__ rows)",
  /recordWatchdogAlarm\(/.test(serverSrc) && /__watchdog__/.test(watchdogModuleSrc),
);
check(
  "watchdog timer is unref'd (Render spin-down must stay possible)",
  /healthWatchdogTimer\.unref/.test(serverSrc),
);

// ── 4. Semantic truth table for deriveWatchdog (imported, not re-stated) ─────
const T0 = 1_700_000_000_000;
const MIN = 60_000;
check("constants: SWEEP_STALE_AFTER_MS = 600_000 (10min)", SWEEP_STALE_AFTER_MS === 600_000);
check("constants: WATCHDOG_BOOT_GRACE_MS = 600_000 (10min)", WATCHDOG_BOOT_GRACE_MS === 600_000);

// never swept, inside boot grace -> stale, but alarm held back
const a = deriveWatchdog(T0 + 1 * MIN, T0, null, 0);
check("truth: never-swept within grace -> stale=true alarmDue=false", a.stale === true && a.alarmDue === false);
// never swept, past grace -> alarm
const b = deriveWatchdog(T0 + 11 * MIN, T0, null, 0);
check("truth: never-swept past grace -> stale=true alarmDue=true", b.stale === true && b.alarmDue === true);
// fresh completion 3min ago (e.g. one-off manual sweep) -> all-clear window
const c = deriveWatchdog(T0 + 20 * MIN, T0, T0 + 17 * MIN, 1);
check("truth: 3min-old completion -> stale=false alarmDue=false", c.stale === false && c.alarmDue === false);
// boundary: EXACTLY 10min old is still fresh (strictly-greater comparison)
const d = deriveWatchdog(T0 + 30 * MIN, T0, T0 + 20 * MIN, 2);
check("truth: exactly-at-edge completion -> still fresh (strictly-greater)", d.stale === false);
// 10.5min old -> stale again (manual window expired; alarm re-arms)
const e = deriveWatchdog(T0 + 30 * MIN + 30_000, T0, T0 + 20 * MIN, 2);
check("truth: past-edge completion -> stale=true alarmDue=true (re-arm)", e.stale === true && e.alarmDue === true);
// ISO shaping
check("truth: lastCompletedSweepAt is ISO or null", c.lastCompletedSweepAt !== null && !Number.isNaN(Date.parse(c.lastCompletedSweepAt as string)) && a.lastCompletedSweepAt === null);
check("truth: bootedAt is ISO", !Number.isNaN(Date.parse(a.bootedAt)));
check("truth: sweepCompletions passes through", c.sweepCompletions === 1 && e.sweepCompletions === 2);

if (failed) {
  process.exit(1);
}
console.log("[health-watchdog] PASS — sweep-completion telemetry + rising-edge gap alarm + anti-false-clear re-arm pinned (#2710)");
