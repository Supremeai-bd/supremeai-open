# P0 #1360 Reflection — Redis Capacity Model & Command Budgeting

Cycle: bridge-20261028-redis-p0 (Job 478316, dispatch 2026-10-28 06:05 UTC+8). Claimed via work_claim (GRANT_NEW, 30-min lease). This doc is the reflection tier of the issue's 3-tier verification contract; the smoke tier is the tower CI suite (`test:tower-ci`, credentials-free) and the tests tier is `test:redis-p0` (8 sections).

## 1. Live capacity picture (evidence: `health_full_sweep` 2026-10-27T21:16Z, guardian alert #1698)

| Chain link | State | Usage / Limit | Headroom |
|---|---|---|---|
| primary | soft-threshold hit (96% preemptive rotation, #646) | 480,000 / 500,000 | 20,000 (frozen by cooldown) |
| secondary | hard-blocked | 500,001 / 500,000 (`ERR max requests limit exceeded`) | 0 |
| tertiary | **active primary** | 0 absorbed at sweep time | 500,000 (sole buffer) |

The chain is one account deep: any traffic surge larger than tertiary's remaining 500k before the 2026-11-01T00:01Z cooldown reset becomes a fleet-wide cache/rate-limit outage for `mcp-control-plane` + `backend`. Capacity rebalancing (paid tier, account addition) is an admin/billing action — the code-side deliverables below shrink the burn instead.

## 2. Command budgeting — what each deliverable buys

- **Hot-read LRU (`hot_read_cache.ts`)**: the fleet's redundant read shape is bounded — dashboards poll the same keys, workforce listings re-read the same slots. Measured on a 100-lookup workload with 60% redundancy: **10 remote calls instead of 100 (90% absorption)**; the #1360 acceptance floor is ≥50%, asserted in tests. Every 100k absorbed lookups = 100k commands of tertiary headroom preserved. Zero extra Redis commands by design (in-memory only).
- **Three-tier alert ladder (warn 80 / high 90 / crit 95, `quotaTierFor`)**: #1522 shipped two rungs; the missing 90% rung is the "act while headroom remains" signal. In the current incident, a 90% alert on tertiary would have fired with ~50k commands of buffer instead of the hard wall at 500,001.
- **Persistent cooldown ledger (`cooldown_ledger.ts`, env `REDIS_COOLDOWN_LEDGER_PATH`)**: pre-ledger, a restart forgot that primary/secondary were quota-dead and re-probed them until an error body arrived — each wasted probe is a real command against a dead account and a real latency addition to the chain walk. Post-ledger, stamps hydrate with usage-proof validation (#1345 invariant), so restarts skip dead accounts with **zero probe commands**. Honest limit: full container recycling still loses the local file (documented in-code); Redis-side persistence is circular (a dead account cannot record its own death).

## 3. Residual risk register (honest)

1. Tertiary burn rate is unmonitored between sweeps — D1 of guardian alert #1698 (expose `estimatedCommands` for the active account per sweep) remains open for the admin surface.
2. Both blocked links share one reset instant (Nov 1 00:01Z) — staggered windows (D3) remain an ops follow-up.
3. The LRU layer is delivered as the contract's caching primitive with telemetry and is wired into CI; point-wiring additional hot call-sites is incremental work for the claiming agent(s) that follow, each one-line `withHotReadCache(...)` at a read path with a stable key.
