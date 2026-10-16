# Kill-Switch Persistence & Heartbeat Ownership — Drop-In Integration (#340)

> Issue: [#340](https://github.com/Supremeai-bd/supremeai-open/issues/340) — feat(mcp): persistent
> kill switch and task-ownership validator chain (P1-high, security).
> Delivery form: **pure-new-file drop-ins** — the four files below land through the bridge with
> ZERO modifications to any existing live file. The exact operator integration diffs (a few lines
> each, byte-exact) are embedded in §3 so the maintainer applies them in one pass.

## 1. Why drop-ins

The live control plane (`src/remediation/killswitch.ts`, `src/index.ts`,
`src/tools/agent.tools.ts`) is deployed code; the private `main` diverges from the public mirror,
so bridge patches that touch those files fail to apply (proven repeatedly: WO #352 attempts r1–r4
all died with `patch does not apply`). This delivery therefore keeps every existing byte untouched
and carries the integration as reviewed diffs — the same hand-off pattern the Single-Pane policy
doc uses for protected `.github/` surfaces (WO #376 Appendix A).

## 2. What landed (4 new files)

| File | Role |
|---|---|
| `src/remediation/killswitch_persistence.ts` | Redis account-chain-backed persistence for the autonomy flag: persist / load / boot-restore verdicts, fail-closed parsing, no-TTL state key |
| `src/lib/heartbeat_ownership.ts` | Strict fail-closed validator for `taskId` / `status` / `ttlSeconds` per `api-schemas/heartbeat.schema.json`, with AC3 legacy pass-through |
| `selftest_killswitch_persistence.ts` | Hermetic offline harness (64 checks) — fake Redis ports + chain-contract stubs; runs under `bun` or `tsx` with zero node_modules |
| `docs/KILLSWITCH_PERSISTENCE.md` | This document |

Design invariants:

- **Account-chain law** (house rule from `src/lib/redis_chain.ts`): every Redis-facing surface
  walks the vault-provisioned chain. Persistence routes writes/reads through
  `runWithAccountChain`; a quota-dead primary cannot strand the flag on a dead account.
- **No TTL**: the state key `supremeai:autonomy-killswitch` is written with plain `SET` — an
  emergency stop must never silently expire (contrast: heartbeats use `SETEX 300s` by design).
- **Hermetic module import**: importing `killswitch_persistence.ts` performs zero I/O —
  `lib/redis_chain.js` loads lazily inside the default resolver (same pattern as the
  `await import("ioredis")` boot block in `src/index.ts`), so offline harnesses inject fake ports
  and never touch Redis/dotenv.
- **Fail-closed parsing** (U2 — UNKNOWN is never PASS): unknown `schemaVersion`, wrong types, or
  non-JSON payloads parse to `corrupt` with the reason attached; nothing is guessed.
- **Restore verdicts**: `fresh` (no key → default-enabled), `disabled` (operator stop persisted →
  integration MUST re-apply the stop), `enabled` (explicit re-enable), `unreachable` / `corrupt`
  (Redis could not answer truthfully → loud ERROR banner, boot continues; every `emergencyStop`
  re-persists and heals the key). Bricking boot on a dead Redis would turn a safety feature into
  an availability incident — the graceful-degradation precedent from `redis_chain.ts`
  ("fleet-wide blackout এড়াতে") applies.

## 3. Operator integration diffs (byte-exact, ~10 lines total)

### 3.1 `src/remediation/killswitch.ts` — persist on every state change

```diff
 export class KillSwitchManager {
   private autonomyEnabled: boolean = true;
+
+  private persist(autonomyEnabled: boolean, reason: string): void {
+    // #340 AC1: flag must survive restarts; a failed persist is a restart-
+    // resurrection bug, so failure is surfaced loudly (attempts ledger attached).
+    import("./killswitch_persistence.js")
+      .then((m) => m.persistKillSwitchState({ autonomyEnabled, reason }))
+      .then((res) => {
+        if (!res.ok) {
+          console.error(`[KILL SWITCH] ⚠️ persistence FAILED (${res.attempts.map((a) => `${a.account}: ${a.error}`).join(" | ")}) — state will NOT survive a restart`);
+        }
+      })
+      .catch((err) => console.error(`[KILL SWITCH] ⚠️ persistence crashed: ${(err as Error).message}`));
+  }

   public emergencyStop(): void {
     if (!this.autonomyEnabled) return;
-
     this.autonomyEnabled = false;
+    this.persist(false, "emergency-stop");
     console.error(`[KILL SWITCH] 🚨 AUTONOMY DISABLED. Dropping to L0 (Read-Only) Mode.`);
```

and in `enableAutonomy()`:

```diff
     this.autonomyEnabled = true;
+    this.persist(true, "admin-re-enable");
     console.log(`[KILL SWITCH] ✅ AUTONOMY RE-ENABLED.`);
```

### 3.2 `src/index.ts` — boot restore (inside `main()`, right after `validateRuntimeKnobs();`)

```diff
 async function main(): Promise<void> {
   // #109: single SSOT read for transport + fail-fast validation of every
   // numeric knob — a garbage value aborts boot here, loudly.
   validateRuntimeKnobs();
+
+  // #340 AC1: re-apply the persisted autonomy state BEFORE any task engine
+  // or scheduler work starts. Verdict semantics live in
+  // killswitch_persistence.ts; disabled → re-run the operator's stop.
+  try {
+    const { restoreKillSwitchOnBoot } = await import("./remediation/killswitch_persistence.js");
+    const restore = await restoreKillSwitchOnBoot();
+    if (restore.outcome === "disabled") {
+      const { globalKillSwitch } = await import("./remediation/killswitch.js");
+      globalKillSwitch.emergencyStop(); // re-persists the same state (idempotent)
+      console.error(`[KILL SWITCH] boot-restore: persisted EMERGENCY STOP re-applied (reason: ${restore.state?.reason ?? "unknown"})`);
+    } else if (restore.outcome === "unreachable" || restore.outcome === "corrupt") {
+      console.error(`[KILL SWITCH] ⚠️ boot-restore could not read persisted state (${restore.outcome}${restore.reason ? `: ${restore.reason}` : ""}) — autonomy default-enabled, key will heal on next emergencyStop`);
+    }
+  } catch (err) {
+    console.error(`[KILL SWITCH] ⚠️ boot-restore crashed: ${(err as Error).message}`);
+  }
   const mode = env.runtime.transport;
```

### 3.3 `src/tools/agent.tools.ts` — strict ownership validation BEFORE the write

Extend the `agent_heartbeat` tool input schema with three optional fields (after `agentId`):

```diff
       agentId: z
         .string()
         .min(1)
         .max(64)
         .optional()
         .describe("Human-readable tool label, e.g. 'Cline' (defaults to slot id)"),
+      // #340 AC2: optional task-ownership telemetry, validated fail-closed
+      // against api-schemas/heartbeat.schema.json BEFORE any Redis write.
+      taskId: z.string().max(128).optional()
+        .describe("Task the agent currently holds (empty string when idle)"),
+      status: z.enum(["alive", "busy", "idle"]).optional()
+        .describe("Lifecycle status per heartbeat.schema.json"),
+      ttlSeconds: z.number().int().min(30).max(3600).optional()
+        .describe("Lease duration in seconds (default 300)"),
```

and as the FIRST statements of the handler (after `const context = RequestContextStore.get();`):

```diff
+        // #340 AC2/AC3: fail-closed BEFORE any state modification. Bare
+        // slot-only pings pass through (legacy ok) — zero breakage for
+        // existing pingers; partial or malformed ownership is rejected with
+        // the offending field named.
+        const ownership = validateHeartbeatOwnership({ taskId, status, ttlSeconds });
+        if (!ownership.ok) {
+          return {
+            isError: true,
+            content: [{ type: "text", text: `heartbeat rejected: [${ownership.field}] ${ownership.reason}` }],
+          };
+        }
```

with the import at the top of the file:

```diff
 } from "../registry/agent_heartbeat.js";
+import { validateHeartbeatOwnership } from "../lib/heartbeat_ownership.js";
```

(Ownership is accepted-but-not-yet-stored by the registry write path; wiring the fields into
`HeartbeatRecord` is a separate, registry-owned change — this slice strictly adds the fail-closed
gate, which is what #340 AC2 mandates.)

### 3.4 `package.json` — optional wiring for the harness (recommended)

```diff
     "test:remediation": "tsx scripts/test-runner.ts test_remediation.ts",
+    "test:killswitch-persistence": "tsx selftest_killswitch_persistence.ts",
```

Not required for CI: the file is named `selftest_*` precisely so the #116 wiring guard
(`test_*.ts` at root + `test/*.ts`) does not flag it unwired before this line lands.

## 4. Acceptance mapping

| #340 AC | Delivery |
|---|---|
| AC1 — kill-switch state persisted across restarts via Redis | `killswitch_persistence.ts` (account-chain writes, no-TTL key, boot-restore verdicts) + §3.1/§3.2 diffs |
| AC2 — `agent_heartbeat` validates `taskId`/`status`/`ttlSeconds` strictly before state modification | `heartbeat_ownership.ts` validator + §3.3 diff (gate runs before `recordHeartbeat`) |
| AC3 — backward compatibility for legacy pings without ownership fields | `legacy: true` verdict for bare slot-only pings — every existing pinger unaffected |

## 5. Verification (evidence snapshot at delivery time)

- `bun selftest_killswitch_persistence.ts` → all checks pass (parse fail-closed battery, persist
  via port + via chain contract with failover ledger, load/restore × fresh|disabled|enabled|
  unreachable|corrupt, ownership legacy/strict/rejections, hermetic import) — exit 0.
- `tsc --noEmit` (strict, ES2022/NodeNext) clean over the two src modules.
- Import smoke under bun with NO `node_modules` and NO env configured — proves the hermetic
  import contract.
- The live-tower acceptance commands from the issue (`npm run build`, `npm test`) require the
  private deploy environment and are the operator's post-integration step: `npm run build` then
  `npm run test:killswitch-persistence` (§3.4).

## 6. Rollback

Delete the four files; nothing else references them until the §3 diffs are applied. The state key
`supremeai:autonomy-killswitch` in Redis can be `DEL`eted to return a stopped tower to default
autonomy after rollback.
