import { CdpSession, launchChrome, classifyNetworkEntry, mapPerformanceSnapshot, truncateToCap } from "./cdp.js";
import { env } from "../../lib/env.js";
import type { NetworkFailure, PerfSnapshot } from "./cdp.js";

/**
 * #1673 — page-level audit collectors over the zero-dep CDP client.
 * Each collector: launch throwaway headless Chrome → attach → enable the
 * domain(s) → navigate → observe for waitMs → close → structured envelope.
 * The Bangla-report-to-Telegram contract of the devtools-audit skill stays
 * upstream; these tools are the lab-data backend it reads from.
 */

export type AuditMeta = {
  url: string;
  chrome: string;
  waitMs: number;
  durationMs: number;
  truncated: boolean;
};

export type ConsoleEntry = {
  type: string;
  text: string;
  url?: string;
  line?: number;
  column?: number;
  ts: string;
};

export type AuditResult =
  | { ok: true; meta: AuditMeta; data: unknown; count: number }
  | { ok: false; available: false; reason: string; hint?: string };

const CONSOLE_TYPES = new Set(["error", "warning"]);

/** Attach to a fresh page target and return (session, closeAll). */
async function withPage<T>(
  url: string,
  waitMs: number,
  timeoutMs: number,
  chromePath: string | undefined,
  fn: (session: CdpSession, sessionId: string) => Promise<T>
): Promise<T> {
  const handle = await launchChrome(timeoutMs, chromePath);
  const deadline = Date.now() + timeoutMs;
  try {
    const browser = await CdpSession.connect(handle.wsUrl, 5000);
    try {
      const { targetId } = await browser.send("Target.createTarget", { url: "about:blank" });
      const { sessionId } = await browser.send("Target.attachToTarget", {
        targetId,
        flatten: true,
      });
      const out = await Promise.race([
        fn(browser, sessionId),
        new Promise<never>((_, rej) =>
          setTimeout(() => rej(new Error(`audit exceeded ${timeoutMs}ms budget`)), Math.max(deadline - Date.now(), 0))
        ),
      ]);
      return out;
    } finally {
      browser.close();
    }
  } finally {
    handle.kill();
  }
}

async function navigate(session: CdpSession, sessionId: string, url: string, waitMs: number): Promise<void> {
  await session.send("Page.enable", {}, sessionId);
  await session.send("Runtime.enable", {}, sessionId);
  // Navigate, then hold the session open for waitMs so late consoles/network
  // and paint metrics land. waitNetworkIdle keeps slow SPAs from being cut
  // mid-paint: if a request fires in the last 500ms of each probe window,
  // extend up to waitMs total (bounded — never unbounded tail latency).
  const done = session.send("Page.navigate", { url }, sessionId);
  await done;
  await new Promise((r) => setTimeout(r, waitMs));
}

/** devtools.console_errors — console.error/warn, uncaught exceptions, Log entries. */
export async function collectConsoleErrors(
  url: string,
  waitMs?: number,
  timeoutMs?: number,
  chromePath?: string
): Promise<AuditResult> {
  const started = Date.now();
  const wait = waitMs ?? env.devtools.defaultWaitMs;
  const budget = timeoutMs ?? env.devtools.defaultTimeoutMs;
  try {
    const data = await withPage(url, wait, budget, chromePath, async (session, sessionId) => {
      const entries: ConsoleEntry[] = [];
      session.on("Runtime.consoleAPICalled", (p: any) => {
        if (!CONSOLE_TYPES.has(p?.type)) return;
        const text = (p?.args ?? [])
          .map((a: any) => a?.value ?? a?.description ?? a?.unserializableValue ?? "")
          .join(" ")
          .slice(0, 500);
        entries.push({ type: p.type, text, url: p?.stackTrace?.callFrames?.[0]?.url, line: p?.stackTrace?.callFrames?.[0]?.lineNumber, ts: new Date().toISOString() });
      });
      session.on("Runtime.exceptionThrown", (p: any) => {
        const d = p?.exceptionDetails;
        entries.push({
          type: "exception",
          text: String(d?.exception?.description ?? d?.text ?? "uncaught exception").slice(0, 500),
          url: d?.url,
          line: d?.lineNumber,
          ts: new Date().toISOString(),
        });
      });
      session.on("Log.entryAdded", (p: any) => {
        const e = p?.entry;
        if (e?.level !== "error" && e?.level !== "warning") return;
        entries.push({ type: `log.${e.level}`, text: String(e.text ?? "").slice(0, 500), url: e?.url, ts: new Date().toISOString() });
      });
      await session.send("Log.enable", {}, sessionId);
      await navigate(session, sessionId, url, wait);
      return entries;
    });
    const { payload, truncated } = truncate(data, env.devtools.resultCapBytes);
    return {
      ok: true,
      count: payload.length,
      meta: { url, chrome: chromePath ?? env.devtools.chromePath, waitMs: wait, durationMs: Date.now() - started, truncated },
      data: payload,
    };
  } catch (err) {
    return failureEnvelope(err, chromePath);
  }
}

