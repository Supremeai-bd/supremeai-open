import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { collectConsoleErrors, collectNetworkFailures, collectPerformanceTrace } from "../adapters/devtools/audit.js";

/**
 * #1673 — devtools.* tool family: chrome-devtools-mcp-grade lab data
 * (performance trace, console, network) backed by a zero-new-deps CDP
 * client (`adapters/devtools`). These are the tool backend the
 * devtools-audit skill's instruction body now points at first; the
 * hand-rolled audit.mjs stays as the offline/unreachable-host fallback.
 *
 * Every tool returns a structured envelope:
 *   ok=true  → { meta{truncated...}, data (non-empty boundary asserted), count }
 *   ok=false → { available:false, reason, hint } (Chrome missing → actionable hint)
 * — the silent-empty class (#2673) is structurally excluded.
 */
export function registerDevtoolsTools(server: McpServer): void {
  const common = {
    url: z.string().url().describe("Target URL to audit (must be reachable from this host)"),
    waitMs: z
      .number()
      .int()
      .min(250)
      .max(30000)
      .optional()
      .describe("Observation window after navigation (default 4000ms; longer for late-painting SPAs)"),
  };

  server.tool(
    "devtools.performance_trace",
    "Lab performance trace of a web page via headless Chrome CDP: FCP/LCP/CLS/TTFB, DOMContentLoaded, load, script/task durations. Grounds the human-eye FCP < 1.0s mandate with data.",
    {
      ...common,
      timeoutMs: z.number().int().min(2000).max(120000).optional().describe("Hard budget for launch+navigate+collect (default 30000ms)"),
    },
    { readOnlyHint: true, idempotentHint: true, openWorldHint: true },
    async ({ url, waitMs, timeoutMs }) => {
      const result = await collectPerformanceTrace(url, waitMs, timeoutMs);
      return {
        isError: !result.ok,
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
      };
    }
  );

  server.tool(
    "devtools.console_errors",
    "Console + exception sweep of a web page via headless Chrome CDP: console.error/warn, uncaught exceptions, browser Log entries with source URLs.",
    {
      ...common,
      timeoutMs: z.number().int().min(2000).max(120000).optional().describe("Hard budget for launch+navigate+collect (default 30000ms)"),
    },
    { readOnlyHint: true, idempotentHint: true, openWorldHint: true },
    async ({ url, waitMs, timeoutMs }) => {
      const result = await collectConsoleErrors(url, waitMs, timeoutMs);
      return {
        isError: !result.ok,
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
      };
    }
  );

  server.tool(
    "devtools.network_failures",
    "Network failure sweep of a web page via headless Chrome CDP: 4xx/5xx, CORS/blocked requests, net::ERR_* failures, slow requests above a threshold.",
    {
      ...common,
      slowMs: z.number().int().min(100).max(60000).optional().describe("Requests slower than this are flagged (default 1500ms)"),
      timeoutMs: z.number().int().min(2000).max(120000).optional().describe("Hard budget for launch+navigate+collect (default 30000ms)"),
    },
    { readOnlyHint: true, idempotentHint: true, openWorldHint: true },
    async ({ url, waitMs, slowMs, timeoutMs }) => {
      const result = await collectNetworkFailures(url, waitMs, slowMs, timeoutMs);
      return {
        isError: !result.ok,
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
      };
    }
  );
}
