import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { auditSecrets, getSyncStatus } from "../adapters/infisical/index.js";

export async function registerInfisicalTools(server: McpServer): Promise<void> {
  server.tool(
    "infisical.audit_secrets",
    "Audit Infisical vault inventory via the v3 RAW path (metadata/keys only, no values); the standard-API status is reported separately in `standardPath` (vendor defect #434).",
    {},
    async () => {
      try {
        const secrets = await auditSecrets();
        return {
          content: [{ type: "text", text: JSON.stringify(secrets, null, 2) }],
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
    "infisical.sync_status",
    "Get the status of Infisical secret integrations/syncs.",
    {},
    async () => {
      try {
        const syncs = await getSyncStatus();
        return {
          content: [{ type: "text", text: JSON.stringify(syncs, null, 2) }],
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
