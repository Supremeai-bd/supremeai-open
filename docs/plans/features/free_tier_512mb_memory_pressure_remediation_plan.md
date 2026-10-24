---
id: free-tier-512mb-memory-pressure-remediation
subject: "SupremeAI — Free-Tier Memory Crisis Remediation Plan"
document_role: implementation
planning_authority: Infrastructure Circle
canonical: false
status: active
evidence_state: unverified
disposition: retain
last_verified: 2026-09-17
supersedes: []
superseded_by: []
related: docs/plans/infrastructure/free_tier_federation_master_plan.md
target_scope: supremeai_internal
---

# SupremeAI — Free-Tier Memory Crisis Remediation Plan

## লক্ষ্য

বর্তমান ~88%+ memory pressure কমানো, কোনো paid infrastructure যোগ না করে এবং 512 MB free-tier constraint বজায় রেখে।

**Scope**
1. Memory-manager cleanup/threshold/logging tuning
2. Process-local cache/object footprint কমানো
3. Production-এ exactly 1 Uvicorn worker নিশ্চিত করা

## Current Codebase Findings

### 1. `backend/core/memory_manager.py`

বর্তমানে:
- Warning threshold: 70%
- Critical threshold: 85%
- Middleware প্রতি request-এর পরে `cleanup_if_needed()` চালায়।
- Warning state-এ standard cleanup/`gc.collect()` বারবার চলতে পারে।
- `_gc_interval_seconds = 60` আছে, কিন্তু বর্তমানে কার্যকরভাবে ব্যবহার হচ্ছে না।
- Critical cleanup-এর 60s cooldown আছে, কিন্তু standard cleanup-এর নেই।
- High-memory warning/critical log request-by-request spam করতে পারে।

**Root concern:** GC-কে per-request safety mechanism বানানো হয়েছে; এতে CPU/log overhead বাড়তে পারে, অথচ live references-এর কারণে RSS কমবেই এমন নয়। fileciteturn59file0

### 2. Process-local caches

`backend/core/cache/multi_layer_cache.py`-এ Redis exact/prefix cache, semantic cache এবং in-memory session cache একসাথে আছে। Redis না থাকলে bounded in-memory fallback-ও আছে; fallback বর্তমানে 5,000 entries পর্যন্ত রাখতে পারে। fileciteturn66file0

`backend/core/cache/autocache_proxy.py`-এ:

```text
request_history = TTLCache(maxsize=1000, ttl=300)
```

আছে। fileciteturn68file0

### 3. Worker count

`backend/main.py` বর্তমানে default `UVICORN_WORKERS=1`, কিন্তু environment variable দিয়ে `>1` worker চালানো সম্ভব। 512 MB free-tier-এর জন্য production-এ এটি বন্ধ রাখা উচিত। fileciteturn63file0

---

# Phase 0 — Baseline

কোড পরিবর্তনের আগে 30–60 মিনিট realistic traffic দিয়ে record করতে হবে:

- RSS MB
- memory %
- CPU %
- request rate
- P95 latency
- 5xx rate
- GC frequency
- cache hit/miss
- Redis availability
- browser process count

Workload:

```text
idle
10 concurrent
25 concurrent
50 concurrent (যদি safe হয়)

100 requests
500 requests
1000 requests
```

বিশেষভাবে দেখবে: workload শেষ হওয়ার পর RSS baseline-এর কাছাকাছি ফেরে কি না।

---

# Phase 1 — Memory Manager Fix

File:

```text
backend/core/memory_manager.py
```

## 1.1 GC cooldown কার্যকর করা

বর্তমান unused `_gc_interval_seconds`-কে বাস্তবে ব্যবহার করতে হবে।

Desired behavior:

```text
< warning
    → no cleanup

warning
    → throttled warning
    → standard GC only if cooldown expired

critical
    → throttled critical log
    → aggressive cleanup only if cooldown expired
```

**Per-request `gc.collect()` নিষিদ্ধ।**

## 1.2 Recommended starting policy

```text
<70%       → no cleanup
70–84%     → standard cleanup, max once/60s
85–91%     → aggressive cleanup, max once/60s
>=92%      → bounded emergency response + alert
```

Threshold production metrics দেখে fine-tune করতে হবে; শুধু threshold কমিয়ে সমস্যা ঢেকে রাখা যাবে না।

## 1.3 `time.monotonic()` ব্যবহার

Cleanup/log cooldown-এর জন্য wall-clock নয়, monotonic clock ব্যবহার করতে হবে।

## 1.4 Log throttling

বর্তমান high-memory log-কে request-based না রেখে state-based করতে হবে:

```text
first crossing → log
still high     → silent
60s later      → update
recovered      → one recovery log
```

এতে log spam কমবে।

## 1.5 Unnecessary `psutil` work

Process RSS-ই মূল signal। `psutil.virtual_memory()` যদি downstream কোথাও প্রয়োজন না হয়, remove করতে হবে।

## 1.6 Production memory headers

বর্তমান middleware প্রতি response-এ:

```text
X-Memory-Used-MB
X-Memory-Percent
```

