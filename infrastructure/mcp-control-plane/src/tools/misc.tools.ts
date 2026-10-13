import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import {
  checkStripe,
  checkQdrant,
  checkVercel,
  checkFirecrawl,
  checkKaggle
} from "../adapters/misc/index.js";

export async function registerMiscTools(server: McpServer): Promise<void> {
  const tools = [
    { name: "misc.stripe", desc: "Check Stripe API", fn: checkStripe },
    { name: "misc.qdrant", desc: "Check Qdrant Vector DB", fn: checkQdrant },
    { name: "misc.vercel", desc: "Check Vercel API", fn: checkVercel },
    { name: "misc.firecrawl", desc: "Check Firecrawl API", fn: checkFirecrawl },
    { name: "misc.kaggle", desc: "Check Kaggle API", fn: checkKaggle },
  ];

  for (const t of tools) {
    server.tool(
      t.name,
      t.desc,
      {},
      async () => {
        try {
          const status = await t.fn();
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
}
