import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { listProviders, testProvider } from "../adapters/ai/index.js";
import { analyzeWithAI, listConfiguredAnalysisProviders } from "../adapters/ai/analyze.js";

export async function registerAITools(server: McpServer): Promise<void> {
  server.tool(
    "ai.list_providers",
    "List all configured AI providers and the number of keys available in their pools.",
    {},
    async () => {
      try {
        const providers = listProviders();
        return {
          content: [{ type: "text", text: JSON.stringify(providers, null, 2) }],
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
    "ai.test_provider",
    "Test an AI provider's API to ensure the keys in the pool are valid and working (tests models endpoint).",
    {
      provider: z.string().describe("The provider to test, e.g. gemini, groq, openrouter, github, mistral"),
    },
    async ({ provider }) => {
      try {
        const result = await testProvider(provider);
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
    "ai.analyze_code",
    "Analyze code/docs using AI (Gemini → Groq → OpenRouter → GitHub Models fallback chain). Extracts best practices, patterns, improvements.",
    {
      task: z.string().describe("Analysis task, e.g. 'extract best practices and architecture patterns'"),
      content: z.string().describe("Code or documentation text to analyze"),
      provider: z.string().optional().describe("Preferred provider: gemini, groq, openrouter, github, auto (default)"),
    },
    async ({ task, content, provider }) => {
      try {
        const result = await analyzeWithAI(task, content, provider ?? "auto");
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "ai.available_providers",
    "List AI providers configured for analysis (with available key counts and fallback order).",
    {},
    async () => {
      try {
        return {
          content: [{
            type: "text",
            text: JSON.stringify({
              analysisProviders: listConfiguredAnalysisProviders(),
              providerPools: listProviders(),
            }, null, 2),
          }],
        };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );
}

