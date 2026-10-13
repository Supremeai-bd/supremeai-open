import { env } from "../../lib/env.js";
import { httpRequest } from "../../lib/http.js";

export async function checkTelegram(): Promise<unknown> {
  const { telegramBotToken } = env.notify;
  if (!telegramBotToken) {
    throw new Error("TELEGRAM_BOT_TOKEN is not configured.");
  }

  const start = Date.now();
  // Using getMe to verify the bot token
  const res = await httpRequest(`https://api.telegram.org/bot${telegramBotToken}/getMe`);
  
  const data = res.data as any;
  if (data.ok) {
    return {
      status: "healthy",
      botUsername: data.result.username,
      latencyMs: Date.now() - start
    };
  }
  
  throw new Error(`Telegram API Error: ${data.description}`);
}

export async function checkWhatsApp(): Promise<unknown> {
  const { whatsappAccessToken, whatsappPhoneNumberId, whatsappWebhookUrl } = env.notify;
  if (!whatsappAccessToken && !whatsappWebhookUrl) {
    throw new Error("Neither WHATSAPP_ACCESS_TOKEN nor WHATSAPP_WEBHOOK_URL is configured.");
  }

  const start = Date.now();
  if (whatsappPhoneNumberId && whatsappAccessToken) {
    const res = await httpRequest(`https://graph.facebook.com/v20.0/${whatsappPhoneNumberId}`, {
      headers: { Authorization: `Bearer ${whatsappAccessToken}` },
    });
    const data = res.data as any;
    if (res.ok && data?.id) {
      return {
        status: "healthy",
        provider: "meta-cloud-api",
        phoneNumberId: data.id,
        verifiedName: data.verified_name || data.display_phone_number,
        latencyMs: Date.now() - start,
      };
    }
    throw new Error(`WhatsApp Meta API Error: ${JSON.stringify(data)}`);
  }

  if (whatsappWebhookUrl) {
    const res = await httpRequest(whatsappWebhookUrl);
    return {
      status: res.ok ? "healthy" : "degraded",
      provider: "webhook-gateway",
      latencyMs: Date.now() - start,
    };
  }

  throw new Error("WHATSAPP_PHONE_NUMBER_ID is required for Meta Cloud API.");
}

export async function checkDiscord(): Promise<unknown> {
  return { status: "deprecated", message: "Discord has been replaced with WhatsApp + Telegram." };
}
