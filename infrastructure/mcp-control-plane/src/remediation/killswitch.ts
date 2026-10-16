import {
  activeAccountChain,
  RedisQuotaExhaustedError,
  responseIndicatesQuotaExhaustion,
  runWithAccountChain,
} from "../lib/redis_chain.js";

/**
 * Autonomy kill switch — PERSISTENT edition (audit 2026-10-16 F1, docs/AUDIT_2026-10-16-intelligence-usability.md).
 *
 * বাংলা: আগের সংস্করণ ছিল বিশুদ্ধ in-memory boolean — Render restart বা crash-recover
 * হলেই emergency stop নিজে থেকে রিসেট হয়ে autonomy আবার ENABLED হয়ে যেত। এখন:
 *
 *   1. BOOT ENV GATE  — AUTONOMY_DISABLED=1/true env থাকলে প্রসেস disabled অবস্থায় শুরু করে
 *                       (ops রানবুক: স্থায়ী বন্ধ চাইলে env-ই একমাত্র নিশ্চিত উপায়)।
 *   2. REDIS PERSIST  — সিদ্ধান্ত `supremeai:autonomy-switch` key-তে (TTL ছাড়া) লেখা হয়
 *                       (JSON {autonomyEnabled, changedAt, changedBy}); boot-এ restore হয়,
 *                       তাই kill টিকে থাকে restart-এর পারে।
 *   3. FAIL-CLOSED    — boot restore-এ store অপ্রাপ্য হলে DISABLED অবস্থায় শুরু + লাউড লগ +
 *                       30s পরপর সর্বোচ্চ ৩টি পুনঃপ্রচেষ্টা (সেফটি > availability; অনিশ্চিত
 *                       অবস্থায় autonomy চালু করা হয় না)।
 *
 * Sync contract preserved: `isAutonomyEnabled()` stays synchronous (engine.ts guard
 * and the MCP/REST kill paths read the in-memory flag); Redis writes are
 * fire-and-forget with loud failure logs, and a boot restore reconciles the cache
 * with the persisted truth. Kill/enable still flip the local cache IMMEDIATELY —
 * the persisted copy is the cross-restart truth, not a gate on the flip.
 */

const SWITCH_KEY = "supremeai:autonomy-switch";
const RESTORE_RETRY_MS = 30_000;
const RESTORE_MAX_RETRIES = 3;

type PersistedSwitchState = {
  autonomyEnabled: boolean;
  changedAt: string;
  changedBy: string;
};

type SwitchStore = {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
};

