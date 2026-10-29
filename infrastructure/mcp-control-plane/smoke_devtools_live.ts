/**
 * #1673 live smoke — real Chrome + real CDP against a local fixture page.
 * Fixture: page.html fires console.error, fetches /api/nope (404), loads /missing.png (404).
 * Expected: console_errors >= 1, network_failures >= 2, performance_trace FCP numeric.
 */
import { collectConsoleErrors, collectNetworkFailures, collectPerformanceTrace } from "./src/adapters/devtools/audit.js";

// Portable: point SMOKE_CHROME at any Chrome/Chromium binary; default = PATH chrome.
const CHROME = process.env.SMOKE_CHROME ?? "chrome";
const URL = process.env.SMOKE_URL ?? "http://127.0.0.1:18923/page.html";

let failures = 0;
function check(name: string, cond: boolean, detail?: string): void {
  if (cond) console.log(`  ✓ ${name}`);
  else { failures += 1; console.error(`  ✗ ${name}${detail ? ` — ${detail}` : ""}`); }
}

async function main(): Promise<void> {
  const consoleRes = await collectConsoleErrors(URL, 1500, 25000, CHROME);
  console.log(JSON.stringify(consoleRes, null, 2).slice(0, 900));
  check("console: ok envelope", consoleRes.ok === true);
  check("console: >= 2 entries (error + 404 log)", consoleRes.ok && consoleRes.count >= 2, String((consoleRes as any).count));
  check("console: truncated=false (small payload)", consoleRes.ok && (consoleRes as any).meta.truncated === false);

  const netRes = await collectNetworkFailures(URL, 1500, 500, 25000, CHROME);
  console.log(JSON.stringify(netRes, null, 2).slice(0, 900));
  check("network: ok envelope", netRes.ok === true);
  check("network: >= 2 failures (missing.png + /api/nope)", netRes.ok && netRes.count >= 2, String((netRes as any).count));
  if (netRes.ok) {
    const kinds = (netRes.data as any[]).map((f) => f.kind);
    check("network: http_error classified", kinds.includes("http_error"), JSON.stringify(kinds));
  }

  const perfRes = await collectPerformanceTrace(URL, 1200, 25000, CHROME);
  console.log(JSON.stringify(perfRes, null, 2).slice(0, 700));
  check("perf: ok envelope", perfRes.ok === true);
  check("perf: FCP numeric (mandate metric grounded)", perfRes.ok && typeof (perfRes as any).data.fcpMs === "number", JSON.stringify((perfRes as any).data?.fcpMs));
  check("perf: TTFB numeric", perfRes.ok && typeof (perfRes as any).data.ttfbMs === "number");

  // Graceful degradation: chrome binary that does not exist.
  const deadRes = await collectConsoleErrors(URL, 500, 5000, "/nonexistent/chrome-binary");
  check("degradation: structured unavailable envelope", deadRes.ok === false && (deadRes as any).available === false, JSON.stringify(deadRes).slice(0, 200));
  check("degradation: actionable hint present", typeof (deadRes as any).hint === "string" && (deadRes as any).hint.includes("DEVTOOLS_CHROME_PATH"));

  console.log(failures === 0 ? "\nSMOKE ALL PASS" : `\nSMOKE FAILED: ${failures}`);
  process.exit(failures === 0 ? 0 : 1);
}

main();
