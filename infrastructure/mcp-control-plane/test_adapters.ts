import "dotenv/config";
import { listServices, getServiceHealth } from "./src/adapters/render/index.js";
import { getWorkflowRuns, listSecrets } from "./src/adapters/github/index.js";
import { getHealth, getAuthUsers } from "./src/adapters/supabase/index.js";
import { pingRedis, getRedisStats } from "./src/adapters/redis/index.js";
import { getWorkerStatus, getAnalytics } from "./src/adapters/cloudflare/index.js";
import { auditSecrets, getSyncStatus } from "./src/adapters/infisical/index.js";
import { getAuthStatus, getHostingStatus } from "./src/adapters/firebase/index.js";
import * as path from "node:path";
import * as fs from "node:fs";
import { config } from "dotenv";

config({ path: path.resolve(process.cwd(), "../../.env") });

async function main() {
  console.log("=== Testing Render Adapter ===");
  try {
    const renderPrimaryId = "render-primary";
    const services = await listServices(renderPrimaryId) as any[];
    console.log(`[Render] Found ${services.length} services on ${renderPrimaryId}`);
    if (services.length > 0) {
      const firstService = services[0].service.id;
      const health = await getServiceHealth(renderPrimaryId, firstService);
      console.log(`[Render] Health for ${firstService}:`, JSON.stringify(health).slice(0, 100) + "...");
    }
  } catch (e) {
    console.error("[Render] Error:", (e as Error).message);
  }

  console.log("\n=== Testing GitHub Adapter ===");
  try {
    const githubId = "github-primary";
    const runs = await getWorkflowRuns(githubId, 1) as any;
    console.log(`[GitHub] Latest runs:`, runs.total_count || "Unknown");
    const secrets = await listSecrets(githubId) as any;
    console.log(`[GitHub] Total secrets:`, secrets.total_count || "Unknown");
  } catch (e) {
    console.error("[GitHub] Error:", (e as Error).message);
  }

  console.log("\n=== Testing Supabase Adapter ===");
  try {
    const supabaseId = "supabase-primary";
    const health = await getHealth(supabaseId);
    console.log(`[Supabase] Health:`, health);
    const users = await getAuthUsers(supabaseId);
    console.log(`[Supabase] Auth users:`, users);
  } catch (e) {
    console.error("[Supabase] Error:", (e as Error).message);
  }

  console.log("\n=== Testing Redis Adapter ===");
  try {
    const ping = await pingRedis();
    console.log(`[Redis] Ping:`, ping);
  } catch (e) {
    console.error("[Redis] Error:", (e as Error).message);
  }

  console.log("\n=== Testing Cloudflare Adapter ===");
  try {
    const cfStatus = await getWorkerStatus();
    console.log(`[Cloudflare] Worker Status:`, cfStatus);
  } catch (e) {
    console.error("[Cloudflare] Error:", (e as Error).message);
  }

  console.log("\n=== Testing Infisical Adapter ===");
  try {
    const secrets = await auditSecrets();
    console.log(`[Infisical] Audited Secrets length:`, (secrets as any[]).length);
  } catch (e) {
    console.error("[Infisical] Error:", (e as Error).message);
  }

  console.log("\n=== Testing Firebase Adapter ===");
  try {
    const authStatus = await getAuthStatus();
    console.log(`[Firebase] Auth Status:`, authStatus);
  } catch (e) {
    console.error("[Firebase] Error:", (e as Error).message);
  }

  console.log("\n=== Testing AI Adapter ===");
  try {
    const { listProviders, testProvider } = await import("./src/adapters/ai/index.js");
    const providers = listProviders() as any[];
    console.log(`[AI] Configured Providers:`, providers);
    if (providers.length > 0) {
      const res = await testProvider(providers[0].provider);
      console.log(`[AI] Test ${providers[0].provider}:`, res);
    }
  } catch (e) {
    console.error("[AI] Error:", (e as Error).message);
  }

  console.log("\n=== Testing Notify Adapter ===");
  try {
    const { checkTelegram, checkDiscord } = await import("./src/adapters/notify/index.js");
    try {
      console.log("[Notify] Telegram:", await checkTelegram());
    } catch(e) { console.error("[Notify] Telegram Error:", (e as Error).message); }
    try {
      console.log("[Notify] Discord:", await checkDiscord());
    } catch(e) { console.error("[Notify] Discord Error:", (e as Error).message); }
  } catch (e) {
    console.error("[Notify] Import Error:", (e as Error).message);
  }

  console.log("\n=== Testing Misc Adapters ===");
  try {
    const misc = await import("./src/adapters/misc/index.js");
    const checks = [
      { name: "Stripe", fn: misc.checkStripe },
      { name: "Qdrant", fn: misc.checkQdrant },
      { name: "Vercel", fn: misc.checkVercel },
      { name: "Firecrawl", fn: misc.checkFirecrawl },
      { name: "Kaggle", fn: misc.checkKaggle },
    ];
    for (const c of checks) {
      try {
        console.log(`[Misc] ${c.name}:`, await c.fn());
      } catch (e) {
        console.error(`[Misc] ${c.name} Error:`, (e as Error).message);
      }
    }
  } catch (e) {
    console.error("[Misc] Error:", (e as Error).message);
  }
}

main().catch(console.error);
