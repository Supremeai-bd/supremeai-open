import { env } from "../../lib/env.js";
import { httpRequest } from "../../lib/http.js";
import { ApprovalRequest } from "./lifecycle.js";
import { signApprovalLink } from "./signing.js";
import { RiskLevel } from "../risk.engine.js";

export class HITLManager {
  /**
   * Sends an approval request to the configured Telegram chat.
   */
  public async requestApproval(request: ApprovalRequest, riskLevel: RiskLevel): Promise<void> {
    const { telegramBotToken, telegramChatId } = env.notify;

    const baseUrl = env.render.controlTower.url || process.env["MCP_URL"] || `http://localhost:${env.port}`;
    // SECURITY: links carry a per-request, expiring HMAC signature — never the
    // permanent admin key. See policy/approvals/signing.ts.
    const base = baseUrl.replace(/\/+$/, "");
    const approveUrl = `${base}/approve?id=${request.id}&${signApprovalLink(request.id, "APPROVED")}`;
    const rejectUrl = `${base}/approve?id=${request.id}&decision=REJECTED&${signApprovalLink(request.id, "REJECTED")}`;

    // Construct the message
    const message = `🚨 **Approval Required (${riskLevel})**\n\n`
      + `**Provider:** ${request.context.provider}\n`
      + `**Action:** ${request.context.action}\n`
      + `**Request ID:** \`${request.id}\`\n\n`
      + `To approve via IDE, tell SupremeAI: "Approve ${request.id}"\n\n`
      + `🔗 **Actions:**\n`
      + `✅ [Approve Request](${approveUrl})\n`
      + `❌ [Reject Request](${rejectUrl})`;

    console.warn(`[HITL] Created Approval Request: ${request.id}`);

    // If Telegram is configured, send the message
    if (telegramBotToken && telegramChatId) {
      try {
        await httpRequest(`https://api.telegram.org/bot${telegramBotToken}/sendMessage`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: {
            chat_id: telegramChatId,
            text: message,
            parse_mode: "Markdown"
          },
          timeoutMs: 5000
        });
        console.log(`[HITL] Approval request sent to Telegram.`);
      } catch (err: any) {
        console.error(`[HITL] Failed to send Telegram message: ${err.message}`);
      }
    } else {
      console.log(`[HITL] Telegram not configured. Approval request printed to console only.`);
      console.log(message);
    }
  }
}

export const globalHITLManager = new HITLManager();
