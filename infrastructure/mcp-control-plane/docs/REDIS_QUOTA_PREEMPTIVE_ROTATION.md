# Redis Quota — Preemptive Rotation & Command-Burn Reduction (#646)

**Scope:** `infrastructure/mcp-control-plane` (routes to the mcp-control-plane satellite)
**Contract:** the fleet must NEVER see a rejected request from the Upstash
monthly command ceiling. Reactive-only rotation (#26/#2613) still let the one
call that crossed 500,000 fail (`ERR max requests limit exceeded. Limit:
500000, Usage: 500002` — live incident). #646 rotates BEFORE the ceiling.

## 1. Preemptive rotation (AC1)

- Soft threshold = **480,000** (96% of the 500,000 free-tier limit).
- When an account's usage estimate reaches the threshold it is placed into the
  SAME cooldown registry the reactive path uses (`markAccountQuotaExhausted`) —
  until the monthly reset (1st of next month, 00:00 UTC +60s grace).
- Zero extra Redis commands: the counter is in-memory.

Usage truth tiering (honest, U2):

| Tier | Source | Role |
|---|---|---|
| 1 | Local command counter (`noteRedisCommands` — every successful REST command in heartbeat/presence/orchestrator clients) | Primary driver. A LOWER BOUND of true account usage when other services share the account. |
| 2 | Quota error body parse (`noteQuotaErrorUsage` — `Limit: X, Usage: Y`) | Reactive fallback that corrects the local estimate to the real number. |
| 3 | Response headers (`noteRedisResponseHeaders` — `x-upstash-remaining-requests` et al.) | Authoritative when the provider sends it. |

## 2. Command-burn reduction (AC2)

| Mechanism | Where | Default | Env knob (0 = off) |
|---|---|---|---|
| Heartbeat write debounce | `registry/agent_heartbeat.ts` | 60s | `REDIS_HEARTBEAT_DEBOUNCE_SECONDS` |
| Presence write debounce | `registry/mcp_presence.ts` | 60s | `REDIS_PRESENCE_DEBOUNCE_SECONDS` |
| L1 read-through cache (`listHeartbeats` / `listPresence`) | `lib/ttl_cache.ts` | 5s | `REDIS_L1_CACHE_TTL_MS` |
| Soft threshold | `lib/redis_chain.ts` | 480,000 | `UPSTASH_PREEMPTIVE_ROTATION_THRESHOLD` |
| Command limit | `lib/redis_chain.ts` | 500,000 | `UPSTASH_COMMAND_LIMIT` |

Safety analysis of the 60s write debounce: the online threshold is 90s and the
key TTL is 300s, so a debounced duplicate write cannot change any derived state
(max staleness 60s < 90s → still `online`). Failed writes never poison the
window — the debounce is recorded ONLY after the Redis write resolves.

## 3. Observability

- `quotaChainStatus()` entries now carry `usage: { estimatedCommands, limit,
  softThreshold, softThresholdHit }` (additive — existing consumers untouched).
- `redisUsageSnapshot()` — per-account window usage for dashboards/tools.
- Preemptive rotations log a `[redis-chain] PREEMPTIVE ROTATION (#646)` warning.

## 4. Verification

```text
npm run test:preemptive-rotation   # 7 scenarios (wired into test:unit)
npm run test:quota-routing         # 4/4 routed paths still shift reactively
```

The #646 regression test proves the core guarantee with a mock that NEVER
serves a quota error: rotation is observed anyway, and the post-rotation write
hits zero requests on the rotated-out account — the "zero failed requests"
property, mechanically checked.
