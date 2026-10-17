/**
 * AI delegation stub (issue #643 — zero-credential control plane).
 *
 * বাংলা মন্তব্য: MCP Control Tower একটি **zero-credential** ফেডারেশন টাস্ক-হাব
 * — সরাসরি LLM provider key pool (Gemini/Groq/OpenRouter/OpenAI/Anthropic/
 * GitHub Models/Mistral) এখানে থাকা উচিত নয় (#643)। AI analysis এখন
 * delegate করা হয় বাইরের agent-caller context-এ (বা Core API-তে)।
 *
 * এই মডিউল আগের public চুক্তি (listProviders / testProvider / getOrInitPool)
 * বজায় রাখে যাতে health engine ও smoke adapter-গুলোর import অটুট থাকে, কিন্তু
 * সৎভাবে জানায়: control plane-এ কোনো provider key নেই, কোনো inference হয় না।
 */

export const AI_DELEGATION_NOTICE =
  "AI analysis is delegated to the external agent caller context (or Core API) — the MCP Control Tower holds no direct LLM provider keys (#643).";

/** সবসময় খালি — control plane আর কোনো key pool ধারণ করে না (#643)। */
export function listProviders(): Array<{ provider: string; keyCount: number }> {
  return [];
}

/** সৎ delegation উত্তর — কোনো provider call হয় না। */
export async function testProvider(
  provider: string,
): Promise<{ provider: string; ok: false; delegated: true; error: string }> {
  return {
    provider,
    ok: false,
    delegated: true,
    error: AI_DELEGATION_NOTICE,
  };
}

/** Back-compat: আগে key pool ফেরত দিত; এখন সৎ null — কোনো pool নেই (#643)। */
export function getOrInitPool(_provider: string): null {
  return null;
}
