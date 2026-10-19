import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { checkTelegram } from "../adapters/notify/index.js";
import { sendTelegram } from "../adapters/notify/actions.js";

export async function registerNotifyTools(server: McpServer): Promise<void> {
  server.tool(
    "notify.telegram",
    "Ping the Telegram Bot API to check bot token validity.",
    {},
    async () => {
      try {
        const status = await checkTelegram();
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
    "notify.send_telegram",
    "Send a message via Telegram bot to the configured (or a specific) chat.",
    {
      message: z.string().min(1).max(4000).describe("Message text"),
      chatId: z.string().optional().describe("Override chat id (default: TELEGRAM_CHAT_ID)"),
      parseMode: z.enum(["Markdown", "HTML"]).optional().describe("Optional parse mode"),
    },
    async ({ message, chatId, parseMode }) => {
      try {
        const result = await sendTelegram(message, chatId, parseMode);
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );
}