দেয়। এগুলো debug-only করা উচিত; production default-এ বন্ধ রাখা ভালো। fileciteturn59file0

## 1.7 OOM path

Emergency path bounded রাখতে হবে।

করা যাবে না:

- unlimited GC loops
- critical OOM অবস্থায় tracemalloc snapshot
- প্রতি warning-এ full cache wipe
- recursive cleanup

---

# Phase 2 — Process-Local Memory Reduction

## 2.1 পুরো backend inventory

Search:

```text
TTLCache
LRUCache
OrderedDict
lru_cache
global
singleton
request_history
session cache
memoize
dict/list/set global state
```

প্রতিটাকে classify করো:

```text
A = required state
B = useful bounded cache
C = duplicate cache
D = temporary request state
E = accidental/unbounded state
```

C/E আগে কমাতে হবে।

## 2.2 `AutoCacheProxy.request_history`

Current:

```text
1000 entries / 300s
```

প্রথম target:

```text
500 entries / 120–300s
```

Measured hit-rate খুব কম হলে 200–300-এ নামানো যাবে।

Blindly cache remove নয়; hit-rate বনাম memory benefit measure করতে হবে। fileciteturn68file0

## 2.3 In-memory Redis fallback

Current cap:

```text
5000 entries
```

Redis unavailable হলে এটি emergency fallback হিসেবে থাকবে, normal production cache হিসেবে নয়। fileciteturn66file0

Initial target:

```text
500–1000 entries
```

এবং values-এর size-ও bound করতে হবে।

## 2.4 Session cache

Session cache-এর জন্য verify:

- max entries
- TTL
- max value size
- eviction
- Redis-এর সাথে duplication

যদি Redis equivalent capability দেয়, local session cache ছোট করা বা remove করা বিবেচনা করতে হবে।

## 2.5 Cache value size limit

শুধু entry count যথেষ্ট নয়।

Example policy:

```text
MAX_LOCAL_CACHE_VALUE_BYTES
```

এর বেশি হলে process-local cache-এ store না করা।

বিশেষ করে বড় LLM responses local memory-তে duplicate রাখা যাবে না।

## 2.6 Duplicate cache layers

Measure:

```text
L1 hit %
L2 hit %
L3 hit %
L4 hit %
memory retained
latency saved
```

Low-value local layer remove/reduce করা যাবে; high-value Redis cache রাখা হবে।

## 2.7 Multi-tenant safety

Memory optimization করতে গিয়ে cache isolation নষ্ট করা যাবে না।

যেখানে প্রয়োজন cache key/context-এ থাকতে হবে:

```text
tenant
user
model
prompt/version
permissions
```

---

# Phase 3 — Exactly One Production Worker

File:

```text
backend/main.py
```

বর্তমান code default 1 worker দিলেও `UVICORN_WORKERS > 1` allow করে। fileciteturn63file0

Production target:

```text
workers = 1
```

Preferred:

- production-এ worker override ignore করা; অথবা
- production + workers > 1 হলে startup fail করা।

Local development/test-এ প্রয়োজন হলে আলাদা behavior থাকতে পারে।

## Deployment audit

Search এবং verify:

```text
render.yaml
Dockerfile
start.sh
Procfile
deployment scripts

uvicorn
gunicorn
--workers
-w
WEB_CONCURRENCY
UVICORN_WORKERS
GUNICORN_WORKERS
```

Hidden Gunicorn/Uvicorn multiplication থাকতে পারবে না।

---

# Phase 4 — Browser Memory Audit

SupremeAI-তে browser automation থাকায় GC tuning-এর পাশাপাশি browser memory আলাদা করে measure করতে হবে।

Compare:

```text
API only
API + AI
API + browser
concurrent browser
```

Verify:

- browser closes
- contexts close
- pages close
- child processes return to baseline
- screenshots/HTML retained হয় না
- browser concurrency bounded
- hard timeout আছে

যদি browser runtime-ই 88% memory-এর প্রধান কারণ হয়, শুধু GC tuning যথেষ্ট হবে না।

---

# Phase 5 — Middleware Optimization

Current pattern:

```text
request
 ↓
memory check
 ↓
request
 ↓
cleanup
```

Target:

```text
request
 ↓
cheap memory check
 ↓
request
 ↓
cleanup only if threshold + cooldown allows
```

Memory manager যেন normal request path-এর expensive operation না হয়।

---

# Phase 6 — Lightweight Observability

শুধু scalar metrics রাখবে:

```text
rss_mb
memory_percent
cleanup_count
aggressive_cleanup_count
last_cleanup_timestamp
cache_entries
cache_hits
cache_misses
```

Python process-এর মধ্যে historical samples-এর বড় list রাখা যাবে না।

History external metrics/logging system-এ যাবে।

---

# Phase 7 — Tests

Update/create:

```text
backend/tests/core/test_memory_manager.py
backend/tests/core/test_cache_optimization.py
```

## Memory tests

