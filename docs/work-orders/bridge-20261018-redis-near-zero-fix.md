# Bridge Work Order: Redis near-zero — IMPLEMENTATION (bridge-20261018-redis-near-zero-fix)

Implements the plan from issue #702 / PR #703 (work order `bridge-20261018-redis-near-zero`).

> **Apply-to note:** the backend code lives in the private monorepo **Supremeai-bd/supremeai** (`backend/`). This repo carries the patch spec: apply `docs/work-orders/patches/bridge-20261018-redis-near-zero-fix.patch` on a branch of that monorepo (`git apply`; hunks are context-anchored, offsets tolerated), then deploy Render `supremeai-primary-node`.

## Changes (the patch)

### 1. `backend/core/cache/multi_layer_cache.py`
- **CACHE_SIMPLE_MODE** (default `true`): `get()` — after an L1 exact miss, returns `None` immediately (AI-call path auto-engages, identical to the existing all-layers-miss path); `set()` — writes L1 + in-memory session cache only, skips L2 semantic + L3 prefix writes (saves the 8-key mget + pipelined setex per response).
- L2/L3 code is NOT deleted — `CACHE_SIMPLE_MODE=false` restores the full 5-layer pipeline at scale.
- **ENABLE_SWARM_STREAM** (default `false`): `start_swarm_cache_invalidator()` no-ops before subscribing. Single-instance deployment (Render numInstances=1) has no cross-instance invalidation work; the PubSub listener only burned quota.

### 2. `backend/core/rate_limit.py`
- Health/telemetry endpoints (`/health`, `/api/v1/health`, `/metrics`, `/healthz`, `/api/health`) are exempt from the Redis-backed rate limiter → 0 Upstash commands per health ping. This was the dominant quota burner (~2 cmds × every ~5s internal monitor ≈ 35k+ cmds/day).

### 3. Env-only actions (Render dashboard, no deploy of code needed)
- `RATE_LIMIT_ENABLED=false` — dev-phase kill switch (limiter returns allow-all; flip back when real users arrive)
- `ENABLE_AGENT_HEARTBEAT=false` — stops the 45s heartbeat loop (~1,920 cmds/day) while in dev

## Safety analysis (why nothing breaks)
- `get()` simple-mode return is byte-equivalent to the existing miss path → `chat.py` `get_completion` / `stream_chat` fall through to the AI model call exactly as before.
- `set()` still writes L1 → exact-repeat prompts keep hitting cache.
- No new imports (os/time/logger already imported in both files).
- Fallbacks untouched: in-memory stub, `InMemoryFallbackLimiter`, circuit breaker all remain.

## Expected outcome
Daily Upstash commands: **500k → <5k** (<1%) at 2-4 active users. Failover chain remains as bonus only (owner decision).

## Acceptance criteria (from #702)
- [ ] Daily Upstash commands < 5k — verify via Upstash console metric graph after 24h
- [ ] Chat works on both L1-hit and L1-miss paths (`[simple-mode]` log line appears on miss)
- [ ] `GET /health` performs 0 Redis commands (no `atomic_window_incr` log lines for health pings)
- [ ] `CACHE_SIMPLE_MODE=false` re-enables L2/L3 (config-only rollback)

## Rollback
`git revert` the monorepo commit; or env-only: `CACHE_SIMPLE_MODE=false`, `ENABLE_SWARM_STREAM=true`.
