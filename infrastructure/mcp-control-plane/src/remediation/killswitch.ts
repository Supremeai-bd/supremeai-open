// ── Emergency kill switch — PERSISTENT (audit F1, 2026-10-16) ───────────────
//
// History: this manager used to be a plain in-memory boolean. `emergencyStop()`
// flipped it, and the next Render auto-deploy or crash-restart silently
// re-enabled autonomy — an admin's emergency stop to L0 (Read-Only) survived
// only until the next restart. For an "emergency stop" primitive that is a
// correctness defect, not a hardening nicety.
//
// Persistence design (smallest safe, per the intelligence-usability audit F1):
//   • The L0 guard (`isAutonomyEnabled`) stays SYNCHRONOUS — remediation
//     engine and policy checks keep their exact semantics.
//   • State persists in the existing Redis account chain under one key
//     (no TTL — an emergency stop must outlive free-tier quota windows too;
//     the chain-walk engine owns account rotation).
//   • Persistence is ARMED explicitly at boot via `initPersistence()` (same
//     doctrine as registerBridgeIntake: armed before the server accepts
//     traffic). An unarmed manager behaves exactly like the old in-memory one,
//     with one loud honesty line — which also means existing test suites that
//     exercise the global singleton can never mutate real Redis.
//   • Boot restore: `disabled` in the store → boots disabled. Restore failure
//     (Redis configured but unreachable, or an unparseable state) FAILS CLOSED
//     to DISABLED — for an emergency primitive, unknown must mean "stopped".
//   • Env gate: `AUTONOMY_DISABLED=1|true` (case-insensitive) boots disabled
//     unconditionally and refuses `enableAutonomy()` — a boot-time operator
//     gate outranks a runtime tool call.
//
// No secrets, no new env names beyond the gate itself; REST walk reuses the
// shared account chain and quota-rotation policy (#110/#2613).

import {
  buildAccountChain,
  RedisQuotaExhaustedError,
  responseIndicatesQuotaExhaustion,
  runWithAccountChain,
  type RedisAccountConfig,
} from "../lib/redis_chain.js";

export const KILL_SWITCH_STATE_KEY = "supremeai:autonomy-kill-switch";
export const KILL_SWITCH_ENV_GATE = "AUTONOMY_DISABLED";

export type KillSwitchPersistState = "enabled" | "disabled";

export type KillSwitchSnapshot = {
  autonomyEnabled: boolean;
  envGateDisabled: boolean;
  persistenceArmed: boolean;
  persistedState: KillSwitchPersistState | null;
  lastPersistError: string | null;
  lastRestoreError: string | null;
  stateKey: string;
};

/** One Redis command against one account; resolves with the REST `result`. */
export type KillSwitchRestCaller = (
  account: RedisAccountConfig,
  command: unknown[],
) => Promise<unknown>;

export interface KillSwitchDeps {
  now?: () => number;
  /** REST command executor (injectable for tests; default = Upstash REST). */
  restCall?: KillSwitchRestCaller;
  chainBuilder?: () => RedisAccountConfig[];
  envGet?: (name: string) => string | undefined;
  log?: (line: string) => void;
  errorLog?: (line: string) => void;
}

/** Default REST caller — house pattern (agent_heartbeat.ts): quota-shaped
 * errors are thrown so `runWithAccountChain` owns cooldown marking (#110). */
