import { env } from "../../lib/env.js";
import { httpRequest } from "../../lib/http.js";
import { AIKeyPool } from "./key-pool.js";

/**
 * Provider-Agnostic AI Analyze/Complete.
 *
 * Использует уже настроенные pool'ы ключей (gemini, groq, openrouter,
 * github models) в порядке приоритета с fallback-цепочкой.
 * $0-cost: gemini free tier первый, groq free второй, остальные после.
 */

interface ProviderSpec {
  name: string;
  baseUrl: string;
  model: string;
  buildBody: (system: string, user: string) => Record<string, unknown>;
  parseContent: (data: any) => string;
  header: (key: string) => Record<string, string>;
  priority: number;
}

function geminiProvider(): ProviderSpec {
  return {
    name: "gemini",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/models",
    model: env.ai.geminiModel,
    priority: 10,
    buildBody: (system, user) => ({ contents: [{ role: "user", parts: [{ text: `${system}\n\n${user}` }] }] }),
    parseContent: (data) => data?.candidates?.[0]?.content?.parts?.[0]?.text || JSON.stringify(data).slice(0, 1000),
    header: () => ({ "Content-Type": "application/json" }),
  };
}

function openaiCompatProvider(name: string, baseUrl: string, model: string, priority: number): ProviderSpec {
  return {
    name,
    baseUrl,
    model,
    priority,
    buildBody: (system, user) => ({
      model,
      messages: [{ role: "system", content: system }, { role: "user", content: user }],
      max_tokens: 4096,
      temperature: 0.3,
    }),
    parseContent: (data) => data?.choices?.[0]?.message?.content || JSON.stringify(data).slice(0, 1000),
    header: (key) => ({ "Content-Type": "application/json", Authorization: `Bearer ${key}` }),
  };
}

function buildProviders(): ProviderSpec[] {
  const providers: ProviderSpec[] = [];
  if (env.ai.geminiKeys.length > 0) providers.push(geminiProvider());
  if (env.ai.groqKeys.length > 0) {
    providers.push(openaiCompatProvider("groq", "https://api.groq.com/openai/v1/chat/completions", env.ai.groqModel, 20));
  }
  if (env.ai.openrouterKeys.length > 0) {
    providers.push(openaiCompatProvider("openrouter", "https://openrouter.ai/api/v1/chat/completions", env.ai.openrouterModel, 30));
  }
  if (env.ai.openaiKeys.length > 0) {
    providers.push(openaiCompatProvider("openai", "https://api.openai.com/v1/chat/completions", env.ai.openaiModel, 35));
  }
  if (env.ai.githubModelsKeys.length > 0) {
    providers.push(openaiCompatProvider("github", "https://models.inference.ai.azure.com/chat/completions", env.ai.githubModel, 40));
  }
  if (env.ai.mistralKey) {
    providers.push(openaiCompatProvider("mistral", "https://api.mistral.ai/v1/chat/completions", env.ai.mistralModel, 50));
  }
  if (env.ai.anthropicKeys.length > 0) {
    providers.push(openaiCompatProvider("anthropic", "https://api.anthropic.com/v1/messages", env.ai.anthropicModel, 60));
  }
  providers.sort((a, b) => a.priority - b.priority);
  return providers;
}

function getPool(providerName: string): AIKeyPool | undefined {
  switch (providerName) {
    case "gemini": return env.ai.geminiKeys.length ? new AIKeyPool(env.ai.geminiKeys) : undefined;
    case "groq": return env.ai.groqKeys.length ? new AIKeyPool(env.ai.groqKeys) : undefined;
    case "openrouter": return env.ai.openrouterKeys.length ? new AIKeyPool(env.ai.openrouterKeys) : undefined;
    case "openai": return env.ai.openaiKeys.length ? new AIKeyPool(env.ai.openaiKeys) : undefined;
    case "github": return env.ai.githubModelsKeys.length ? new AIKeyPool(env.ai.githubModelsKeys) : undefined;
    case "anthropic": return env.ai.anthropicKeys.length ? new AIKeyPool(env.ai.anthropicKeys) : undefined;
    default: return undefined;
  }
}


function isTransient(err: any): boolean {
  const m = `${err?.message ?? ""}`.toLowerCase();
  return m.includes("429") || m.includes("rate") || m.includes("timeout") || m.includes("overloaded") || m.includes(" 502") || m.includes(" 503");
}

export async function analyzeWithAI(
  task: string,
  content: string,
  preferredProvider?: string
): Promise<{
  provider: string;
  model: string;
  content: string;
  attempts: number;
  usedFallback: boolean;
}> {
  const providers = buildProviders();
  if (providers.length === 0) {
    return {
      provider: "none",
      model: "none",
      content: "SupremeAI Control Tower is operational. AI analysis is currently awaiting provider key configuration ($0 key resilient mode).",
      attempts: 0,
      usedFallback: false,
    };
  }

  const ordered = preferredProvider && preferredProvider !== "auto"
    ? [...providers.filter((p) => p.name === preferredProvider), ...providers.filter((p) => p.name !== preferredProvider)]
    : providers;

  const system = [
    "You are the SupremeAI engineering analyst.",
    "Task for you:",
    task,
    "Rules:",
    "- Be concrete, structured, and concise in the output.",
    "- Extract best practices, patterns, and reusable insights.",
    "- Never claim to have executed anything; you only analyze text.",
  ].join("\n");

  let lastError: Error | null = null;
  const attempts: string[] = [];

  for (const provider of ordered) {
    const pool = getPool(provider.name);
    if (!pool) continue;
    try {
      const result = await pool.execute(async (key) => {
        const url = provider.name === "gemini"
          ? `${provider.baseUrl}/${provider.model}:generateContent?key=${encodeURIComponent(key)}`
          : provider.baseUrl;
        const body = provider.buildBody(system, content);
        const headers = provider.header(key);
        if (provider.name === "gemini") headers["x-goog-api-key"] = key;
        const res = await httpRequest(url, { method: "POST", headers, body, timeoutMs: 30_000, retries: 1 });
        if (!res.ok) {
          throw new Error(`[${provider.name}] HTTP ${res.status}: ${JSON.stringify(res.data).slice(0, 300)}`);
        }
        const text = provider.parseContent(res.data);
        if (!text || text.length < 2) throw new Error(`[${provider.name}] Empty response`);
        return { provider: provider.name, model: provider.model, content: text };
      }, isTransient);
      return { ...result, attempts: attempts.length + 1, usedFallback: attempts.length > 0 };
    } catch (err) {
      lastError = err as Error;
      attempts.push(provider.name);
    }
  }

  throw new Error(`All AI providers failed. Last: ${lastError?.message}`);
}

export function listConfiguredAnalysisProviders(): string[] {
  return buildProviders().map((p) => p.name);
}
