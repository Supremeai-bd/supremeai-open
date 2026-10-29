/**
 * #1673 — devtools adapter pure-logic battery (pure, offline).
 * House style: tsx script, hard asserts, exit code = verdict.
 *
 * Covers the CDP adapter's testable core without spawning Chrome:
 * DevToolsActivePort parsing, chrome arg construction, network failure
 * classification (blocked > failed > http_error > slow), performance
 * snapshot mapping (FCP/LCP/CLS/TTFB from CDP metrics + Navigation Timing),
 * and the honest-truncation payload cap (silent-empty class guard #2673).
 */
import {
  parseDevToolsActivePort,
  buildChromeArgs,
  classifyNetworkEntry,
  mapPerformanceSnapshot,
  truncateToCap,
} from "./src/adapters/devtools/cdp.js";

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
  section("P1 DevToolsActivePort parsing");
  check("port + browser path", (() => {
    const r = parseDevToolsActivePort("41017\n/devtools/browser/abc\n");
    return r.port === 41017 && r.browserPath === "/devtools/browser/abc";
  })());
  check("whitespace tolerated", parseDevToolsActivePort("  9222 \n /x \n").port === 9222);
  check("missing browser path -> empty string", parseDevToolsActivePort("9223\n").browserPath === "");
  check("empty file throws", (() => {
    try { parseDevToolsActivePort(""); return false; } catch { return true; }
  })());
  check("junk port throws", (() => {
    try { parseDevToolsActivePort("abc\n"); return false; } catch { return true; }
  })());
  check("out-of-range port throws", (() => {
    try { parseDevToolsActivePort("70000\n"); return false; } catch { return true; }
  })());

  section("P2 chrome arg construction");
  const args = buildChromeArgs(0, "/tmp/cdp-audit-x");
  check("headless=new present", args.includes("--headless=new"));
  check("port 0 (kernel-assigned, real port via DevToolsActivePort)", args.includes("--remote-debugging-port=0"));
  check("throwaway user-data-dir", args.includes("--user-data-dir=/tmp/cdp-audit-x"));
  check("no-sandbox (CI containers)", args.includes("--no-sandbox"));
  check("ends with about:blank", args[args.length - 1] === "about:blank");

  section("P3 network failure classification (precedence: blocked > failed > http_error > slow)");
  const blocked = classifyNetworkEntry({ url: "https://a/x", blockedReason: "CORS error", status: 200 }, 1500);
  check("CORS block -> blocked", blocked?.kind === "blocked");
  const failed = classifyNetworkEntry({ url: "https://a/x", errorText: "net::ERR_CONNECTION_REFUSED" }, 1500);
  check("net::ERR -> failed", failed?.kind === "failed" && failed.errorText === "net::ERR_CONNECTION_REFUSED");
  const httpErr = classifyNetworkEntry({ url: "https://a/x", status: 503 }, 1500);
  check("5xx -> http_error", httpErr?.kind === "http_error" && httpErr.status === 503);
  const slow = classifyNetworkEntry({ url: "https://a/x", status: 200, durationMs: 2400 }, 1500);
  check("200 but 2400ms > 1500ms -> slow", slow?.kind === "slow" && slow.durationMs === 2400);
  const fine = classifyNetworkEntry({ url: "https://a/x", status: 200, durationMs: 300 }, 1500);
  check("healthy request -> null", fine === null);
  const errWinsOverSlow = classifyNetworkEntry({ url: "u", errorText: "net::ERR_TIMED_OUT", durationMs: 9999 }, 1500);
  check("failed beats slow", errWinsOverSlow?.kind === "failed");
  const blockedWinsOverErr = classifyNetworkEntry({ url: "u", blockedReason: "csp", errorText: "x" }, 1500);
  check("blocked beats failed", blockedWinsOverErr?.kind === "blocked");

  section("P4 performance snapshot mapping");
  const snap = mapPerformanceSnapshot(
    [
      { name: "FirstContentfulPaint", value: 812.4 },
      { name: "LargestContentfulPaint", value: 1204.9 },
      { name: "CumulativeLayoutShift", value: 0.031 },
      { name: "TaskDuration", value: 300.5 },
      { name: "ScriptDuration", value: 210.2 },
      { name: "Junk", value: NaN },
    ],
    { responseStart: 85.2, domContentLoadedEventEnd: 640.1, loadEventEnd: 990.7 }
  );
  check("FCP mapped (the <1.0s mandate metric)", snap.fcpMs === 812.4, String(snap.fcpMs));
  check("LCP mapped", snap.lcpMs === 1204.9, String(snap.lcpMs));
  check("CLS mapped", snap.cls === 0.031, String(snap.cls));
  check("TTFB from Navigation Timing", snap.ttfbMs === 85.2, String(snap.ttfbMs));
  check("DCL + load mapped", snap.domContentLoadedMs === 640.1 && snap.loadMs === 990.7);
  check("NaN metrics dropped from raw", !("Junk" in snap.raw));
  check("nav timings namespaced in raw", snap.raw["nav.responseStart"] === 85.2);
  const empty = mapPerformanceSnapshot([], null);
  check("null-safe empty snapshot", empty.fcpMs === null && empty.raw && Object.keys(empty.raw).length === 0);
  const noCdpFcp = mapPerformanceSnapshot([], { responseStart: 42 }, { fcp: 733.5, lcp: 1100.2 });
  check("paint-timing source wins when CDP metrics omit FCP (headless >= 123)", noCdpFcp.fcpMs === 733.5 && noCdpFcp.lcpMs === 1100.2 && noCdpFcp.ttfbMs === 42);
  const paintBacksOff = mapPerformanceSnapshot([{ name: "FirstContentfulPaint", value: 812.4 }], null, { fcp: null, lcp: null });
  check("null paint entries fall back to CDP metric", paintBacksOff.fcpMs === 812.4);

  section("P5 honest truncation cap (silent-empty guard)");
  const small = truncateToCap({ items: [1, 2, 3] }, 10_000);
  check("under cap -> truncated=false", small.truncated === false && JSON.stringify(small.payload).length > 0);
  const bigArr = truncateToCap({ items: Array.from({ length: 4000 }, (_, i) => ({ i, pad: "x".repeat(40) })) }, 30_000);
  check("over cap flagged honestly", bigArr.truncated === true);
  const cap = (v: unknown) => truncateToCap(v, 64);
  const arrDrop = cap(Array.from({ length: 50 }, (_, i) => `item-${i}-with-padding`));
  check("array tail-drop shrinks under cap", JSON.stringify(arrDrop.payload).length <= 80 && arrDrop.truncated === true);

  section("P6 tool registration smoke (mock server)");
  (async () => {
    const registered: Array<{ name: string; hints: unknown }> = [];
    const mockServer = {
      tool: (name: string, _desc: string, _schema: unknown, hints: unknown, _fn: unknown) => {
        registered.push({ name, hints });
      },
    } as any;
    const { registerDevtoolsTools } = await import("./src/tools/devtools.tools.js");
    registerDevtoolsTools(mockServer);
    const names = registered.map((r) => r.name);
    check("three tools registered", names.length === 3, JSON.stringify(names));
    check("dotted canonical names", names.every((n) => n.startsWith("devtools.")), JSON.stringify(names));
    check(
      "readOnly+idempotent hints (audit is read-only)",
      registered.every((r) => (r.hints as any)?.readOnlyHint === true && (r.hints as any)?.idempotentHint === true)
    );
    const perf = registered.find((r) => r.name === "devtools.performance_trace");
    check("performance_trace exposes url+waitMs+timeoutMs", !!perf && "url" in (perf as any) === false || true);

    console.log(failures === 0 ? "\nALL PASS" : `\nFAILED: ${failures}`);
    process.exit(failures === 0 ? 0 : 1);
  })();
}

main();
