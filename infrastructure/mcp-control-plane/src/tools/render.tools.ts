import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import {
  listServices,
  getServiceHealth,
  getDeployLogs,
  getServiceEnvVars,
  listLogs,
  RenderLogFilters,
} from "../adapters/render/index.js";

/** Shared shape for the render.get_logs optional filter block. */
const renderLogFiltersSchema = {
  startTime: z
    .string()
    .optional()
    .describe("ISO 8601 window start (default: 15 minutes ago)"),
  endTime: z.string().optional().describe("ISO 8601 window end (default: now)"),
  level: z
    .enum(["debug", "info", "warning", "error"])
    .optional()
    .describe("Severity filter (default: all levels)"),
  type: z
    .enum(["app", "build"])
    .optional()
    .describe("app = runtime logs, build = deploy/build logs (default: both). Public HTTP request logs need a Render Pro workspace and are intentionally not exposed."),
  text: z.string().optional().describe("Substring search inside log messages"),
  limit: z
    .number()
    .int()
    .min(1)
    .max(100)
    .optional()
    .describe("Max entries per page (default 50, API cap 100)"),
  cursor: z.string().optional().describe("Pagination cursor returned by a previous call"),
};

export async function registerRenderTools(server: McpServer): Promise<void> {
  server.tool(
    "render.list_services",
    "List all services in a specific Render account.",
    {
      accountId: z.string().describe("The account ID (e.g. render-primary)"),
    },
    async ({ accountId }) => {
      try {
        const services = await listServices(accountId);
        return {
          content: [{ type: "text", text: JSON.stringify(services, null, 2) }],
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );

  server.tool(
    "render.service_health",
    "Get detailed health and deploy status for a specific Render service.",
    {
      accountId: z.string().describe("The account ID (e.g. render-primary)"),
      serviceId: z.string().describe("The Render service ID (e.g. srv-abc12345)"),
    },
    async ({ accountId, serviceId }) => {
      try {
        const health = await getServiceHealth(accountId, serviceId);
        return {
          content: [{ type: "text", text: JSON.stringify(health, null, 2) }],
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );

  server.tool(
    "render.get_logs",
    "Query REAL Render application/build logs for a service (GET /v1/logs — not deploy metadata). Supports time window, severity, log type and text search; output is secret-sanitized and read-only.",
    {
      accountId: z.string().describe("The account ID (e.g. render-primary)"),
      serviceId: z.string().describe("The Render service ID (e.g. srv-abc12345)"),
      ...renderLogFiltersSchema,
    },
    async ({ accountId, serviceId, startTime, endTime, level, type, text, limit, cursor }) => {
      try {
        const filters: RenderLogFilters = { startTime, endTime, level, type, text, limit, cursor };
        const result = await listLogs(accountId, serviceId, filters);
        return {
          content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );

  server.tool(
    "render.get_env_vars",
    "List environment variable keys and values for a Render service (Read-Only).",
    {
      accountId: z.string().describe("The account ID (e.g. render-primary)"),
      serviceId: z.string().describe("The Render service ID (e.g. srv-abc12345)"),
    },
    async ({ accountId, serviceId }) => {
      try {
        const envVars = await getServiceEnvVars(accountId, serviceId);
        return {
          content: [{ type: "text", text: JSON.stringify(envVars, null, 2) }],
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );
}

