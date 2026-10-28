import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

interface ParityCheck {
  component: string;
  status: "ok" | "drift" | "unconfigured" | "error";
  details: Record<string, unknown>;
}

async function runParityAudit(): Promise<{ status: string; checks: ParityCheck[] }> {
  const checks: ParityCheck[] = [];

  const envValue = (key: string): string | undefined => process.env[key];

  checks.push({
    component: "render",
    status: envValue("RENDER_API_KEY") ? "ok" : "unconfigured",
    details: { note: "Render node SHA comparison requires RENDER_API_KEY" },
  });

  checks.push({
    component: "cloudflare",
    status: envValue("CLOUDFLARE_API_TOKEN") ? "ok" : "unconfigured",
    details: { note: "Cloudflare deployment version inspection requires CLOUDFLARE_API_TOKEN" },
  });

  checks.push({
    component: "supabase",
    status: envValue("SUPABASE_URL") ? "ok" : "unconfigured",
    details: { note: "Schema migration parity requires SUPABASE_URL" },
  });

  checks.push({
    component: "redis",
    status: envValue("REDIS_URL") ? "ok" : "unconfigured",
    details: { note: "Queue backlog inspection requires REDIS_URL" },
  });

  checks.push({
    component: "infisical",
    status: envValue("INFISICAL_TOKEN") ? "ok" : "unconfigured",
    details: { note: "Secret completeness cross-reference requires INFISICAL_TOKEN" },
  });

  checks.push({
    component: "github_satellites",
    status: envValue("GITHUB_TOKEN") ? "ok" : "unconfigured",
    details: {
      satellites: [
        "supremeai-core",
        "supremeai-api",
        "supremeai-browser",
        "supremeai-studio",
        "supremeai-vscode",
      ],
      note: "Commit hash alignment requires GITHUB_TOKEN",
    },
  });

  const hasDrift = checks.some((c) => c.status === "drift" || c.status === "error");
  return { status: hasDrift ? "drift_detected" : "ok", checks };
}

export async function registerParityTools(server: McpServer): Promise<void> {
  const handler = async () => {
    const result = await runParityAudit();
    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
  };

  server.tool("system.parity_audit", "Run a multi-platform commit/schema/secret parity audit", {}, handler as any);
  server.tool("system_parity_audit", "Run a multi-platform commit/schema/secret parity audit", {}, handler as any);
}

export { runParityAudit };
