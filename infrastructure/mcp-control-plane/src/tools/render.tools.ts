import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { listServices, getServiceHealth, getDeployLogs, getServiceEnvVars } from "../adapters/render/index.js";

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
    "Get the latest deploy logs for a specific Render service.",
    {
      accountId: z.string().describe("The account ID (e.g. render-primary)"),
      serviceId: z.string().describe("The Render service ID (e.g. srv-abc12345)"),
    },
    async ({ accountId, serviceId }) => {
      try {
        const logs = await getDeployLogs(accountId, serviceId);
        return {
          content: [{ type: "text", text: JSON.stringify(logs, null, 2) }],
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

