import type { IncomingMessage } from "node:http";
import { getOrCreateGuestClient, type ClientProtocol, type ExternalClient } from "./client-registry.js";
import { profileForProvider } from "./tool-visibility.js";

/**
 * Vendor-agnostic auto-registration for no-auth AI clients (#2588).
 *
 * Architectural principle (founder guidance on #2588): the tower is
 * PROTOCOL-driven, not vendor-driven. Any AI that speaks one of our universal
 * transports —
 *   • `streamable-http` (POST /mcp — modern MCP spec: Cursor, Claude Desktop,
 *     VS Code, Gemini Spark, …)
 *   • `sse` (GET /sse — legacy MCP SSE: xAI Grok, Claude Web, web connectors)
 *   • `stdio` (local stdio bridge)
 * — is ACCEPTED by transport type alone. No vendor gets special handling and
 * no manual registry entry is ever required: every connect auto-registers a
 * database record (provider label, protocol, client id, IP, timestamps).
 *
 * The signature table below is therefore COSMETIC ONLY — it assigns a nicer
 * display label for well-known clients. Unknown clients still auto-register
 * with the `generic` provider label. Adding a future AI requires zero code
 * change: it simply shows up as `generic` until (optionally) a label entry
 * is added here.
 */
const PROVIDER_SIGNATURES: ReadonlyArray<{ readonly match: readonly string[]; readonly provider: string; readonly label: string }> = [
  { match: ["grok", "xai"], provider: "xai", label: "xAI Grok Web" },
  { match: ["chatgpt", "openai"], provider: "chatgpt", label: "ChatGPT Web" },
  { match: ["claude"], provider: "claude", label: "Claude Web" },
  { match: ["gemini"], provider: "gemini", label: "Gemini Web" },
  { match: ["cursor"], provider: "cursor", label: "Cursor" },
  { match: ["copilot"], provider: "copilot", label: "GitHub Copilot" },
  { match: ["windsurf"], provider: "windsurf", label: "Windsurf" },
  { match: ["cline"], provider: "cline", label: "Cline" },
  { match: ["vscode", "vs code", "code/"], provider: "vscode", label: "VS Code" },
  { match: ["deepseek"], provider: "deepseek", label: "DeepSeek" },
  { match: ["mistral"], provider: "mistral", label: "Mistral" },
  { match: ["z.ai"], provider: "zai", label: "Z.ai" },
  { match: ["qwen"], provider: "qwen", label: "Qwen" },
  { match: ["kimi", "moonshot"], provider: "moonshot", label: "Moonshot Kimi" },
  { match: ["openrouter"], provider: "openrouter", label: "OpenRouter" },
];

/** Best-effort provider LABEL for dashboards. Unknown ⇒ generic (never blocks acceptance). */
export function detectProviderLabel(userAgent: string): { provider: string; label: string } {
  const ua = userAgent.toLowerCase();
  for (const signature of PROVIDER_SIGNATURES) {
    if (signature.match.some((needle) => ua.includes(needle))) {
      return { provider: signature.provider, label: signature.label };
    }
  }
  return { provider: "generic", label: "AI Guest" };
}

/**
 * #110 Part 2 — Named Client Identity (?client=<name>).
 *
 * বাংলা মন্তব্য: বাহ্যিক AI ক্লায়েন্ট (Claude Web, Grok, ChatGPT...) এখন ক্লিন URL
 * (?client=groq_main) দিয়ে সংযোগ দিতে পারবে — কোনো টোকেন বা হেডার লাগবে না।
 * রেজিস্ট্রিতে স্থায়ী `named_<name>` রেকর্ড তৈরি/বাঁধা হয়, তাই ক্লাউড ইগ্রেস IP
 * যতই ঘুরুক, রোল-আপগ্রেড আর হারাবে না (IP-ভিত্তিক guest_ id-এর IP-drift demotion
 * সমস্যার স্থায়ী সমাধান)। রোল প্রমোশন কেবলমাত্র ডেটাবেস (registry store) থেকেই নিয়ন্ত্রিত হয়।
 *
 * Security: the name is strictly sanitized (`^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$`)
 * so it can never smuggle path separators, control chars, or registry-key
 * collisions (a rejected/absent name degrades to the legacy IP-guest path —
 * fail-open to the SAFER default, never to privilege).
 */
const NAMED_CLIENT_RE = /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$/;

export function isValidClientName(name: string): boolean {
  return NAMED_CLIENT_RE.test(name);
}

/**
 * Extracts a validated named-client identity from a raw request URL.
 * Returns `null` when the URL is absent, has no `client` query param, or the
 * value fails sanitization — callers then fall back to IP-based guests.
 */
export function namedClientFromUrl(rawUrl: string | undefined | null): { name: string; id: string } | null {
  if (!rawUrl) return null;
  let parsed: URL;
  try {
    // Base is irrelevant — only search params matter; tolerate scheme-less paths.
    parsed = new URL(rawUrl, "https://tower.invalid");
  } catch {
    return null;
  }
  const name = parsed.searchParams.get("client")?.trim() ?? "";
  if (!name || !isValidClientName(name)) return null;
  return { name, id: `named_${name}` };
}

/**
 * Real client IP behind Render/Cloudflare proxies (moved here so the shared
 * auto-register hook and the /mcp rate limiter use ONE definition).
 */
export function clientIpFor(req: IncomingMessage): string {
  const forwarded = req.headers["x-forwarded-for"];
  if (typeof forwarded === "string" && forwarded.trim()) {
    return forwarded.split(",")[0].trim();
  }
  return req.socket.remoteAddress ?? "unknown";
}

/**
 * Shared auto-registration hook (#1767 for /sse, #2588 for /mcp).
 *
 * Called on connection establishment (SSE GET handshake or streamable-HTTP
 * `initialize`) for clients that present NO bearer token. Creates or reuses
 * an active guest record in the client registry so admins can see, monitor
 * and dynamically re-role any connected AI from the dashboard — with zero
 * manual registration.
 *
 * #110 Part 2: when the request URL carries `?client=<name>` the hook binds
 * the connection to the PERSISTENT named record `named_<name>` instead of the
 * IP-derived guest id — zero tokens, zero headers, IP-drift-immune identity.
 * Role promotions made by admins survive reconnects from ANY IP because the
 * registry record (the database, per the issue contract) is keyed by the
 * stable name, not by network coordinates.
 */
export function autoRegisterGuestClient(
  req: IncomingMessage,
  protocol: ClientProtocol,
  tenantId = "tenant_default",
): ExternalClient {
  const { provider, label } = detectProviderLabel(String(req.headers["user-agent"] ?? ""));
  // Tool Exposure Policy: chatgpt guests get the curated discovery surface by
  // default (derive-once — admin-set profiles are never clobbered, see
  // getOrCreateGuestClient). Every other provider keeps the full surface.
  const toolProfile = profileForProvider(provider);

  // #110: named identity path — stable `named_<name>` id wins over IP guests.
  const named = namedClientFromUrl(req.url);
  if (named) {
    const guestName = `Named Client: ${named.name} (${label})`;
    return getOrCreateGuestClient(named.id, guestName, provider, protocol, tenantId, toolProfile);
  }

  const clientIp = clientIpFor(req).replace(/[^a-zA-Z0-9]/g, "_");
  const guestId = `guest_${provider}_${clientIp.slice(0, 12)}`;
  const guestName = `${label} Client (${clientIp})`;
  return getOrCreateGuestClient(guestId, guestName, provider, protocol, tenantId, toolProfile);
}
