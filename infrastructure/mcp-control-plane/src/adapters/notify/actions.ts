import { env } from "../../lib/env.js";
import { httpRequest } from "../../lib/http.js";

/**
 * Notify — активная отправка сообщений (не только health-проверки).
 * Telegram Bot API + Discord Webhook.
 */

export async function sendTelegram(
  message: string,
  chatId?: string,
  parseMode?: "Markdown" | "HTML"
): Promise<unknown> {
  const token = env.notify.telegramBotToken;
  if (!token) throw new Error("TELEGRAM_BOT_TOKEN is not configured.");
  const chat = chatId || env.notify.telegramChatId;
  if (!chat) throw new Error("TELEGRAM_CHAT_ID is not configured and no chatId was provided.");

  const res = await httpRequest(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: {
      chat_id: chat,
      text: message.slice(0, 4096),
      ...(parseMode ? { parse_mode: parseMode } : {}),
      disable_web_page_preview: true,
    },
    timeoutMs: 10_000,
  });

  const data = res.data as any;
  if (!data?.ok) throw new Error(`Telegram send failed: ${data?.description ?? res.status}`);
  return { ok: true, messageId: data.result?.message_id, chatId: chat, sentAt: new Date().toISOString() };
}

export async function sendWhatsApp(
  message: string,
  recipientPhone?: string
): Promise<unknown> {
  const { whatsappAccessToken, whatsappPhoneNumberId, whatsappRecipientPhone, whatsappWebhookUrl } = env.notify;
  const targetPhone = recipientPhone || whatsappRecipientPhone;

  // 1. Meta WhatsApp Cloud API
  if (whatsappPhoneNumberId && whatsappAccessToken) {
    if (!targetPhone) {
      throw new Error("WHATSAPP_RECIPIENT_PHONE is not configured and no recipientPhone provided.");
    }
    const cleanedPhone = targetPhone.replace(/[^0-9]/g, "");

    const res = await httpRequest(`https://graph.facebook.com/v20.0/${whatsappPhoneNumberId}/messages`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${whatsappAccessToken}`,
        "Content-Type": "application/json",
      },
      body: {
        messaging_product: "whatsapp",
        recipient_type: "individual",
        to: cleanedPhone,
        type: "text",
        text: { body: message.slice(0, 4096) },
      },
      timeoutMs: 10_000,
    });

    const data = res.data as any;
    if (!res.ok || data?.error) {
      throw new Error(`WhatsApp send failed: ${data?.error?.message || res.status}`);
    }
    return {
      ok: true,
      provider: "meta-cloud-api",
      messageId: data.messages?.[0]?.id,
      recipient: cleanedPhone,
      sentAt: new Date().toISOString(),
    };
  }

  // 2. Generic Webhook / Gateway
  if (whatsappWebhookUrl) {
    const res = await httpRequest(whatsappWebhookUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: {
        to: targetPhone,
        message: message.slice(0, 4096),
        text: message.slice(0, 4096),
      },
      timeoutMs: 10_000,
    });
    if (!res.ok) throw new Error(`WhatsApp webhook send failed: ${res.status}`);
    return {
      ok: true,
      provider: "webhook-gateway",
      sentAt: new Date().toISOString(),
    };
  }

  throw new Error("WhatsApp is not configured. Provide WHATSAPP_ACCESS_TOKEN + WHATSAPP_PHONE_NUMBER_ID or WHATSAPP_WEBHOOK_URL.");
}

export async function sendDiscord(message: string): Promise<unknown> {
  return { ok: false, error: "Discord is deprecated. Please use sendTelegram or sendWhatsApp instead." };
}