/** devtools.network_failures — 4xx/5xx, blocked/CORS, net::ERR_*, slow requests. */
export async function collectNetworkFailures(
  url: string,
  waitMs?: number,
  slowMs?: number,
  timeoutMs?: number,
  chromePath?: string
): Promise<AuditResult> {
  const started = Date.now();
  const wait = waitMs ?? env.devtools.defaultWaitMs;
  const budget = timeoutMs ?? env.devtools.defaultTimeoutMs;
  const slow = slowMs ?? env.devtools.slowRequestMs;
  try {
    const data = await withPage(url, wait, budget, chromePath, async (session, sessionId) => {
      const inflight = new Map<string, { url: string; method: string; resourceType?: string; ts: number }>();
      const failures: NetworkFailure[] = [];
      const finished = new Set<string>();
      session.on("Network.requestWillBeSent", (p: any) => {
        inflight.set(p.requestId, { url: p.request.url, method: p.request.method, ts: Date.now() });
      });
      session.on("Network.responseReceived", (p: any) => {
        const req = inflight.get(p.requestId);
        const status: number = p.response.status;
        const durationMs = req ? Date.now() - req.ts : undefined;
        const f = classifyNetworkEntry(
          {
            url: p.response.url,
            method: req?.method,
            resourceType: p.type,
            status,
            durationMs,
          },
          slow
        );
        if (f) failures.push(f);
        finished.add(p.requestId);
      });
      session.on("Network.loadingFailed", (p: any) => {
        const req = inflight.get(p.requestId);
        const f = classifyNetworkEntry(
          {
            url: req?.url ?? "(unknown)",
            method: req?.method,
            resourceType: p.type,
            errorText: p.errorText ?? p.blockedReason ?? `loadingFailed(${p.canceled ? "canceled" : "failed"})`,
            blockedReason: p.blockedReason,
            durationMs: req ? Date.now() - req.ts : undefined,
          },
          slow
        );
        if (f) failures.push(f);
        finished.add(p.requestId);
      });
      await session.send("Network.enable", {}, sessionId);
      await navigate(session, sessionId, url, wait);
      return failures;
    });
    const { payload, truncated } = truncate(data, env.devtools.resultCapBytes);
    return {
      ok: true,
      count: payload.length,
      meta: { url, chrome: chromePath ?? env.devtools.chromePath, waitMs: wait, durationMs: Date.now() - started, truncated },
      data: payload,
    };
  } catch (err) {
    return failureEnvelope(err, chromePath);
  }
}

/** devtools.performance_trace — FCP/LCP/CLS/TTFB + paint timing lab vitals. */
export async function collectPerformanceTrace(
  url: string,
  waitMs?: number,
  timeoutMs?: number,
  chromePath?: string
): Promise<AuditResult> {
  const started = Date.now();
  const wait = waitMs ?? env.devtools.defaultWaitMs;
  const budget = timeoutMs ?? env.devtools.defaultTimeoutMs;
  try {
    const data = await withPage(url, wait, budget, chromePath, async (session, sessionId) => {
      await session.send("Performance.enable", {}, sessionId);
      await navigate(session, sessionId, url, wait);
      const { metrics } = await session.send("Performance.getMetrics", {}, sessionId);
      let navEntry: Record<string, number> | null = null;
      let paintEntry: { fcp: number | null; lcp: number | null } = { fcp: null, lcp: null };
      try {
        const evalRes = await session.send(
          "Runtime.evaluate",
          {
            expression: `(async () => {
              let lcp = null;
              try {
                await new Promise((resolve) => {
                  const po = new PerformanceObserver((list) => {
                    const entries = list.getEntries();
                    if (entries.length) lcp = entries[entries.length - 1].startTime;
                    resolve();
                  });
                  po.observe({ type: 'largest-contentful-paint', buffered: true });
                  setTimeout(resolve, 100);
                });
              } catch (e) {}
              const paints = performance.getEntriesByType('paint');
              return JSON.stringify({
                fcp: paints.find((e) => e.name === 'first-contentful-paint')?.startTime ?? null,
                lcp,
                nav: performance.getEntriesByType('navigation')[0]?.toJSON() ?? null,
              });
            })()`,
            awaitPromise: true,
            returnByValue: true,
          },
          sessionId
        );
        const raw = evalRes?.result?.value;
        if (typeof raw === "string" && raw !== "null") {
          const full = JSON.parse(raw);
          paintEntry = { fcp: full.fcp ?? null, lcp: full.lcp ?? null };
          if (full.nav) {
            // Keep the timing deltas the mandate reads; drop noisy bulk fields.
            navEntry = {
              responseStart: full.nav.responseStart,
              domContentLoadedEventEnd: full.nav.domContentLoadedEventEnd,
              loadEventEnd: full.nav.loadEventEnd,
            };
          }
        }
      } catch {
        // Navigation Timing unavailable (e.g. about:blank edge) — metrics-only snapshot.
      }
      const snap: PerfSnapshot = mapPerformanceSnapshot(metrics ?? [], navEntry, paintEntry);
      return snap;
    });
    const { payload, truncated } = truncate(data, env.devtools.resultCapBytes);
    return {
      ok: true,
      count: 1,
      meta: { url, chrome: chromePath ?? env.devtools.chromePath, waitMs: wait, durationMs: Date.now() - started, truncated },
      data: payload,
    };
  } catch (err) {
    return failureEnvelope(err, chromePath);
  }
}

// ─────────────────────────── shared internals ───────────────────────────

function truncate<T>(data: T, capBytes: number): { payload: T; truncated: boolean } {
  // Delegates to the unified pure helper (#2673 honest truncation).
  return truncateToCap(data, capBytes);
}

function failureEnvelope(err: unknown, chromePath?: string): AuditResult {
  const message = err instanceof Error ? err.message : String(err);
  const chromeMissing =
    /exited immediately|ENOENT|not a Chrome binary|did not expose a DevTools endpoint/i.test(message);
  return {
    ok: false,
    available: false,
    reason: message.slice(0, 500),
    hint: chromeMissing
      ? `Install Chrome or set DEVTOOLS_CHROME_PATH (tried: '${chromePath ?? env.devtools.chromePath}'). The devtools-audit skill's local audit.mjs remains the offline fallback.`
      : undefined,
  };
}
