import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { checkTelegram, checkWhatsApp } from "../adapters/notify/index.js";
import { sendTelegram, sendWhatsApp } from "../adapters/notify/actions.js";

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

  server.tool(
    "notify.whatsapp",
    "Ping the WhatsApp Cloud API / Webhook to check validity. Honest precondition: returns status 'unconfigured' (never throws) until WHATSAPP_ACCESS_TOKEN or WHATSAPP_WEBHOOK_URL env refs are provisioned in the tower env (docs/TOWER_HEALTH_RUNBOOK.md §5).",
    {},
    async () => {
      try {
        const status = await checkWhatsApp();
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
    "notify.send_whatsapp",
    "Send a message via WhatsApp Bot (Meta Cloud API or Webhook Gateway) to configured recipient. Honest precondition: requires WHATSAPP_ACCESS_TOKEN (+ WHATSAPP_WEBHOOK_URL) env provisioning — fails honestly with 'unconfigured' until then; do not schedule this lane in unprovisioned environments (docs/TOWER_HEALTH_RUNBOOK.md §5).",
    {
      message: z.string().min(1).max(4000).describe("Message text"),
      recipientPhone: z.string().optional().describe("Recipient phone number with country code (e.g. 88017XXXXXXXX)"),
    },
    async ({ message, recipientPhone }) => {
      try {
        const result = await sendWhatsApp(message, recipientPhone);
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );
}
