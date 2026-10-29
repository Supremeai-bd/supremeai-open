import { spawn, type ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { httpRequest } from "../../lib/http.js";
import { env } from "../../lib/env.js";

/**
 * #1673 — chrome-devtools-mcp as the tool backend for the devtools-audit skill.
 *
 * Zero-new-deps CDP (Chrome DevTools Protocol) client: speaks raw JSON over
 * the browser's remote-debugging WebSocket using Node's native WebSocket
 * (>= 21), after spawning a throwaway headless Chrome. This grounds the
 * loop's "human-eye FCP < 1.0s" mandate with lab data (performance trace,
 * console, network) instead of hand-rolled scraping.
 *
 * Graceful degradation is a hard requirement: the tower runs on hosts where
 * Chrome may not exist, so every failure surfaces as a structured
 * { available: false, reason } envelope — never a crash, never a hollow 200
 * (the silent-empty class, #2673: every success payload carries a non-empty
 * boundary assertion and an explicit truncated flag).
 */

// ─────────────────────────── pure helpers (unit-tested) ───────────────────────────

/** Chrome's DevToolsActivePort file: line 1 = port, line 2 = browser path. */
export function parseDevToolsActivePort(text: string): { port: number; browserPath: string } {
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  if (lines.length === 0) throw new Error("DevToolsActivePort file is empty");
  const port = Number(lines[0]);
  if (!Number.isInteger(port) || port <= 0 || port > 65535) {
    throw new Error(`DevToolsActivePort: invalid port ${JSON.stringify(lines[0])}`);
  }
  return { port, browserPath: lines[1] ?? "" };
}

export function buildChromeArgs(port: number, userDataDir: string): string[] {
  return [
    "--headless=new",
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${userDataDir}`,
    "--no-sandbox",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--window-size=1366,900",
    "about:blank",
  ];
}

export type NetworkFailure = {
  url: string;
  kind: "http_error" | "blocked" | "failed" | "slow";
  status?: number;
  method?: string;
  resourceType?: string;
  errorText?: string;
  durationMs?: number;
};

/**
 * Classify one finished/failed network exchange. Pure.
 * Precedence: blocked (CORS) > failed (net::ERR_*) > http_error (>= 400) > slow.
 */
export function classifyNetworkEntry(
  entry: {
    url: string;
    method?: string;
    resourceType?: string;
    status?: number;
    errorText?: string;
    blockedReason?: string;
    durationMs?: number;
  },
  slowMs: number
): NetworkFailure | null {
  const { url, method, resourceType, status, errorText, blockedReason, durationMs } = entry;
  if (blockedReason) {
    return { url, kind: "blocked", method, resourceType, status, errorText: blockedReason, durationMs };
  }
  if (errorText) {
    return { url, kind: "failed", method, resourceType, errorText, durationMs };
  }
  if (typeof status === "number" && status >= 400) {
    return { url, kind: "http_error", status, method, resourceType, durationMs };
  }
  if (typeof durationMs === "number" && durationMs > slowMs) {
    return { url, kind: "slow", status, method, resourceType, durationMs };
  }
  return null;
}

export type PerfSnapshot = {
  fcpMs: number | null;
  lcpMs: number | null;
  cls: number | null;
  ttfbMs: number | null;
  domContentLoadedMs: number | null;
  loadMs: number | null;
  scriptDurationMs: number | null;
  taskDurationMs: number | null;
  raw: Record<string, number>;
};

/**
 * Merge CDP Performance.getMetrics output with Navigation Timing v2 entries
 * into the flat lab-vitals snapshot the FCP < 1.0s mandate reads. Pure.
 */
export function mapPerformanceSnapshot(
  metrics: Array<{ name: string; value: number }>,
  navEntry: Record<string, number> | null,
  paintEntry?: { fcp: number | null; lcp: number | null }
): PerfSnapshot {
  const byName = new Map(metrics.map((m) => [m.name, m.value]));
  const nav = navEntry ?? {};
  const raw: Record<string, number> = {};
  for (const [k, v] of byName) {
    if (typeof v === "number" && Number.isFinite(v)) raw[k] = v;
  }
  for (const [k, v] of Object.entries(nav)) {
    if (typeof v === "number" && Number.isFinite(v)) raw[`nav.${k}`] = v;
  }
  const num = (x: unknown): number | null =>
    typeof x === "number" && Number.isFinite(x) && x >= 0 ? Math.round(x * 1000) / 1000 : null;
  return {
    // Chrome headless (>= 123) stopped emitting FirstContentfulPaint through
    // Performance.getMetrics; the page's paint-timing entries are the canonical
    // source. Prefer explicit paint values, fall back to CDP metrics.
    fcpMs: num(paintEntry?.fcp ?? byName.get("FirstContentfulPaint")),
    lcpMs: num(paintEntry?.lcp ?? byName.get("LargestContentfulPaint")),
    cls: num(byName.get("CumulativeLayoutShift")),
    taskDurationMs: num(byName.get("TaskDuration")),
    scriptDurationMs: num(byName.get("ScriptDuration")),
    ttfbMs: num(nav.responseStart),
    domContentLoadedMs: num(nav.domContentLoadedEventEnd),
    loadMs: num(nav.loadEventEnd),
    raw,
  };
}

/**
 * Honest truncation under a byte cap (silent-empty class guard, #2673).
 * Arrays: drop tail items until under cap — never silently drop; the
 * truncated flag always travels with the payload. Objects: returned as-is
 * with truncated=true (consumers read the flag and re-request narrower
 * arguments).
 */
export function truncateToCap<T>(payload: T, maxBytes: number): { payload: T; truncated: boolean } {
  const bytesOf = (x: unknown): number => Buffer.byteLength(JSON.stringify(x), "utf8");
  if (bytesOf(payload) <= maxBytes) return { payload, truncated: false };
  if (Array.isArray(payload)) {
    let kept = payload.slice();
    while (kept.length > 0) {
      kept = kept.slice(0, kept.length - 1);
      if (bytesOf(kept) <= maxBytes) return { payload: kept as unknown as T, truncated: true };
    }
    return { payload: [] as unknown as T, truncated: true };
  }
  return { payload, truncated: true };
}

// ─────────────────────────── live plumbing ───────────────────────────

type CdpEvent = { method: string; params: any };
type Pending = { resolve: (v: any) => void; reject: (e: Error) => void };

/** Minimal CDP-over-WebSocket session: id-matched commands + event tap. */
export class CdpSession {
  private ws: WebSocket;
  private nextId = 1;
  private pending = new Map<number, Pending>();
  private listeners = new Map<string, Array<(p: any) => void>>();
  readonly events: CdpEvent[] = [];

  private constructor(ws: WebSocket) {
    this.ws = ws;
    ws.addEventListener("message", (ev: MessageEvent) => {
      let msg: any;
      try {
        msg = JSON.parse(String(ev.data));
      } catch {
        return;
      }
      if (typeof msg.id === "number") {
        const p = this.pending.get(msg.id);
        if (!p) return;
        this.pending.delete(msg.id);
        if (msg.error) p.reject(new Error(`CDP ${msg.error.message ?? JSON.stringify(msg.error)}`));
        else p.resolve(msg.result);
        return;
      }
      if (typeof msg.method === "string") {
        this.events.push({ method: msg.method, params: msg.params });
        for (const fn of this.listeners.get(msg.method) ?? []) fn(msg.params);
        for (const fn of this.listeners.get("*") ?? []) fn(msg.params);
      }
    });
  }

  static connect(url: string, timeoutMs: number): Promise<CdpSession> {
    if (typeof WebSocket === "undefined") {
      return Promise.reject(new Error("devtools adapter requires Node >= 21 (native WebSocket)"));
    }
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url);
      const timer = setTimeout(() => {
        try { ws.close(); } catch { /* already closed */ }
        reject(new Error(`CDP WebSocket connect timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      ws.addEventListener("open", () => {
        clearTimeout(timer);
        resolve(new CdpSession(ws));
      });
      ws.addEventListener("error", () => {
        clearTimeout(timer);
        reject(new Error("CDP WebSocket connection failed"));
      });
    });
  }

  on(method: string, fn: (params: any) => void): void {
    const key = method === "*" ? "*" : method;
    const arr = this.listeners.get(key) ?? [];
    arr.push(fn);
    this.listeners.set(key, arr);
  }

  send(method: string, params: Record<string, unknown> = {}, sessionId?: string): Promise<any> {
    const id = this.nextId++;
    const msg: Record<string, unknown> = { id, method, params };
    if (sessionId) msg.sessionId = sessionId;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      try {
        this.ws.send(JSON.stringify(msg));
      } catch (err) {
        this.pending.delete(id);
        reject(err instanceof Error ? err : new Error(String(err)));
      }
    });
  }

  close(): void {
    try { this.ws.close(); } catch { /* best effort */ }
  }
}

