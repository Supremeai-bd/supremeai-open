import { env } from "../../lib/env.js";
import { httpRequest, bearerAuth } from "../../lib/http.js";
import { AIKeyPool } from "../ai/key-pool.js";

export async function checkStripe(): Promise<unknown> {
  const { secretKey } = env.stripe;
  if (!secretKey) throw new Error("STRIPE_SECRET_KEY is not configured.");

  const start = Date.now();
  // Fetch account details to verify the key
  const res = await httpRequest(`https://api.stripe.com/v1/account`, {
    headers: bearerAuth(secretKey)
  });

  return {
    status: "healthy",
    accountId: (res.data as any).id,
    latencyMs: Date.now() - start
  };
}

export async function checkQdrant(): Promise<unknown> {
  const { url, apiKey } = env.qdrant;
  if (!url) throw new Error("QDRANT_URL is not configured.");

  const start = Date.now();
  const headers = apiKey ? { "api-key": apiKey } : undefined;
  
  // Qdrant health endpoint
  const res = await httpRequest(`${url}/healthz`, { headers });

  return {
    status: "healthy",
    message: res.data,
    latencyMs: Date.now() - start
  };
}

export async function checkVercel(): Promise<unknown> {
  const { token, projectId } = env.vercel;
  if (!token) throw new Error("VERCEL_TOKEN is not configured.");

  const start = Date.now();
  // Fetch deployments for the project or just verify auth
  let url = "https://api.vercel.com/v6/deployments?limit=1";
  if (projectId) url += `&projectId=${projectId}`;

  const res = await httpRequest(url, { headers: bearerAuth(token) });
  const data = res.data as any;

  return {
    status: "healthy",
    latestDeployments: data.deployments ? data.deployments.length : 0,
    latencyMs: Date.now() - start
  };
}

let firecrawlPoolInstance: AIKeyPool | undefined;
function firecrawlPool(): AIKeyPool {
  const keys = env.firecrawl.apiKeys;
  if (!firecrawlPoolInstance || (firecrawlPoolInstance.length === 0 && keys.length > 0)) {
    firecrawlPoolInstance = new AIKeyPool(keys);
  }
  return firecrawlPoolInstance;
}

export async function checkFirecrawl(): Promise<unknown> {
  const pool = firecrawlPool();
  if (pool.length === 0) throw new Error("FIRECRAWL_API_KEY is not configured.");

  const start = Date.now();
  await pool.execute(
    async (key: string) => {
      const res = await httpRequest("https://api.firecrawl.dev/v1/scrape", {
        method: "POST",
        headers: bearerAuth(key),
        body: { url: "https://example.com" }
      });

      if (!res.ok) {
        if (res.status === 401) {
          throw new Error("Firecrawl API Error: Unauthorized");
        }
        throw new Error(`Firecrawl API Error (${res.status}): ${JSON.stringify(res.data)}`);
      }
      return res;
    },
    (err: any) => {
      const msg = (err?.message || "").toLowerCase();
      return msg.includes("429") || msg.includes("402") || msg.includes("credit") || msg.includes("quota") || msg.includes("rate limit");
    }
  );

  return {
    status: "healthy",
    poolSize: pool.length,
    latencyMs: Date.now() - start
  };
}

// Lazy singleton: env.kaggle.tokens must be read AFTER the Infisical secrets
// pull (main() -> pullSecretsIntoProcessEnv). A module-level
// `new AIKeyPool(env.kaggle.tokens)` snapshots an EMPTY pool because this
// module is imported before the pull runs — leaving kaggle permanently
// "not configured" in production even though the tokens are in env.
// Re-creates once if the first snapshot was taken too early (self-heal).
let kagglePoolInstance: AIKeyPool | undefined;
function kagglePool(): AIKeyPool {
  const tokens = env.kaggle.tokens;
  if (!kagglePoolInstance || (kagglePoolInstance.length === 0 && tokens.length > 0)) {
    kagglePoolInstance = new AIKeyPool(tokens);
  }
  return kagglePoolInstance;
}

export async function checkKaggle(): Promise<unknown> {
  if (kagglePool().length === 0) throw new Error("KAGGLE_API_TOKENS is not configured.");

  const start = Date.now();
  await kagglePool().execute(
    async (token) => {
      const isBearer = token.startsWith("KGAT_");
      const authHeader = isBearer ? `Bearer ${token}` : `Basic ${Buffer.from(token).toString('base64')}`;
      const res = await httpRequest("https://www.kaggle.com/api/v1/competitions/list", {
        headers: { Authorization: authHeader }
      });
      if (!res.ok) {
        throw new Error(`Kaggle API error (${res.status}): ${JSON.stringify(res.data)}`);
      }
      return res;
    },
    (err: any) => {
      const msg = err?.message || "";
      return msg.includes("429") || msg.includes("rate limit") || msg.includes("quota");
    }
  );

  return {
    status: "healthy",
    poolSize: kagglePool().length,
    latencyMs: Date.now() - start
  };
}