export const killSwitchRestCall: KillSwitchRestCaller = async (account, command) => {
  if (!account.restUrl || !account.restToken) {
    // Kill-switch state is a single GET/SET — REST-only by design; TCP-only
    // accounts are skipped by the walk (documented skip contract in
    // lib/redis_chain.ts) and never reach this caller.
    throw new Error(`kill-switch store: account "${account.label}" has no REST credentials`);
  }
  const res = await fetch(account.restUrl, {
    method: "POST",
    headers: { Authorization: `Bearer ${account.restToken}`, "Content-Type": "application/json" },
    body: JSON.stringify(command),
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) {
    const errText = await res.text().catch(() => "");
    if (responseIndicatesQuotaExhaustion(res.status, errText)) {
      throw new RedisQuotaExhaustedError(
        account.label,
        `Upstash REST [${account.label}] কোটা শেষ — kill-switch state op বাতিল`,
      );
    }
    throw new Error(`Upstash REST [${account.label}] returned HTTP ${res.status}`);
  }
  const payload = (await res.json()) as { result?: unknown; error?: string };
  if (payload.error) {
    if (responseIndicatesQuotaExhaustion(res.status, String(payload.error))) {
      throw new RedisQuotaExhaustedError(
        account.label,
        `Upstash REST [${account.label}] কোটা শেষ (body) — kill-switch state op বাতিল`,
      );
    }
    throw new Error(`Upstash error [${account.label}]: ${payload.error}`);
  }
  return payload.result;
};

const REST_ONLY = (account: RedisAccountConfig): boolean => !account.restUrl || !account.restToken;

export class KillSwitchManager {
  private autonomyEnabled: boolean;
  private readonly envGateDisabled: boolean;
  private armed = false;
  private persistedState: KillSwitchPersistState | null = null;
  private lastPersistError: string | null = null;
  private lastRestoreError: string | null = null;
  private readonly deps: Required<KillSwitchDeps>;

  constructor(deps: KillSwitchDeps = {}) {
    this.deps = {
      now: deps.now ?? (() => Date.now()),
      restCall: deps.restCall ?? killSwitchRestCall,
      chainBuilder: deps.chainBuilder ?? buildAccountChain,
      envGet: deps.envGet ?? ((name: string) => process.env[name]),
      log: deps.log ?? ((line: string) => console.log(line)),
      errorLog: deps.errorLog ?? ((line: string) => console.error(line)),
    };
    const raw = (this.deps.envGet(KILL_SWITCH_ENV_GATE) ?? "").trim().toLowerCase();
    this.envGateDisabled = raw === "1" || raw === "true";
    this.autonomyEnabled = !this.envGateDisabled;
    if (this.envGateDisabled) {
      this.deps.errorLog(
        `[KILL SWITCH] 🚨 AUTONOMY_DISABLED=${raw} — booting straight to L0 (Read-Only). ` +
          `enableAutonomy() calls are refused until the env gate is lifted.`,
      );
    }
  }

  /** Sync L0 guard — semantics unchanged for the remediation engine. */
  public isAutonomyEnabled(): boolean {
    return this.autonomyEnabled;
  }

  public emergencyStop(): void {
    if (!this.autonomyEnabled) return; // idempotent

    this.autonomyEnabled = false;
    this.deps.errorLog(`[KILL SWITCH] 🚨 AUTONOMY DISABLED. Dropping to L0 (Read-Only) Mode.`);

    // Stop the background task scheduler if it's running
    import("../tasks/engine.js").then(({ globalTaskEngine }) => {
      globalTaskEngine.stopBackgroundScheduler();
      // Note: We don't forcefully kill running tasks right now,
      // but we could mark them as failed or cancel them if we had cancellation tokens.
      this.deps.errorLog(`[KILL SWITCH] Background task scheduler stopped.`);
    }).catch((err) => this.deps.errorLog(`[KILL SWITCH] scheduler stop failed: ${err?.message ?? err}`));

    void this.persistState("disabled");
  }

  public enableAutonomy(): void {
    if (this.envGateDisabled) {
      this.deps.errorLog(
        `[KILL SWITCH] enableAutonomy() REFUSED — ${KILL_SWITCH_ENV_GATE} env gate is set ` +
          `(operator boot intent outranks runtime tool calls).`,
      );
      return;
    }
    if (this.autonomyEnabled) return; // idempotent

    this.autonomyEnabled = true;
    this.deps.log(`[KILL SWITCH] ✅ AUTONOMY RE-ENABLED.`);
    void this.persistState("enabled");
  }

  /**
   * Arm Redis persistence + boot-time state restore. Called once from
   * `main()` BEFORE the server accepts traffic; idempotent; never throws
   * (fail-honest introspection via `describe()`). Restore failure fails
   * CLOSED (autonomy disabled) — unknown must mean "stopped" for an
   * emergency primitive.
   */
  public async initPersistence(): Promise<void> {
    if (this.armed) return;

    const chain = this.deps.chainBuilder();
    if (chain.length === 0) {
      this.lastPersistError = "no Redis account configured — kill-switch state is VOLATILE";
      this.deps.errorLog(
        `[KILL SWITCH] ⚠️ no Redis account configured — emergency stop state is VOLATILE ` +
          `(will NOT survive restarts). Configure the Upstash chain to arm persistence.`,
      );
      return;
    }

    this.armed = true;

    if (this.envGateDisabled) {
      // Env gate wins at boot; still sync the store so Redis truth matches.
      await this.persistState("disabled");
      return;
    }

    try {
      const stored = await this.readState();
      this.persistedState = stored;
      if (stored === "disabled" && this.autonomyEnabled) {
        this.autonomyEnabled = false;
        this.deps.errorLog(
          `[KILL SWITCH] 🚨 restored DISABLED from persistent store — previous emergency stop survives the restart.`,
        );
      } else if (stored === "enabled") {
        this.deps.log(`[KILL SWITCH] persistent state = enabled (no emergency stop on record).`);
      }
    } catch (err) {
      this.lastRestoreError = err instanceof Error ? err.message : String(err);
      this.autonomyEnabled = false; // FAIL-CLOSED
      this.deps.errorLog(
        `[KILL SWITCH] ❌ state restore FAILED (${this.lastRestoreError}) — failing CLOSED: ` +
          `autonomy stays DISABLED until an admin re-enables. Unknown must mean "stopped".`,
      );
    }
  }

  /** Boot/operator introspection — every state transition reason is visible. */
  public describe(): KillSwitchSnapshot {
    return {
      autonomyEnabled: this.autonomyEnabled,
      envGateDisabled: this.envGateDisabled,
      persistenceArmed: this.armed,
      persistedState: this.persistedState,
      lastPersistError: this.lastPersistError,
      lastRestoreError: this.lastRestoreError,
      stateKey: KILL_SWITCH_STATE_KEY,
    };
  }

  /** REST-only walk (TCP-only accounts skipped per the redis_chain contract). */
  private async readState(): Promise<KillSwitchPersistState> {
    const { value } = await runWithAccountChain(
      (account) => this.deps.restCall(account, ["GET", KILL_SWITCH_STATE_KEY]),
      {
        chain: this.deps.chainBuilder(),
        skip: REST_ONLY,
        aggregateError: (attempts) =>
          new Error(
            `all ${attempts.length} Redis account(s) failed during kill-switch restore: ` +
              attempts.map((a) => `${a.account}: ${a.error ?? "unknown"}`).join(" | "),
          ),
      },
    );
    if (value === null || value === undefined || value === "") {
      // No record yet — first boot on a fresh store; nothing to restore.
      return "enabled";
    }
    let parsed: { autonomyEnabled?: unknown };
    try {
      parsed = JSON.parse(String(value)) as { autonomyEnabled?: unknown };
    } catch {
      throw new Error(`kill-switch state is unparseable (corrupt record) — refusing to guess`);
    }
    if (parsed.autonomyEnabled === false) return "disabled";
    if (parsed.autonomyEnabled === true) return "enabled";
    throw new Error(`kill-switch state record lacks a boolean autonomyEnabled — refusing to guess`);
  }

  /** Fire-and-forget write (flip already applied in memory; never throws). */
  private async persistState(state: KillSwitchPersistState): Promise<void> {
    if (!this.armed) {
      this.deps.errorLog(
        `[KILL SWITCH] ⚠️ persistence NOT armed (initPersistence() not called or no Redis) — ` +
          `this flip is VOLATILE and will be lost on restart.`,
      );
      return;
    }
    try {
      const record = JSON.stringify({
        autonomyEnabled: state === "enabled",
        updatedAt: new Date(this.deps.now()).toISOString(),
        writer: "mcp-control-plane/killswitch.ts",
      });
      await runWithAccountChain(
        (account) => this.deps.restCall(account, ["SET", KILL_SWITCH_STATE_KEY, record]),
        {
          chain: this.deps.chainBuilder(),
          skip: REST_ONLY,
          aggregateError: (attempts) =>
            new Error(
              `all ${attempts.length} Redis account(s) failed during kill-switch persist: ` +
                attempts.map((a) => `${a.account}: ${a.error ?? "unknown"}`).join(" | "),
            ),
        },
      );
      this.persistedState = state;
    } catch (err) {
      this.lastPersistError = err instanceof Error ? err.message : String(err);
      this.deps.errorLog(
        `[KILL SWITCH] ❌ persist FAILED (${this.lastPersistError}) — in-memory state stands, ` +
          `but the restart-survival guarantee is broken until a successful write.`,
      );
    }
  }
}

export const globalKillSwitch = new KillSwitchManager();
