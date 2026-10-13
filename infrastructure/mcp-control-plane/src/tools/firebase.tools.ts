import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { getAuthStatus, getHostingStatus } from "../adapters/firebase/index.js";

export async function registerFirebaseTools(server: McpServer): Promise<void> {
  server.tool(
    "firebase.auth_status",
    "Check Firebase Authentication status and connectivity.",
    {},
    async () => {
      try {
        const status = await getAuthStatus();
        return {
          content: [{ type: "text", text: JSON.stringify(status, null, 2) }],
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
    "firebase.hosting_status",
    "Check Firebase Hosting/Admin SDK status.",
    {},
    async () => {
      try {
        const status = await getHostingStatus();
        return {
          content: [{ type: "text", text: JSON.stringify(status, null, 2) }],
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