/** Minimal persistent (no-TTL) store over the Upstash/TCP account chain. */
async function makeSwitchStore(): Promise<SwitchStore> {
  const chain = activeAccountChain();
  if (chain.length === 0) {
    throw new Error("No Redis configuration — autonomy switch state unavailable");
  }
  const restAccounts = chain.filter((account) => account.restUrl && account.restToken);
  if (restAccounts.length > 0) {
    const call = async (body: unknown[]): Promise<unknown> => {
      const { value } = await runWithAccountChain(
        async (account) => {
          const res = await fetch(account.restUrl as string, {
            method: "POST",
            headers: {
              Authorization: `Bearer ${account.restToken}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify(body),
            signal: AbortSignal.timeout(10_000),
          });
          if (!res.ok) {
            const errText = await res.text().catch(() => "");
            if (responseIndicatesQuotaExhaustion(res.status, errText)) {
              throw new RedisQuotaExhaustedError(
                account.label,
                `Upstash REST [${account.label}] daily quota exhausted — cooldown until UTC reset`,
              );
            }
            throw new Error(`Upstash REST [${account.label}] HTTP ${res.status}`);
          }
          const payload = (await res.json()) as { result?: unknown; error?: string };
          if (payload.error) {
            if (responseIndicatesQuotaExhaustion(res.status, String(payload.error))) {
              throw new RedisQuotaExhaustedError(
                account.label,
                `Upstash REST [${account.label}] daily quota exhausted (body) — cooldown shift`,
              );
            }
            throw new Error(`Upstash error [${account.label}]: ${payload.error}`);
          }
          return payload.result;
        },
        {
          skip: (account) => !account.restUrl || !account.restToken,
          aggregateError: () => new Error("autonomy switch: all chain accounts failed"),
        },
      );
      return value;
    };
    return {
      get: async (key) => (await call(["GET", key])) as string | null,
      set: async (key, value) => {
        // No TTL by design — the kill decision must survive indefinitely.
        await call(["SET", key, value]);
      },
    };
  }
  const tcpAccount = chain.find((account) => account.tcpUrl);
  if (!tcpAccount) {
    throw new Error("No Redis configuration — autonomy switch state unavailable");
  }
  const { Redis } = await import("ioredis");
  const client = new (Redis as unknown as new (url: string, opts: object) => {
    get(key: string): Promise<string | null>;
    set(key: string, value: string): Promise<"OK">;
  })(tcpAccount.tcpUrl as string, { maxRetriesPerRequest: 2, lazyConnect: false });
  return {
    get: async (key) => client.get(key),
    set: async (key, value) => {
      await client.set(key, value);
    },
  };
}

export class KillSwitchManager {
  private autonomyEnabled: boolean = true;
  private persistEnabled: boolean;
  private persistedState: "enabled" | "disabled" | "unknown" = "unknown";
  private lastPersistError: string | null = null;
  private lastRestoreError: string | null = null;
  private restoreAttempts = 0;
  private restoreTimer: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    // 1) Boot env gate — fail-closed: an explicit ops env wins over everything.
    const envGate = process.env.AUTONOMY_DISABLED;
    const envDisabled = envGate === "1" || envGate === "true";
    this.autonomyEnabled = !envDisabled;
    // Persistence is best-effort: without Redis config the in-memory + env-gate
    // behavior degrades gracefully to the pre-audit semantics (never a boot crash).
    this.persistEnabled = activeAccountChain().length > 0;
    if (envDisabled) {
      this.persistedState = "disabled";
      console.error(
        "[KILL SWITCH] AUTONOMY_DISABLED env gate present — starting DISABLED (L0). Remove the env to re-enable via autonomy.enable.",
      );
    } else if (this.persistEnabled) {
      // 2) Boot restore from the persisted truth (async; cache stays sync-readable).
      void this.restoreFromStore();
    } else {
      console.error(
        "[KILL SWITCH] No Redis configuration — persistence unavailable; in-memory + env-gate semantics only (restart resets manual stops).",
      );
    }
  }

  public isAutonomyEnabled(): boolean {
    return this.autonomyEnabled;
  }

  /** Introspection for autonomy.status / dashboards — honest persistence state. */
  public describe(): {
    autonomyEnabled: boolean;
    persistedState: "enabled" | "disabled" | "unknown";
    envGate: boolean;
    persistEnabled: boolean;
    lastPersistError: string | null;
    lastRestoreError: string | null;
  } {
    return {
      autonomyEnabled: this.autonomyEnabled,
      persistedState: this.persistedState,
      envGate: process.env.AUTONOMY_DISABLED === "1" || process.env.AUTONOMY_DISABLED === "true",
      persistEnabled: this.persistEnabled,
      lastPersistError: this.lastPersistError,
      lastRestoreError: this.lastRestoreError,
    };
  }

  public emergencyStop(): void {
    if (!this.autonomyEnabled) return;

    this.autonomyEnabled = false;
    console.error(`[KILL SWITCH] 🚨 AUTONOMY DISABLED. Dropping to L0 (Read-Only) Mode.`);

    // Stop the background task scheduler if it's running
    import("../tasks/engine.js").then(({ globalTaskEngine }) => {
       globalTaskEngine.stopBackgroundScheduler();
       // Note: We don't forcefully kill running tasks right now,
       // but we could mark them as failed or cancel them if we had cancellation tokens.
       console.error(`[KILL SWITCH] Background task scheduler stopped.`);
    }).catch(console.error);

    this.persist(false);
  }

  public enableAutonomy(): void {
    if (this.autonomyEnabled) return;

    this.autonomyEnabled = true;
    console.log(`[KILL SWITCH] ✅ AUTONOMY RE-ENABLED.`);
    this.persist(true);
  }

  /** Fire-and-forget persistence of the switch decision (loud on failure). */
  private persist(enabled: boolean): void {
    if (!this.persistEnabled) return;
    this.persistedState = enabled ? "enabled" : "disabled";
    const payload: PersistedSwitchState = {
      autonomyEnabled: enabled,
      changedAt: new Date().toISOString(),
      changedBy: "mcp-tower",
    };
    (async () => {
      const store = await makeSwitchStore();
      await store.set(SWITCH_KEY, JSON.stringify(payload));
      this.lastPersistError = null;
      console.log(`[KILL SWITCH] Decision persisted to ${SWITCH_KEY} (autonomyEnabled=${enabled}).`);
    })().catch((err: unknown) => {
      this.lastPersistError = (err as Error)?.message ?? String(err);
      // বাংলা: লোকাল flip ইতিমধ্যে কার্যকর — শুধু cross-restart সত্য সংরক্ষণ ব্যর্থ; লাউড থাকতে হবে।
      console.error(`[KILL SWITCH] ⚠️ persistence FAILED (restart will NOT remember this decision): ${this.lastPersistError}`);
    });
  }

  /** Boot restore; fail-closed (DISABLED) while the truth is unreadable. */
  private async restoreFromStore(retry: number = 0): Promise<void> {
    try {
      const store = await makeSwitchStore();
      const raw = await store.get(SWITCH_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as PersistedSwitchState;
        this.autonomyEnabled = parsed.autonomyEnabled === true;
        this.persistedState = parsed.autonomyEnabled ? "enabled" : "disabled";
        this.lastRestoreError = null;
        console.error(
          `[KILL SWITCH] Boot restore from ${SWITCH_KEY}: autonomy ${this.autonomyEnabled ? "ENABLED" : "DISABLED"} (changedAt=${parsed.changedAt}).`,
        );
      } else {
        // No persisted decision yet — first boot: stay enabled (matches env-gate).
        this.persistedState = "enabled";
        this.lastRestoreError = null;
        console.log(`[KILL SWITCH] No persisted decision at ${SWITCH_KEY} — first-boot default ENABLED.`);
      }
    } catch (err) {
      this.lastRestoreError = (err as Error)?.message ?? String(err);
      this.restoreAttempts = retry + 1;
      // Fail-closed while truth is unknown: do NOT leave autonomy running on an
      // unverified state. Loud + bounded retries; env gate can always force-enable path.
      this.autonomyEnabled = false;
      console.error(
        `[KILL SWITCH] ⚠️ boot restore FAILED (${this.restoreAttempts}/${RESTORE_MAX_RETRIES}) — starting DISABLED (fail-closed): ${this.lastRestoreError}`,
      );
      if (retry + 1 < RESTORE_MAX_RETRIES) {
        if (this.restoreTimer) clearTimeout(this.restoreTimer);
        this.restoreTimer = setTimeout(() => {
          void this.restoreFromStore(retry + 1);
        }, RESTORE_RETRY_MS);
        if (typeof this.restoreTimer === "object" && "unref" in this.restoreTimer) {
          (this.restoreTimer as { unref: () => void }).unref();
        }
      }
    }
  }
}

export const globalKillSwitch = new KillSwitchManager();
