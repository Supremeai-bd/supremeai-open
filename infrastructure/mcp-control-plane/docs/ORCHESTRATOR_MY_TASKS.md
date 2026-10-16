# ORCHESTRATOR_MY_TASKS — Agent-Side Poll Closing the Assignment Loop

**Audit finding F3 (P1, 2026-10-16 external audit)** · governing doctrine: `docs/AUDIT_2026-10-16-external-audit.md` · delivery lane: pure-new-file drop-in (per the WO #390-pattern proven for issue #340).

---

## 1. Problem

`orchestratorDispatch()` writes a `DispatchState{issueRef,role,assignedSlot,attempts,log,updatedAt}` record to Redis (`supremeai:orchestrate:<issueRef>`, 30-day TTL) and returns. A full census found **zero readers for agent consumption** — the only consumers were the tool-layer stateKey echo and a test print. Consequence (P1): the orchestrator's `decision: assigned` is a ledger entry, not routed work. Agents have no way to discover what was assigned to their slot; assignments silently rot until the 30-day TTL expires.

The Telegram/WhatsApp push-notice variant of the audit's fix direction is a **channel + credentials ADMIN_DECISION (§6 class)** — deferred, not presumed here. The poll tool alone restores the P1 visibility: any agent can ask "what is assigned to me?" through authenticated MCP.

## 2. Design

Two new artifacts, **zero bytes changed on any existing file** (bridge hunks against live control-plane files cannot apply on the drifted private mirror — the #352-class lesson, r1–r4 all died with `patch does not apply`):

| File | Role |
|---|---|
| `src/lib/orchestrator_my_tasks.ts` | Hermetic lib: scan loop, state collection, slot filter, deterministic ordering, report formatter. **Zero static imports, zero I/O at module load, zero credential reads.** Structural types mirror the registry's `DispatchState`/`DispatchStore` — compiles against either mirror, cannot break on private-main drift. |
| `test_orchestrator_my_tasks.ts` | 30-check offline suite (FakeScanStore + injected states), imports ONLY the lib. Runs under `tsx` and `bun`. |

Contract highlights (all machine-asserted):

- **SCAN only, never KEYS** — cursor-paginated (`COUNT 1000`), bounded at 20 pages (~20k keys; orchestrate state is ≤ events/day). A bound-exceeded scan reports `partialScan: true` — it never masquerades as a full keyspace view (U2).
- **Fail-closed on scan-less stores** — a legacy store without `scan` throws an honest error; the poll tool must never fabricate an empty queue (unknown ≠ no tasks).
- **Skip-and-count corruption** — corrupt JSON, vanished keys (TTL race), and bare-prefix keys are skipped AND counted (`corruptSkipped`); one bad record never blinds the agent to the rest of the queue.
- **`assigned` and `fallback` both count** — both are real routed work; `escalate`/`no-candidate` carry `assignedSlot: null` and exclude naturally.
- **Deterministic ordering** — newest `updatedAt` first, `issueRef` ascending tiebreak; identical inputs produce byte-identical reports (asserted).
- **Honest ages** — unparseable timestamps yield `ageSeconds: null`, never a guess.
- **SSOT wiring, not duplication** — the lib's `DEFAULT_ORCHESTRATE_STATE_PREFIX` mirrors the registry constant for standalone use, and the operator wiring below passes `ORCHESTRATE_STATE_PREFIX` / `MAX_RETRIES` explicitly at the call site, so no literal can silently drift from the registry SSOT.

## 3. Operator integration diffs (byte-exact, ~35 lines across 3 files)

These hunks wire the lib into the live control plane. They are **operator-side by design**: existing control-plane files drift between the public mirror and private main, so the integration rides as documentation instead of bridge hunks (same hand-off pattern as WO #390 §3 / WO #376 Appendix A).

### 3.1 `src/registry/orchestrator_dispatch.ts` — expose SCAN on the store

Anchor: the `DispatchStore` type and `makeDispatchStore()` return objects (both the Upstash-REST and ioredis-TCP paths).

```diff
 /** Minimal Redis client over the account chain (GET/SET semantics). */
-type DispatchStore = {
+export type DispatchStore = {
   get(key: string): Promise<string | null>;
   setEx(key: string, ttlSeconds: number, value: string): Promise<void>;
+  /** F3: optional scan enables the agent-side poll path (orchestrator_my_tasks).
+   *  Absent scan = fail-closed at the poll tool (never a fake empty queue). */
+  scan?(match: string): Promise<{ keys: string[]; partial: boolean }>;
 };
```

Add the shared import once at the top of the file:

```diff
+import { scanAllKeys, SCAN_PAGE_COUNT, SCAN_MAX_PAGES } from "../lib/orchestrator_my_tasks.js";
```

Inside `makeDispatchStore()`, the Upstash REST return object gains:

```diff
       setEx: async (key, ttl, value) => {
         await call(["SET", key, value, "EX", String(ttl)]);
       },
+      // F3: SCAN over Upstash REST — same pipeline channel, quota-aware via `call`.
+      scan: async (match) => {
+        const result = await scanAllKeys(async (cursor) => {
+          return (await call([
+            "SCAN", cursor, "MATCH", match, "COUNT", String(SCAN_PAGE_COUNT),
+          ])) as [string, string[]];
+        }, match);
+        if (result.partial) {
+          console.log(`[orchestrator-dispatch] scan partial: exceeded ${SCAN_MAX_PAGES} pages for ${match}`);
+        }
+        return result;
+      },
     };
```

The ioredis TCP path gains the same method (non-blocking SCAN, never KEYS):

```diff
   const client = new (Redis as unknown as new (url: string, opts: object) => {
     get(key: string): Promise<string | null>;
     set(key: string, value: string, mode: "EX", ttl: number): Promise<"OK">;
+    scan(cursor: string, ...args: string[]): Promise<[string, string[]]>;
   })(tcpAccount.tcpUrl as string, { maxRetriesPerRequest: 2, lazyConnect: false });
   return {
     get: async (key) => client.get(key),
     setEx: async (key, ttl, value) => {
       await client.set(key, value, "EX", ttl);
     },
+    scan: async (match) =>
+      scanAllKeys(
+        (cursor) => client.scan(cursor, "MATCH", match, "COUNT", String(SCAN_PAGE_COUNT)),
+        match,
+      ),
   };
```

### 3.2 `src/tools/orchestrator.tools.ts` — register the poll tool

Anchor: `registerOrchestratorTools()`, immediately after the existing `orchestrator_dispatch` tool registration. Imports needed: `orchestratorMyTasks`, `myTasksReport`, `type MyTasksResult` from `../lib/orchestrator_my_tasks.js`.

```diff
+  server.tool(
+    "orchestrator_my_tasks",
+    `Poll the orchestrator for tasks assigned to my slot (agent-side loop closure for orchestrator_dispatch). Scans orchestrate:* state, filters by assignedSlot, newest first (cap 50, honest truncation/partial flags). Zero tasks = genuinely empty queue — scan-capable store guaranteed (fail-closed otherwise).`,
+    {
+      slot: z
+        .string()
+        .min(1)
+        .max(64)
+        .regex(/^[\w.:-]+$/)
+        .describe("My heartbeat slot id (as reported by agent_heartbeat / agent_status), e.g. coder-2 or agent-3"),
+    },
+    async ({ slot }) => {
+      const context = RequestContextStore.get();
+      if (!context?.authenticated) {
+        return {
+          isError: true,
+          content: [{ type: "text", text: "Authentication required for orchestrator_my_tasks" }],
+        };
+      }
+      try {
+        const result = await orchestratorMyTasks({
+          slot,
+          store: await makeDispatchStore(),
+          statePrefix: ORCHESTRATE_STATE_PREFIX, // SSOT — registry constant, never a duplicated literal
+        });
+        return {
+          content: [{ type: "text", text: myTasksReport(result, { maxRetries: MAX_RETRIES }) }],
+        };
+      } catch (error) {
+        return {
+          isError: true,
+          content: [
+            { type: "text", text: `orchestrator_my_tasks failed: ${error instanceof Error ? error.message : String(error)}` },
+          ],
+        };
+      }
+    },
+  );
```

(`makeDispatchStore`, `ORCHESTRATE_STATE_PREFIX`, `MAX_RETRIES` are already imported by this module's existing `orchestrator_dispatch` tool.)

### 3.3 `package.json` — test wiring (from first commit, wired in-task)

```diff
     "test:hybrid-repo-access": "tsx test_hybrid_repo_access.ts",
+    "test:orchestrator-my-tasks": "tsx test_orchestrator_my_tasks.ts",
     "test:tower-ci": "...",
```

…plus append `&& npm run test:orchestrator-my-tasks` to the `test:unit` chain and `&& npm run --silent test:orchestrator-my-tasks` to the `test:tower-ci` chain (session-14 lesson: a suite that exists but is not wired is a silent skip).

## 4. API contract

`orchestratorMyTasks({slot, store, nowMs?, limit?, statePrefix?}) → MyTasksResult`:

| Field | Meaning |
|---|---|
| `tasks[]` | `MyTaskEntry{issueRef, role, assignedSlot, attempts, updatedAt, ageSeconds, lastAudit}` — newest first, cap `limit` (default 50) |
| `scannedStates` | every `orchestrate:*` record seen (assigned and not) |
| `corruptSkipped` | corrupt / vanished / bare-prefix records skipped |
| `truncated` | more matches than `limit` |
| `partialScan` | SCAN page bound exceeded — partial keyspace view |

`myTasksReport(result, {maxRetries?, truncatedLimit?}) → string` — the agent-facing rendering: per-slot header, numbered entries with `attempts n/maxRetries` and age (or `age unknown`), last audit line, and a trailing scan-summary line carrying every honesty flag.

Error semantics: store without `scan` → throws `dispatch store does not support scan — orchestrator_my_tasks unavailable (fail-closed: cannot claim an empty queue)`; the tool maps any throw to an honest `isError` envelope.

## 5. Post-integration verification (operator, private env)

1. `npm run typecheck` → 0 errors (the lib is import-free; the wiring is type-only coupling)
2. `npm run test:orchestrator-my-tasks` → `✅ ALL ORCHESTRATOR MY-TASKS TESTS PASSED` (30 checks)
3. `npm run test:unit` / `npm run test:tower-ci` → green with the new suite wired in
4. Live smoke (authenticated MCP): call `orchestrator_my_tasks` with a real slot → report lists routed work or the explicit per-slot empty line with the scan count

## 6. Explicit non-goals (scope honesty)

- **Push notifications** (Telegram/WhatsApp dispatch notice): channel + credentials = ADMIN_DECISION class — the poll tool alone closes the P1 visibility gap; push remains an operator decision.
- **F4 (no-candidate re-evaluator)**: separate finding, separate slice — not mixed in (§4 atomic slices).
- **Registry refactor**: the store keeps `scan` OPTIONAL — legacy stores stay byte-compatible; only the poll path requires scan capability.
