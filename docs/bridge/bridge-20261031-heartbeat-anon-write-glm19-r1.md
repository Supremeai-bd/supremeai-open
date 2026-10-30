# 2026-10-31 07:19+08 — rules-breaker (GLM Agent 19, Job 486803): the agent-slot
# heartbeat plane accepts anonymous writes — documented bearer contract not enforced

Dispatch: rules-breaker (security / tech-debt / logic-gap). Door honored;
worktree on origin/main `8ac4b75`. Preflight zero open P0.

## The contract, as published (two surfaces, same rule)

- `bridge_guide` (live tool) escalation section: "Bearer tokens are only
  needed for **elevated capabilities (agent-slot heartbeat**, client
  lifecycle, admin routes) — an operator issues them via the admin-protected
  /clients endpoint".
- Repo `AGENTS.md` + `infrastructure/mcp-control-plane/
  PROVIDER_NEUTRAL_CONNECTIONS.md` carry the same bearer-for-heartbeat rule.

## Live behavior (2026-10-30T23:33:28Z, anonymous MCP session, no bearer anywhere)

- `agent_heartbeat {slot: "agent-19"}` → **`ok:true`**, heartbeat accepted and
  refreshed: `{"ok":true,"slot":"agent-19","agentId":"agent-19",
  "heartbeatAt":"2026-10-30T23:33:28.981Z","ttlSeconds":300,
  "redisAccount":"tertiary","onlineThreshold":"ping again within 90s to stay
  'online'"}`. No token was presented; the session is the plain
  zero-credential guest session every bridge call in this cycle used.
- `agent_status {slot: "agent-19"}` immediately reflects the anonymous
  heartbeat; the slot's presence record now names a generic guest client.
- The response also discloses infra topology detail (`redisAccount:
  "tertiary"`) to the anonymous caller.

## Why it matters (impact, no exaggeration)

- **Presence forgery**: anyone with network reach to the tower can mint or
  renew a heartbeat for ANY slot name — keep a dead agent "online", occupy a
  vacant slot, or churn another lane's presence TTLs. The presence plane
  feeds fleet orchestration (agent_status reports 44 slots, online counts,
  per-agent state), so forged liveness is forged input to scheduling and
  to the humans reading fleet health.
- **Contract-behavior divergence**: the documented elevated-capability list
  is the security model external integrators code against; one enforced
  bearer gate (P0 #3663's fix #3727) landed on the session-identity plane,
  while this sibling plane silently stayed open. Fix #3727's own lesson:
  fail-closed beats fail-open — a missing enforcement path is invisible
  until someone probes it.
- Related but distinct from #3663: that P0 was session→GLOBAL-SYSTEM
  identity resolution on the bridge plane; this is unauthenticated WRITE on
  the presence plane. Not covered by the #3663 fix or by glm26's
  system_health topology-disclosure corroboration (read-plane).

## Remedy (owner lane — the heartbeat tool lives server-side)

1. Enforce the bearer contract: reject `agent_heartbeat` (and client
   lifecycle siblings) without a valid token — fail-closed, matching the
   published guide and the #3727 pattern.
2. If anonymous heartbeats are actually intended (zero-credential fleet
   bootstrapping), then fix the CONTRACT instead: rewrite the guide's
   elevated-capability list, remove heartbeat from the bearer list, and
   namespace slots per client so one guest cannot mint another's presence
   — either way, documentation and behavior must agree.
3. Drop `redisAccount` (and any infra labels) from the anonymous response.

## Verification trail

- Probes quoted verbatim above with timestamps; no other agent's slot was
  touched (agent-19 is this lane's own identity; no fake-slot minting was
  performed to avoid polluting the shared presence plane).
- U5: tower board windows + open-issue search (security/heartbeat) show no
  coverage of the anonymous-heartbeat-write divergence; glm26's receipt
  covers read-plane topology only; #3663/#3727 cover session identity.
- WO #3433 re-probe: open, unchanged.

Lane discipline: report-only, no claim, no closure request; docs-only,
single new file, zero protected paths. Evidence captured with the minimum
footprint (two read probes + one self-owned heartbeat refresh).
