import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { pingRedis, getRedisStats, readRedisKey } from "../adapters/redis/index.js";
import { quotaChainStatus, nextQuotaResetEpochMs, upstashCommandLimit } from "../lib/redis_chain.js";
import { sendTelegram } from "../adapters/notify/actions.js";
import { cacheLookup, cacheStore, cacheConfigStatus } from "../lib/semantic_cache.js";

// #1522 (Q1): in-memory per-window dedup for quota alerts. Resets on deploy —
// the persistent, cron-side dedup lives in scripts/ops/redis_quota_monitor.py.
const quotaAlertSent = new Map<string, string>();

export async function registerRedisTools(server: McpServer): Promise<void> {
  server.tool(
    "redis.ping",
    "Ping the Redis cache/queue to verify connectivity.",
    {},
    async () => {
      try {
        const res = await pingRedis();
        return {
          content: [{ type: "text", text: JSON.stringify(res, null, 2) }],
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );

  server.tool(
    "redis.stats",
    "Get basic statistics from Redis via the INFO command.",
    {},
    async () => {
      try {
        const stats = await getRedisStats();
        return {
          content: [{ type: "text", text: JSON.stringify(stats, null, 2) }],
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );

  server.tool(
    "redis.read_key",
    "Safely read/get the value of a key from Redis cache (Read-Only).",
    {
      key: z.string().describe("The Redis key to read"),
    },
    async ({ key }) => {
      try {
        const res = await readRedisKey(key);
        return {
          content: [{ type: "text", text: JSON.stringify(res, null, 2) }],
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );

  server.tool(
    "redis.rotation_status",
    "Inspect the Upstash Redis auto-rotation chain status, active primary, and quota cooldowns (#26).",
    {},
    async () => {
      try {
        const { quotaChainStatus, getActiveRedisAccount, nextQuotaResetEpochMs } = await import("../lib/redis_chain.js");
        const active = getActiveRedisAccount();
        const chain = quotaChainStatus();
        const nextReset = new Date(nextQuotaResetEpochMs()).toISOString();
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                {
                  autoRotateEnabled: true,
                  activePrimary: active.label,
                  quotaWindow: process.env.UPSTASH_QUOTA_WINDOW || "monthly",
                  nextGlobalResetAt: nextReset,
                  chain,
                },
                null,
                2
              ),
            },
          ],
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );
  // ── #1522 (Q1): 80% quota warning + Qdrant semantic cache surfaces ──────────
  // বাংলা মন্তব্য: 96% preemptive rotation (#646) ট্রাফিক বাঁচায়, কিন্তু "কোটা
  // শেষ হচ্ছে" খবরটি কাউকে দেয় না — redis.quota_alert সেই খবর Telegram-এ পাঠায়
  // (window-প্রতি একবার; স্থায়ী dedup ক্রন-পাশে scripts/ops/redis_quota_monitor.py-তে)।

  server.tool(
    "redis.quota_alert",
    "Evaluate the Upstash account-chain quota usage and send a Telegram warning when any account crosses the threshold (default 80%, critical at 95%). Deduplicated per account per tier per quota window (in-memory).",
    {
      thresholdPct: z.number().min(1).max(100).optional().describe("Warning threshold percent (default 80, env REDIS_QUOTA_ALERT_PCT)"),
      chatId: z.string().optional().describe("Optional Telegram chat id override"),
    },
    async ({ thresholdPct, chatId }) => {
      try {
        const warnPct = thresholdPct ?? (Number(process.env.REDIS_QUOTA_ALERT_PCT) || 80);
        const critPct = Number(process.env.REDIS_QUOTA_CRIT_PCT) || 95;
        const nowMs = Date.now();
        const chain = quotaChainStatus(nowMs);
        const windowKey = new Date(nextQuotaResetEpochMs(nowMs)).toISOString();
        const accounts = chain.map((entry) => {
          const used = entry.usage?.estimatedCommands ?? 0;
          const limit = entry.usage?.limit ?? upstashCommandLimit();
          const pct = limit > 0 ? Math.round((used * 10000) / limit) / 100 : null;
          const tier = pct === null ? null : pct >= critPct ? "crit" : pct >= warnPct ? "warn" : null;
          return {
            label: entry.label,
            used,
            limit,
            pct,
            tier,
            cooldownUntil: entry.cooldownUntil,
            isActivePrimary: entry.isActivePrimary,
          };
        });
        const active = accounts.filter((a) => a.tier !== null);
        const alertKey = (a: (typeof accounts)[number]) => `${a.label}:${a.tier}`;
        const fresh = active.filter((a) => quotaAlertSent.get(alertKey(a)) !== windowKey);
        let telegram: { sent: boolean; messageId?: unknown; reason?: string } = { sent: false };
        if (fresh.length > 0) {
          const lines = fresh.map(
            (a) =>
              `${a.tier === "crit" ? "[CRITICAL]" : "[WARN]"} Upstash Redis account '${a.label}' at ${a.pct}% of quota (${a.used} / ${a.limit} commands).`,
          );
          const primary = chain.find((c) => c.isActivePrimary)?.label ?? "unknown";
          lines.push(`Active rotation primary: ${primary}.`);
          lines.push(`Quota window resets: ${windowKey}.`);
          lines.push(
            "Auto-rotation (#646) protects traffic at 96%, but capacity is running out — top up, downgrade burn, or add an account.",
          );
          try {
            const sent = await sendTelegram(lines.join("\n"), chatId);
            telegram = { sent: true, messageId: sent.messageId };
            for (const a of fresh) quotaAlertSent.set(alertKey(a), windowKey);
          } catch (notifyErr) {
            // Graceful degradation (#3): a Telegram outage must not fail the report.
            telegram = { sent: false, reason: (notifyErr as Error).message };
          }
        }
        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                {
                  thresholdPct: warnPct,
                  criticalPct: critPct,
                  window: windowKey,
                  accounts,
                  alertsPending: fresh.length,
                  telegram,
                  persistentDedupCounterpart: "scripts/ops/redis_quota_monitor.py",
                },
                null,
                2
              ),
            },
          ],
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );

  server.tool(
    "cache.semantic_lookup",
    "Look up a semantically similar cached answer for a question in the Qdrant semantic cache (#1522); falls back to char-trigram lexical similarity when no embedding provider is configured (result honestly labels which embedder ran). A hit avoids the Redis-backed downstream path entirely.",
    {
      question: z.string().min(1).describe("The user question to look up"),
    },
    async ({ question }) => {
      try {
        const result = await cacheLookup(question);
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );

  server.tool(
    "cache.semantic_store",
    "Store a question/answer pair in the Qdrant semantic cache (#1522). Keeps only the newest SEMANTIC_CACHE_MAX_ENTRIES (default 20) patterns — oldest points are pruned by storedAt.",
    {
      question: z.string().min(1).describe("The user question"),
      answer: z.string().min(1).describe("The grounded answer to cache"),
    },
    async ({ question, answer }) => {
      try {
        const result = await cacheStore(question, answer);
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );

  server.tool(
    "cache.status",
    "Report the semantic cache configuration honestly: embedder tier (gemini vs trigram-lexical-fallback), collection, hit threshold, caps.",
    {},
    async () => {
      try {
        return { content: [{ type: "text", text: JSON.stringify(cacheConfigStatus(), null, 2) }] };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );
}
