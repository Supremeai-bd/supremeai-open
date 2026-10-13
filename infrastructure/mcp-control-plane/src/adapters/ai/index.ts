import { env } from "../../lib/env.js";
import { httpRequest, bearerAuth } from "../../lib/http.js";
import { AIKeyPool } from "./key-pool.js";

const pools: Record<string, AIKeyPool> = {};

export function getOrInitPool(provider: string): AIKeyPool | null {
  if (pools[provider] && pools[provider].length > 0) {
    return pools[provider];
  }

  let keys: string[] = [];
  switch (provider) {
    case "gemini":
      keys = env.ai.geminiKeys;
      break;
    case "groq":
      keys = env.ai.groqKeys;
      break;
    case "openrouter":
      keys = env.ai.openrouterKeys;
      break;
    case "github":
      keys = env.ai.githubModelsKeys;
      break;
    case "mistral":
      keys = env.ai.mistralKey ? [env.ai.mistralKey] : [];
      break;
  }

  if (keys.length > 0) {
    pools[provider] = new AIKeyPool(keys);
    return pools[provider];
  }
  return null;
}

export function listProviders(): unknown {
  const supported = ["gemini", "groq", "openrouter", "github", "mistral"];
  for (const p of supported) {
    getOrInitPool(p);
  }
  return Object.keys(pools).map((provider) => ({
    provider,
    keyCount: pools[provider].length,
  }));
}

function isRateLimit(err: any): boolean {
  // Usually 429 Too Many Requests
  return err?.message?.includes("429") || err?.message?.includes("Too Many Requests");
}

export async function testProvider(provider: string): Promise<unknown> {
  const pool = getOrInitPool(provider);
  if (!pool) {
    throw new Error(`Provider '${provider}' not configured or no keys found.`);
  }


  const start = Date.now();
  
  const result = await pool.execute(async (key) => {
    let res: any;
    // We will just hit the /models endpoint to verify the key works.
    switch (provider) {
      case "gemini":
        res = await httpRequest(`https://generativelanguage.googleapis.com/v1beta/models?key=${key}`, { timeoutMs: 5000 });
        break;
      case "groq":
        res = await httpRequest(`https://api.groq.com/openai/v1/models`, { headers: bearerAuth(key), timeoutMs: 5000 });
        break;
      case "openrouter":
        res = await httpRequest(`https://openrouter.ai/api/v1/models`, { headers: bearerAuth(key), timeoutMs: 5000 });
        break;
      case "github":
        res = await httpRequest(`https://models.inference.ai.azure.com/models`, { headers: bearerAuth(key), timeoutMs: 5000 });
        break;
      case "mistral":
        res = await httpRequest(`https://api.mistral.ai/v1/models`, { headers: bearerAuth(key), timeoutMs: 5000 });
        break;
      default:
        throw new Error(`Unknown provider for testing: ${provider}`);
    }
    
    // If it didn't throw, it's successful
    return {
      success: true,
      statusCode: res.status,
      modelsCount: res.data?.data?.length || res.data?.models?.length || "unknown",
    };
  }, isRateLimit);

  return {
    provider,
    ...result,
    latencyMs: Date.now() - start,
  };
}