export type ChromeHandle = {
  proc: ChildProcess;
  wsUrl: string;
  userDataDir: string;
  kill: () => void;
};

/** Spawn a throwaway headless Chrome and wait for its DevTools endpoint. */
export async function launchChrome(timeoutMs: number, chromePath?: string): Promise<ChromeHandle> {
  const bin = chromePath ?? env.devtools.chromePath;
  const userDataDir = mkdtempSync(join(tmpdir(), "cdp-audit-"));
  // Port 0 lets the kernel pick a free port; Chrome publishes the real one
  // in <userDataDir>/DevToolsActivePort.
  const proc = spawn(bin, buildChromeArgs(0, userDataDir), { stdio: "ignore" });
  // spawn() failures (ENOENT — no Chrome installed) arrive ASYNC as an 'error'
  // event; without this listener the whole tower process crashes. Capture and
  // surface through the structured degradation envelope instead. (Holder object:
  // TS cannot see callback assignments to a bare let, which narrows it to never.)
  const spawnState: { error: Error | null } = { error: null };
  proc.on("error", (e) => {
    spawnState.error = e;
  });

  const deadline = Date.now() + timeoutMs;
  const portFile = join(userDataDir, "DevToolsActivePort");
  let lastErr: Error | null = null;

  while (Date.now() < deadline) {
    if (spawnState.error) {
      rmSync(userDataDir, { recursive: true, force: true });
      throw new Error(`failed to spawn headless Chrome ('${bin}'): ${spawnState.error.message}`);
    }
    if (proc.exitCode !== null) {
      rmSync(userDataDir, { recursive: true, force: true });
      throw new Error(`headless Chrome exited immediately (code ${proc.exitCode}) — is '${bin}' a Chrome binary?`);
    }
    if (existsSync(portFile)) {
      try {
        const { port } = parseDevToolsActivePort(readFileSync(portFile, "utf8"));
        const ver = await httpRequest(`http://127.0.0.1:${port}/json/version`, {
          method: "GET",
          timeoutMs: 2000,
        });
        const wsUrl = (ver.data as any)?.webSocketDebuggerUrl;
        if (ver.ok && typeof wsUrl === "string" && wsUrl.length > 0) {
          return {
            proc,
            wsUrl,
            userDataDir,
            kill: () => {
              try { proc.kill("SIGKILL"); } catch { /* already gone */ }
              rmSync(userDataDir, { recursive: true, force: true });
            },
          };
        }
        lastErr = new Error(`DevTools endpoint answered but no webSocketDebuggerUrl (${ver.status})`);
      } catch (err) {
        lastErr = err instanceof Error ? err : new Error(String(err));
      }
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  try { proc.kill("SIGKILL"); } catch { /* already gone */ }
  rmSync(userDataDir, { recursive: true, force: true });
  throw new Error(`headless Chrome did not expose a DevTools endpoint within ${timeoutMs}ms${lastErr ? ` (last: ${lastErr.message})` : ""}`);
}
