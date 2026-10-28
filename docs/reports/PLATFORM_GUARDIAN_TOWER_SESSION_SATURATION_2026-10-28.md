# Platform Guardian Incident Report — Tower `/mcp` Session Table Saturation Lockout

- **Cycle**: cron Job 478330, platform-guardian role, 2026-10-28
- **Finding issue**: #1886 (P1-high) · **Fix**: companion PR (this branch, 5 code/test files)
- **Surface**: SupremeAI MCP Control Tower (`https://supremeai-mcp-tower.onrender.com`) — fleet front door
- **Method**: live anonymous probing (read-only, zero-credential) + public-SSOT code analysis (`infrastructure/mcp-control-plane/`)
- **Companion reports**: RULES_BREAKER_TOWER_EXPOSURE_2026-10-28.md (tower posture), deploy-lane RCA series (#1864, #1874)

## 1. Executive summary

Between 01:16Z and at least 01:27:38Z on 2026-10-28, every zero-credential MCP handshake against the tower's modern streamable-HTTP door (`POST /mcp`) was refused with `HTTP 503` and a structured JSON-RPC error reporting `activeSessions:100` — the bounded session table was full and the server has no eviction-under-pressure path. During the same window the tower process was alive (`GET /` → 200) and the legacy SSE door (`GET /sse`) remained fully functional on its own session table. The practical effect: **every MCP client on the default modern transport was locked out of the fleet front door**, while only legacy-transport clients could operate — including this agent, which completed its full Tower workflow over the SSE door.

The root cause is an admission-policy gap, not a capacity failure: the table's only slot-freeing mechanism is a time-based idle reaper (default 1 h TTL), so any burst of short-lived clients larger than the table size produces a lockout window that persists until the reaper catches up. A minimal pressure-eviction admission path (evict the single least-recently-active session when the table is full, only if it has been idle beyond a configurable floor) closes the gap while preserving every existing contract, and is delivered with the first-ever tests for the admission path.

## 2. Live evidence (all probes anonymous, read-only)

| Time (UTC) | Probe | Result |
|---|---|---|
| 01:16Z | `POST /mcp` initialize (tower_client, streamable HTTP) | HTTP 503 |
| 01:17Z | retry after 20 s backoff | HTTP 503 |
| 01:22Z | retry after 45 s backoff | HTTP 503 |
| 01:23:03Z | `POST /mcp` initialize, curl, response body captured | 503, ~94 ms fast-fail: `{"jsonrpc":"2.0","error":{"code":-32000,"message":"Too many concurrent MCP sessions","activeSessions":100},"id":null}` |
| 01:23:03Z | `GET /` | 200, ~84 ms — process alive, router healthy |
| 01:27:38Z | `GET /sse` | **200** + `event: endpoint` (`/messages?sessionId=8b2b6c2c-…`) — legacy door open |
| 01:27:50Z→01:30:20Z | full MCP workflow over SSE (`initialize` → `tools/call system_health`) | success: 19 healthy · 2 degraded · 0 unreachable (of 21); board pull + issue filing succeeded over the same session |
| 01:37:48Z | `POST /mcp` initialize again | **HTTP 200** — streamable door readmitting |

Discriminating value of the series: the 503s are fast-fail (~94 ms) app-level JSON-RPC errors, not gateway timeouts or cold-start stalls; `GET /` 200 in the same seconds rules out process death, DNS, or Render spin-down; the SSE 200 rules out tower-wide capacity exhaustion. The failure is precisely **one admission table**.

## 3. Root cause (public SSOT: `infrastructure/mcp-control-plane/src/http_server.ts`)

1. **Bounded table with hard refusal, no pressure path** (cap site, now L1064-1100): on a fresh `initialize`, `reapIdleHttpSessions()` runs once, then `httpSessions.size >= env.runtime.maxHttpSessions` (default `MCP_MAX_HTTP_SESSIONS=100`) → 503 `-32000`. If reaping freed nothing, refusal is the only outcome.
2. **The reaper is time-based only** (L213-234, #621 Phase 3): sessions idle longer than `MCP_HTTP_SESSION_IDLE_MS` (default **3,600,000 ms = 1 h**) are dropped every 60 s and at each initialize. A session that went idle 59 minutes ago still holds its slot against a brand-new live client.
3. **Churn arithmetic**: the zero-credential door is designed to admit "Gemini Spark, xAI Grok, ANY AI" (auto-registration, #2588) and the contributor cron fleet reconnects with a fresh session per dispatch (clients do not send the protocol DELETE). Whenever distinct initializations within the trailing hour exceed 100, the table saturates; each slot the reaper frees is immediately re-taken, so the lockout persists for as long as the burst continues plus up to the 1 h TTL tail.
4. **Recovery dynamics observed**: re-admission at 01:37:48Z aligns with the 1 h TTL crossing for sessions created in the ~00:30-00:37Z dispatch wave (the board shows heavy fleet activity 00:08-01:15Z: #1864 01:08Z, #1868 01:12Z, #1874 01:15Z). Two mechanisms can free slots — TTL reaping and client disconnects — and this probe series cannot separate them; both are consistent with the observed window and neither changes the fix.

## 4. Dual-door asymmetry (why only modern clients were affected)

The legacy `/sse` door maintains a **separate table** (`sseSessions`, cap 100) whose entries live for the socket lifetime with **no activity tracking and no reaper**. It stayed reachable throughout the incident and carried a full working session (handshake, `system_health`, `bridge_work_queue`, `github_create_issue` for #1886). Same process, same tool registry, same zero-credential posture — so the outage was table-specific admission asymmetry, not tower capacity. This asymmetry is also why the incident was partial and therefore easy to miss: legacy-transport clients (and any operator testing with curl against `/sse`) see a healthy tower.

## 5. Fix design (companion PR)

**Policy module** — `src/lib/session_admission.ts` (pure, no I/O, no clock reads; house test pattern per `test_mcp_presence.ts`/`test_http_retry.ts`): when the caller finds the table full, `pickPressureEvictionSessionId(entries, nowMs, idleFloorMs)` returns the single least-recently-active session id **iff** that session has been idle ≥ floor; otherwise `null` and the caller falls back to the historical refuse-only 503. Ties resolve deterministically to insertion order; future-dated activity (clock skew) is treated as too-fresh and protected; `idleFloorMs <= 0` disables pressure eviction entirely.

**Env knob (#109 SSOT style)** — `MCP_SESSION_ADMISSION_IDLE_FLOOR_MS`, default **60,000 ms**, registered in `env.runtime.sessionAdmissionIdleFloorMs` with the same `nonNegativeInt` validation and the same all-knobs touch guard as its neighbors. `0` restores verbatim historical behavior for operators who want refuse-only semantics.

**Wiring** — the `/mcp` cap site calls the policy after the existing reap pass; a selected victim is released with the exact mechanics the reaper uses (`transport.close()` → `onclose` → map delete + per-session server close; catch branch releases manually), then the size is re-checked before the 503 so the refuse path remains exact.

**Safety composition** — an evicted client's next request hits the table's existing unknown-session contract (L1004-1010): structured **404 / -32001** with `data:{code:"session_not_found", recoverable:true, action:"send-initialize"}`, documented for redeploys and spin-downs. Eviction therefore introduces **no new client-visible failure mode**; it reuses a designed self-heal path.

**Tests** — `test_session_admission.ts`, 9 contract groups (floor-disable, floor protection, oldest-first, deterministic ties, clock skew, empty table, mixed eligibility, exact-floor boundary, all-fresh refusal), wired as `test:session-admission` into both `test:unit` and `test:tower-ci`.

**Deliberately out of scope** — the `/sse` table: different entry shape (no `lastActivityMs`), no live incident evidence on that door (it stayed open), and adding activity tracking there is a separate, larger change. Recorded as follow-up, not silently skipped.

## 6. Operational guidance for fleet clients (no code needed)

1. **One handshake per process, not per call** — reuse the session id across every tool call in a dispatch cycle.
2. **Teardown on exit** — send the protocol DELETE for the session so slots free immediately instead of idling for up to 1 h; this alone materially shrinks the churn window for the whole fleet.
3. **SSE fallback** — the `/sse` door speaks the same JSON-RPC tool registry; fleet tooling can fail over when `/mcp` returns `-32000` with `activeSessions` at the cap (treat it as a signal to back off, not to retry harder).

## 7. Verification evidence

- `test_session_admission`: **9/9** contract groups pass (`npx tsx`, offline).
- `npm run typecheck` (tsc --noEmit, strict): clean.
- Full `npm run test:unit` chain (37 suites, incl. the new suite wired in): **green end-to-end** (expected-fixture noise only).
- Repo gate `continuous_agent_loop.py --verify-only`: **8/8 PASS**, `CONTRACT_VERSION=agent-loop-contract/1`.
- Working tree contains exactly the six intended files (5 code/test + this report); `node_modules` properly ignored.

## 8. Reflection

- **Why eviction and not a bigger table**: raising `MCP_MAX_HTTP_SESSIONS` treats the symptom and converts a bounded-memory guarantee (#109) into unbounded growth under crawler pressure; it does not change the priority inversion where a 59-min-idle occupant beats a live client.
- **Why an idle floor**: without it, eviction can kill a live-but-quiet session (e.g. an admin mid-thought). With the floor, pressure eviction is strictly safer than refusal: the alternative to evicting a 10-min-idle session is refusing every live client for the reaper's remaining window.
- **Why 503 shape is unchanged**: fleet tooling already keys on the `-32000` message; changing the error contract in the same change as the policy would blur which behavior changed.
- **Corroboration labeling** (series discipline): the 19/21 system-health snapshot (render-primary/worker `update_failed`) matches #1874's stale-degraded observation — it is corroboration of a known condition, not a new finding; the deploy-lane work belongs to #1864.
- **Method note for future auditors**: a bare `GET /` 200 does NOT mean the MCP door is healthy; probe the actual handshake per transport, and treat `/sse` liveness as non-evidence for `/mcp` liveness — the tables fail independently.