- [ ] below warning → no cleanup
- [ ] warning → cleanup only once per cooldown
- [ ] repeated warning → no repeated GC
- [ ] critical → aggressive cleanup
- [ ] repeated critical → cooldown respected
- [ ] log throttling works
- [ ] recovery log occurs once
- [ ] force cleanup behavior tested
- [ ] MemoryError path safe
- [ ] psutil failure safe

## Cache tests

- [ ] request history bounded
- [ ] session cache bounded
- [ ] fallback Redis bounded
- [ ] oversized local values rejected
- [ ] eviction works
- [ ] TTL works
- [ ] Redis available → fallback unused
- [ ] Redis unavailable → fallback remains bounded
- [ ] tenant/user isolation preserved

Existing cache optimization tests already cover prefix batching, idempotency fail-closed behavior এবং `request_history` TTLCache shape; নতুন memory regression tests এগুলোর ওপর add করতে হবে। fileciteturn71file0

## Worker tests

- [ ] production resolves to one worker
- [ ] production cannot accidentally use `UVICORN_WORKERS > 1`
- [ ] actual Render/Docker command verified

---

# Phase 8 — Before/After Load Test

একই workload দিয়ে compare:

| Metric | Before | After | Goal |
|---|---:|---:|---|
| Cold RSS | record | record | no regression |
| Idle RSS | record | record | lower/stable |
| Peak RSS | record | record | meaningful reduction |
| 100 req RSS | record | record | lower/stable |
| 500 req RSS | record | record | lower/stable |
| 1000 req RSS | record | record | lower/stable |
| GC/min | record | record | lower |
| logs/min | record | record | much lower |
| P95 latency | record | record | no major regression |
| 5xx | record | record | no regression |

---

# Phase 9 — Success Criteria

## Memory

- [ ] Normal traffic আর sustained 88%+ memory state তৈরি করে না।
- [ ] 512 MB limit-এর নিচে meaningful headroom থাকে।
- [ ] Repeated workload-এ RSS continuously grow করে না।
- [ ] Browser tasks memory release করে।

## Cleanup

- [ ] Per-request GC নেই।
- [ ] Standard cleanup cooldown-based।
- [ ] Aggressive cleanup cooldown-based।
- [ ] Warning/critical logs throttled।

## Cache

- [ ] সব process-local cache bounded।
- [ ] Large values locally retained হয় না।
- [ ] Redis fallback emergency-only এবং bounded।
- [ ] Duplicate/low-value local caches reduced।

## Workers

- [ ] Production exactly 1 worker।
- [ ] Hidden multi-worker configuration নেই।

## Performance

- [ ] P95 latency materially worsen করে না।
- [ ] GC-এর কারণে CPU spike নেই।
- [ ] Error rate বাড়ে না।

---

# Phase 10 — Rollout Order

```text
1. Baseline
2. Memory-manager cooldown + log throttling
3. Measure
4. Reduce process-local caches
5. Measure
6. Enforce one worker
7. Measure
8. Browser lifecycle audit
9. Full regression/load test
10. Deploy
11. Monitor
```

প্রতিটি phase independently revertible রাখতে হবে।

---

# Anti-Patterns

**করা যাবে না:**

- [ ] “Memory বেশি → আরও বেশি GC” approach
- [ ] প্রতি request-এ `gc.collect()`
- [ ] 70% হলেই সব cache clear
- [ ] measurement ছাড়া সব cache delete
- [ ] root cause না জেনে paid RAM upgrade
- [ ] unlimited request history
- [ ] বড় LLM responses process cache-এ রাখা
- [ ] 512 MB instance-এ multiple workers
- [ ] memory monitoring-এর জন্য বড় in-process history রাখা

---

# AI Coding Agent Instruction

Agent-কে এই order-এ কাজ করতে হবে:

```text
1. Read the current memory manager.
2. Inventory every process-local cache/object.
3. Inspect actual deployment worker configuration.
4. Create a baseline/regression test.
5. Fix cleanup cooldown and log throttling.
6. Stop per-request GC.
7. Bound/reduce local caches.
8. Enforce one production worker.
9. Audit browser lifecycle.
10. Run unit + integration + load tests.
11. Compare before/after RSS, CPU, latency and errors.
12. Keep only changes that improve memory without functional regression.
```

**Do not rewrite the architecture. Do not add paid services. Do not remove Redis-backed functionality merely to reduce RAM.**

---

# Definition of Done

```text
[ ] No sustained 88%+ memory under expected normal load
[ ] GC is cooldown-based
[ ] No per-request GC
[ ] Memory logs are throttled
[ ] Local caches are bounded
[ ] Large local values are rejected
[ ] Redis fallback is bounded
[ ] Exactly one production worker
[ ] Browser resources are released
[ ] Tests pass
[ ] Load test passes
[ ] No tenant/data isolation regression
[ ] No major latency regression
[ ] Rollback verified
```

## Core Philosophy

> **Measure → identify retained state → bound local memory → prevent worker multiplication → throttle cleanup → verify under load.**

Garbage collection is a last-mile mechanism; it is **not** a substitute for fixing retained objects and oversized process-local caches.