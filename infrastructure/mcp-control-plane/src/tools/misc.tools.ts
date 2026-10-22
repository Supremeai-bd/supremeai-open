import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import {
  checkStripe,
  checkQdrant,
  checkVercel,
  checkFirecrawl,
  checkKaggle,
  pushKaggleKernel,
  getKaggleKernelStatus,
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

  server.tool(
    "misc.kaggle_push_kernel",
    "Push and run a script or notebook kernel on Kaggle GPU/TPU pool.",
    {
      username: z.string().describe("Kaggle username"),
      slug: z.string().describe("Kernel slug (e.g. supremeai-lora-eval)"),
      title: z.string().describe("Kernel title"),
      code: z.string().describe("Python code or notebook JSON string"),
      isNotebook: z.boolean().optional().describe("True if code is notebook JSON (default false)"),
    },
    async ({ username, slug, title, code, isNotebook }) => {
      try {
        const result = await pushKaggleKernel(username, slug, title, code, isNotebook ?? false);
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "misc.kaggle_kernel_status",
    "Check execution status and failure logs of a Kaggle kernel.",
    {
      username: z.string().describe("Kaggle username"),
      slug: z.string().describe("Kernel slug"),
    },
    async ({ username, slug }) => {
      try {
        const result = await getKaggleKernelStatus(username, slug);
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );
}

