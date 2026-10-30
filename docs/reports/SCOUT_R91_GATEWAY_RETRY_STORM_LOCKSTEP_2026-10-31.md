# Scout Radar R91 — Gateway Retry-Storm Lockstep: zero-jitter deterministic backoff + retry-after min-cap accelerates synchronized 429/503 hammering

- **Lane:** R91 (freeness verified per the #2392 predicate at fresh main `79253684`, 2026-10-31 ~06:4x+08: tracked-tree scan zero, last-200 origin/main subjects zero, captured open-queue titles zero across 76 rows; board keyword sweep `jitter|backoff|retry|thundering|429|rate limit` zero rows — subjects disjoint from R88 vendor-drift / R89 prompt-cache / R90 gh-aw)
- **Filed by:** GLM Agent 26 (Job 486824), ecosystem-scout role, 06:26+08 dispatch, continuous-loop assigned
- **Defining artifact:** this report + WO (the bridge auto-files the defining issue on submit)
- **Verdict:** `adapt` — fix direction routed to owner lane; zero code edits by the filer (scout mandate)
- **Surface:** `gateway/provider_chain.py` — the live LLM request path (9-leg auto chain, R88 context: 429/503 is the chain's normal operating condition, not an edge case)

## Finding (one sentence)

`execute_chain()` retries a failing provider with a **deterministic, zero-jitter exponential backoff** and **caps the delay at `min(backoff, retry-after)`**, so every concurrent chain that hits the same provider blip wakes for its retry **at the same millisecond tick** (live-proven: 0.22 ms spread across 30 concurrent chains) and **re-hits a 429'd provider ~50× sooner than the provider instructed** (live-proven: `retry-after: 5.0` honored as 0.1002 s).

## Evidence (all live-verified 2026-10-31, zero-credential, against the in-repo module)

| # | Claim | Proof |
|---|---|---|
| E1 | Zero-jitter backoff on the retryable-status path | `gateway/provider_chain.py` L307–313: `delay = backoff_base_s * (2 ** retry)`; `random` appears nowhere in the module's imports (L11–22). Same deterministic form on the transport-error path, L286–288 |
| E2 | Retry-after is **under**-honored via `min()` | L310–312: `ra = result.retry_after_s; if ra is not None and ra > 0: delay = min(delay, ra)` — when the provider says "wait 5 s" and the backoff says "wait 0.1 s", the gateway waits 0.1 s. RFC 9110 §10.2.3: for 429/503 the client should wait at least the indicated period |
| E3 | **Live lockstep repro (F1)** — 30 concurrent `execute_chain()` chains, stub transport returning 503, `max_retries=1`, `backoff_base_s=0.1`: 60 attempt-wake timestamps form **two sharp clusters** — 30 wakes < 50 ms, **0 wakes in the staggered middle band (50–85 ms)**, 30 wakes ≥ 85 ms with **cluster-2 spread 0.22 ms** (min 0.1007 s). Deterministic backoff = synchronized retry ticks; with jitter the middle band would be uniformly filled. Repro source: Appendix A (imports the real module; the stub transport is the module's own documented injection seam, L6–7 "Transport is injected (attempt_fn) so tests and the SSE layer run deterministically offline") |
| E4 | **Live retry-after repro (F2)** — single chain, stub 429 carrying `retry-after: 5.0`: observed pre-retry sleep **0.1002 s** → **49.9× violation** of the provider's explicit window. On a rate-limited leg this converts a throttle into accelerated hammering, which is exactly the behavior that extends 429 lockouts |
| E5 | Docstring mis-attribution | L242: "with exponential backoff (issue #2082)" — open-repo #2082 is the tower-exposure probe WO (closed 2026-10-29, title carries no backoff/retry scope). The load-bearing docstring cites the wrong issue |
| E6 | The codebase's own convention expects jitter | `scripts/ops/advanced_analysis/queue_health_checker.py` L12 explicitly *verifies* "exponential backoff and jitter in queue retry logic"; `scripts/ops/health/check_system_health.py` L109 uses jittered backoff. The gateway request path — the highest-blast-radius retry plane — is the place the convention is missing |
| E7 | Census (secondary context, not this lane's headline) | Unjittered `2 ** retry/attempt` backoffs also at `core/database/supabase_client.py` L57/L89, `core/security/secret_vault.py` L368/L492, `core/optimization/optimized_redis_client.py` L130, `core/health/proactive_healer.py` L79, `core/services/render_preflight_service.py` L198 (day-scale cooldown), `core/tools/knowledge_squeezer/.../engine.py` L57. One convention could cover all; gateway first |

## Why it matters

The 9-leg auto chain (see R88) routinely operates through 429/503s — provider throttles are normal weather, not exceptions. Under a provider blip, every in-flight request in the process (and, with Render's multi-instance scaling, every instance) retries in **lockstep**, re-concentrating load on the exact leg the fleet just agreed to back off from. The missing jitter defeats the purpose of backoff precisely when backoff matters most. The `min()` cap independently violates the provider's own throttling contract and prolongs 429 lockouts. Both defects sit in ~6 lines and both fixes are one-liners; the surrounding honest-ledger architecture (per-attempt ledger, zero silent fallback) is untouched.

## Fix direction (owner lane; filer made zero code edits)

- **Plan-1 (core, ~2 lines each site):** full/equal jitter on both sleep sites — e.g. `delay = random.uniform(0, backoff_base_s * (2 ** retry))` (full jitter) or equal-jitter `0.5 * (backoff_base_s * 2 ** retry) + random.uniform(0, 0.5 * (backoff_base_s * 2 ** retry))` (keeps the mean); and promote retry-after from cap to **floor**: `if ra is not None and ra > 0: delay = max(delay, ra)`. Same treatment on the transport-error sleep (L287).
- **Plan-2 (tests):** extend the existing stub-transport suite with (a) a lockstep test — N concurrent chains, assert wakes fill the middle band (or: max pairwise retry-tick spread exceeds one jitter quantum); (b) a retry-after test — assert observed sleep ≥ `retry-after`. The injection seam already exists (L6–7), so both tests run offline deterministically except for the timing assertion.
- **Plan-3 (docs):** re-attribute or drop the "(issue #2082)" citation at L242.
- **Plan-4 (optional sweep):** apply the same jitter convention to the E7 census sites in one follow-up lane.

## Method note

Zero-credential throughout: the repro imports `gateway/provider_chain.py` from the working tree at `79253684`, substitutes only the transport (the module's documented seam), and measures `time.monotonic()` around the real `asyncio.sleep()` calls inside the real `execute_chain()`. No network, no keys, no vendor calls. The pass-through breaker stub isolates the backoff plane (the breaker is separately wired and correct: OPEN → HALF_OPEN after cooldown, HALF_OPEN failure → fresh OPEN, verified by reading L55–94).

## Receipt-closure convention

This report does not resolve its own subject: the lane stays open until an owner-lane PR lands Plan-1/Plan-2 (and ideally Plan-3). No `closes` claim, no code edits by the filer.

## Appendix A — live repro (runnable as-is; stdlib + the in-repo module only)

```python
import asyncio, sys, time
sys.path.insert(0, "<repo-root>")
from gateway.provider_chain import Endpoint, execute_chain

class R:  # AttemptResult-shaped stub
    def __init__(s, status, headers=None):
        s.status, s.headers = status, {k.lower(): v for k, v in (headers or {}).items()}
        s.body, s.latency_ms, s.endpoint = b"{}", 1, None
    @property
    def retry_after_s(s):
        ra = s.headers.get("retry-after")
        return None if ra is None else float(ra)

class NoBreaker:
    def allow(s, p): return True
    def record_failure(s, p): pass
    def record_success(s, p): pass

async def f1(n=30):  # lockstep proof
    log, ep = [], Endpoint(provider="openai", model="m")
    async def attempt(e, p): log.append(time.monotonic()); return R(503)
    async def one():
        try: await execute_chain((ep,), b"{}", attempt_fn=attempt, max_retries=1,
                                 backoff_base_s=0.1, circuit_breaker=NoBreaker())
        except Exception: pass
    t0 = time.monotonic(); await asyncio.gather(*[one() for _ in range(n)])
    ts = sorted(t - t0 for t in log)
    mid = [t for t in ts if 0.05 <= t < 0.085]
    c2 = [t for t in ts if t >= 0.085]
    print(f"wakes<50ms={sum(t<0.05 for t in ts)} mid(50-85ms)={len(mid)} "
          f"wakes>=85ms={len(c2)} cluster2_spread_ms={(c2[-1]-c2[0])*1000:.2f}")
    # observed: 30 / 0 / 30, spread 0.22 ms  →  lockstep, no jitter

async def f2():  # retry-after violation proof
    log, ep = [], Endpoint(provider="openai", model="m")
    async def attempt(e, p): log.append(time.monotonic()); return R(429, {"retry-after": "5.0"})
    t0 = time.monotonic()
    try: await execute_chain((ep,), b"{}", attempt_fn=attempt, max_retries=1,
                             backoff_base_s=0.1, circuit_breaker=NoBreaker())
    except Exception: pass
    print(f"sleep={log[1]-log[0]:.4f}s (retry-after 5.0)")  # observed: 0.1002s → 49.9x violation

asyncio.run(f1()); asyncio.run(f2())
```
