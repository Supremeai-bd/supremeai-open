/**
 * safeUrl — central URL allowlist helper for every dynamic `<a href>` (issue #2520).
 *
 * বাংলা মন্তব্য (থ্রেট মডেল): AI-সোর্স রিসার্চ, ফাইল লিস্ট, CI জব, ডেপ্লয়মেন্ট স্ট্যাটাস —
 * এইসব backend/মডেল-জেনারেটেড string সরাসরি href-এ গেলে attacker `javascript:alert(1)`
 * বা `data:text/html` জাতীয় URL ঢুকিয়ে script execution (XSS) করাতে পারে, কারণ ব্রাউজার
 * এই প্রোটোকলগুলোকে navigation-এ execute করে। নীতি: allowlist — শুধুমাত্র http:, https:,
 * mailto: অনুমোদিত; javascript:, data:, vbscript:, file: প্রভৃতি যেকোনো প্রোটোকল ও URL
 * parse-ব্যর্থতা fail-closed ("#") হয়। "#" দিয়ে শুরু হওয়া internal hash-route অক্ষত থাকে।
 */

const ALLOWED_PROTOCOLS: ReadonlySet<string> = new Set(['http:', 'https:', 'mailto:']);

export function safeUrl(raw: string | null | undefined): string {
  if (!raw) return '#';
  const trimmed = raw.trim();
  if (!trimmed) return '#';
  // বাংলা মন্তব্য: internal hash-route (যেমন '#/session/1') — SPA রুট, allowlist দরকার নেই
  if (trimmed.startsWith('#')) return trimmed;
  try {
    const parsed = new URL(trimmed, window.location.origin);
    if (!ALLOWED_PROTOCOLS.has(parsed.protocol)) return '#';
    return parsed.href;
  } catch {
    return '#';
  }
}
