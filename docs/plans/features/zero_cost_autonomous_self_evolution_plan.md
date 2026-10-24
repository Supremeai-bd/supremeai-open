---
target_scope: combined_ecosystem
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:zero_cost_autonomous_self_evolution_plan
subject: SupremeAI — Self-Evolution & Zero-Cost Improvement Plan
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# SupremeAI — Self-Evolution & Zero-Cost Improvement Plan

**Status:** Proposed implementation plan  
**Date:** 2026-09-02  
**Basis:** `supremeai_how_it_learns_report.md` and the findings stated in that report  
**Primary goal:** Turn SupremeAI's existing telemetry/evolution infrastructure into a safer, persistent, measurable self-improvement loop without introducing unnecessary paid infrastructure or heavy dependencies.

---

## 1. Executive Decision

### Is the proposed plan good?

**Yes, directionally — but it should NOT be implemented exactly as a flat list of 30+ features.**

The report identifies the right architectural gaps:

- learning data persistence
- actual feedback-loop closure
- adaptive rather than fixed thresholds
- actual provider token usage
- cache effectiveness measurement
- provider performance learning
- error-pattern learning
- safer dynamic skill creation
- better cost controls

However, several recommendations in the report are too optimistic or need stronger safety constraints.

### Important corrections

1. **Do not make adaptive behavior the first step.**
   First make the current learning signals persistent, observable, deterministic, and testable.

2. **Do not let an LLM directly modify production behavior.**
   Any generated skill/configuration must pass validation, tests, security checks, policy checks, and a rollback gate.

3. **Do not use SQLite as production learning storage.**
   Production learning state should use the already-available persistent backend. Avoid adding another database.

4. **Do not assume a fixed percentage of token or cost savings.**
   Claims such as "~30% token savings", "~50% cache hit", or "~40% cost reduction" should be treated as targets to measure, not guarantees.

5. **Do not use "zero 429 errors" or "zero OOM kills" as design assumptions.**
   The system should reduce probability and recover safely; it cannot guarantee provider or platform behavior.

6. **Do not implement cross-user learning before privacy/isolation controls are explicit.**
   Shared learning must never leak user-specific content.

7. **Do not prioritize EWC/PyTorch.**
   The current architecture is primarily operational/behavioral learning. EWC is optional research infrastructure and should remain low priority unless there is a concrete model-training workload.

---

# 2. Target Architecture

The target learning loop should become:

```text
User Request
    |
    v
LLM Gateway
    |
    v
Provider Selection
    |
    v
Task Execution
    |
    +--------------------+
    |                    |
    v                    v
Telemetry            User Feedback
    |                    |
    +---------+----------+
              |
              v
      Persistent Learning Store
              |
       +------+------+
       |             |
       v             v
 Fitness        Error/Pattern Analysis
       |             |
       +------+------+
              |
              v
       Performance Oracle
              |
              v
       Candidate Improvement
              |
              v
       Safety / Policy Gate
              |
       +------+------+
       |             |
     Reject        Approve
       |             |
       v             v
    Audit log   Canary / Shadow
                     |
                     v
              Measured Validation
                     |
              +------+------+
              |             |
           Rollback       Promote
              |             |
              +------+------+
                     |
                     v
              Updated Skill /
              Parameter /
              Routing Policy
```

### Core principle

> **Observe → Learn → Propose → Validate → Measure → Promote.**

Never:

> **Observe → LLM changes production.**

---

# 3. Priority Model

## P0 — Production safety and correctness

These must happen before autonomous optimization:

1. Remove production SQLite fallback from degraded production DB paths.
2. Make learning-state persistence production-safe.
3. Fix credential/secrets exposure issues already identified by the repository audit.
4. Make AutoSkillCreator fail closed when security validation is unavailable.
5. Remove silent `MockRef` skill-loss behavior.
6. Add regression tests for all of the above.
7. Ensure every autonomous change has an audit record and rollback path.

## P1 — Close the learning loop

1. Persistent telemetry → learning store.
2. Telemetry → FitnessEngine.
3. User feedback → skill/provider/prompt scoring.
4. Error patterns → candidate improvements.
5. Prompt optimization → measured reuse.
6. Provider latency/success → routing score.
7. Cache hit/miss → routing and TTL evidence.

## P2 — Controlled adaptation

1. Adaptive fitness thresholds.
2. Adaptive provider priority.
3. Learned token-estimation ratios.
4. Smart cache TTL.
5. Time-aware routing.
6. Request deduplication.
7. Model cascading.
8. Prompt compression.

## P3 — Advanced autonomy

1. Cross-user aggregate learning with strict privacy boundaries.
2. Automated candidate skill generation at scale.
3. More sophisticated benchmark-driven optimization.
4. Optional EWC/model-training experiments.

---

# 4. Phase 0 — Safety Baseline

**Priority:** P0  
**Goal:** Make the existing system safe enough to improve itself.

## 4.1 Database degradation

### Required behavior

Production must have exactly two modes:

```text
Valid production DB
    -> normal SQLAlchemy/DB operation

Missing/broken DB + explicit degraded mode
    -> REST-only operation
    -> NO SQLite fallback
    -> SQL-dependent features unavailable
```

### Forbidden behavior

```text
Production DB failure
    -> SQLite :memory:
    -> continue as if persistent storage exists
```

### Acceptance tests

- production + valid DB → engine initializes
- production + missing DB + degradation=false → fail closed
- production + missing DB + degradation=true → no SQLAlchemy engine
- production + DB connection failure + degradation=true → no SQLite
- test/dev → SQLite may remain available if explicitly intended

---

# 5. Phase 1 — Persistent Learning Store

**Priority:** P0/P1

The report correctly identifies SQLite persistence as a major weakness.

## 5.1 Design rule

Use the project's existing persistent PostgreSQL/Supabase infrastructure rather than introducing a new database.

### Target tables

At minimum:

```text
learning_events
task_outcomes
fitness_snapshots
provider_metrics
skill_metrics
feedback_events
prompt_candidates
improvement_proposals
improvement_runs
```

## 5.2 Learning event schema

Each event should contain:

```text
event_id
timestamp
tenant_id
session_id
request_id
task_type
skill_id
provider
model
success
latency_ms
input_tokens
output_tokens
estimated_cost
actual_cost
error_class
error_hash
cache_hit
feedback
metadata
```

### Privacy rule

Do not persist raw user content by default.

Prefer:

- hashes
- task categories
- aggregate statistics
- redacted metadata
- explicit opt-in content storage where necessary

---

# 6. Phase 2 — Telemetry Quality

**Priority:** P1

The report correctly recommends connecting telemetry to the actual learning loop.

## 6.1 Required telemetry

Every LLM operation should produce a structured event.

Minimum:

```text
provider
model
task_type
latency
success
failure class
token usage
estimated cost
cache hit/miss
fallback count
retry count
```

## 6.2 Actual token usage

Replace the assumption:

```text
characters / fixed ratio = tokens
```

with:

```text
estimated tokens
+
actual provider-reported usage where available
```

Use actual usage to calibrate estimates.

### Learning process

```text
estimated_tokens
actual_tokens
      |
      v
provider/model-specific error
      |
      v
EMA / bounded calibration
      |
      v
better future estimate
```

Do not allow calibration to become unbounded or unstable.

---

# 7. Phase 3 — Fitness Engine

**Priority:** P1

The existing fitness concept is useful. Keep the current deterministic baseline before making it adaptive.

## 7.1 Baseline score

Retain measurable components such as:

```text
success rate
latency
error rate
cost
```

The exact weights should remain configurable.

## 7.2 Minimum sample size

Never change production routing based on a tiny sample.

Example policy:

```text
< 10 samples
    -> insufficient evidence

10–49 samples
    -> cautious adjustment

50+ samples
    -> normal adaptive evaluation
```

These numbers are starting policy values, not universal truths.

## 7.3 Adaptive threshold

Only after sufficient historical data exists:

```text
baseline threshold
      |
      v
historical distribution
      |
      v
bounded adaptive threshold
```

The adaptive threshold must have:

- minimum bound
- maximum bound
- change-rate limit
- rollback capability

---

# 8. Phase 4 — Provider Intelligence

**Priority:** P1/P2

The current provider priority list should become evidence-driven gradually.

## 8.1 Provider score

Possible inputs:

```text
success rate
p95 latency
rate-limit frequency
availability
estimated cost
actual cost
quality feedback
```

Example conceptual score:

```text
provider_score =
    quality_weight
  + reliability_weight
  + latency_weight
  + cost_weight
```

Do not allow a provider with insufficient observations to suddenly become the preferred provider.

## 8.2 Exploration vs exploitation

Always retain a small exploration mechanism:

```text
known-good provider
        +
limited measurement of alternatives
```

Otherwise the system can permanently lock onto an initially lucky provider.

---

# 9. Phase 5 — User Feedback Loop

**Priority:** P1

The report correctly identifies feedback as an important missing learning signal.

## 9.1 Feedback events

Support:

```text
thumbs_up
thumbs_down
retry
regenerate
follow_up
explicit correction
```

Do not interpret every follow-up as negative feedback.

## 9.2 Feedback aggregation

Aggregate by:

```text
skill
task type
provider
model
prompt template
```

Never expose one user's content to another user.

## 9.3 Confidence

A single thumbs-down must not disable a skill.

Use:

```text
feedback count
+
success rate
+
confidence interval / bounded confidence
```

before changing behavior.

---

# 10. Phase 6 — Error Pattern Learning

**Priority:** P1

The report's proposal is strong, but it needs a safe design.

## 10.1 Error fingerprint

Normalize errors into:

```text
error_class
provider
task_type
route
error_hash
```

Do not use raw stack traces as the primary key.

## 10.2 Candidate generation

Example:

```text
same error
3+ times
within time window
      |
      v
candidate investigation
```

The candidate can be:

- retry policy change
- provider fallback
- prompt change
- configuration proposal
- code fix proposal

## 10.3 No automatic production fix

Candidate:

```text
error pattern
 -> proposal
 -> test
 -> safety scan
 -> benchmark
 -> canary
 -> approval gate
```

---

# 11. Phase 7 — AutoSkillCreator Hardening

**Priority:** P0

This is one of the most important parts of the plan.

## 11.1 Security checks must fail closed

Current architecture reportedly has a dangerous weakness:

```text
security dependency unavailable
    -> dummy SecurityError fallback
    -> security check effectively disabled
```

Required:

```text
security scanner unavailable
    -> candidate rejected
```

Never:

```text
scanner unavailable
    -> assume safe
```

## 11.2 Skill lifecycle

Every generated skill should have:

```text
PROPOSED
  ↓
STATIC_CHECKED
  ↓
SECURITY_CHECKED
  ↓
TESTED
  ↓
BENCHMARKED
  ↓
CANARY
  ↓
PROMOTED
```

Failure at any stage:

```text
REJECTED
```

## 11.3 Version every skill

Store:

```text
skill_id
version
parent_version
created_at
generator
reason
fitness_before
fitness_after
tests
security_result
benchmark_result
rollback_target
```

---

# 12. Phase 8 — Prompt Optimization

**Priority:** P1/P2

The existing `prompt_optimizations` concept should become measurable.

## 12.1 Candidate lifecycle

```text
successful prompt
       ↓
candidate template
       ↓
offline evaluation
       ↓
shadow evaluation
       ↓
limited production
       ↓
measure
       ↓
promote/reject
```

## 12.2 Never optimize for one metric

A prompt is not better merely because it is faster.

Evaluate:

```text
quality
success
latency
token usage
cost
user feedback
```

---

# 13. Phase 9 — Cache Intelligence

**Priority:** P2

The report's cache recommendations are useful, but cache hit-rate targets should be measured rather than assumed.

## 13.1 Track

```text
cache_lookup
cache_hit
cache_miss
similarity_score
response_age
task_type
provider
```

## 13.2 Smart TTL

Start with a simple policy:

```text
frequently reused + stable
    -> longer TTL

rarely reused
    -> shorter TTL
```

Do not let TTL adaptation exceed configured bounds.

## 13.3 Request deduplication

For identical in-flight requests:

```text
Request A -> LLM
Request B -> wait for A
Request C -> wait for A
```

This should be implemented with bounded timeouts and cancellation handling.

---

# 14. Phase 10 — Model Cascading

**Priority:** P2

Use smaller/cheaper models for tasks that do not require maximum capability.

Example:

```text
simple classification
    -> small/cheap model

normal generation
    -> standard model

complex reasoning
    -> high-quality model
```

Routing should be based on measured quality, not only model size or price.

## Safety

If the cheap model repeatedly fails a task class:

```text
failure rate rises
    -> route task class upward
```

---

# 15. Phase 11 — Time-Aware Optimization

**Priority:** P2

The proposed time-of-day optimization is reasonable only if provider limits or reliability actually vary by time.

Collect data first:

```text
hour
provider
success
latency
rate-limit events
```

Only then derive a routing policy.

Do not assume:

```text
night = better provider
day = worse provider
```

without evidence.

---

# 16. Phase 12 — Cross-User Learning

**Priority:** P3

This should be implemented only after tenant isolation is proven.

## Allowed

Aggregate information such as:

```text
task category popularity
anonymous skill success rate
provider aggregate performance
generic prompt performance
```

## Forbidden

Using one user's:

- private prompt
- private response
- personal data
- private files
- credentials
- conversation content

to improve another user's responses without an appropriate privacy basis.

---

# 17. Phase 13 — Adaptive Optimizer

**Priority:** P2

The current AdaptiveOptimizer should become a controlled decision system.

Every optimization needs:

```text
proposal
reason
expected benefit
risk
baseline
measurement window
rollback condition
```

## Example

```text
Proposal:
Increase cache TTL from 30m to 60m

Expected:
Higher cache reuse

Risk:
Stale responses

Validation:
7-day shadow/canary comparison

Rollback:
Hit-rate or quality regression
```

---

# 18. Phase 14 — Self-Benchmark Integration

**Priority:** P1/P2

SelfBenchmark should not only report a grade.

It should become the validation layer for autonomous changes.

## Before change

```text
baseline benchmark
```

## After change

```text
candidate benchmark
```

## Promotion rule

A candidate should only be promoted when:

```text
critical metrics do not regress
AND
security passes
AND
tests pass
AND
candidate benefit exceeds minimum threshold
```

A single aggregate score is insufficient.

---

# 19. Phase 15 — Rollback Architecture

**Priority:** P0

Every autonomous change must be reversible.

## Required rollback targets

- skill version
- prompt version
- routing policy
- provider priority
- cache policy
- configuration
- generated artifacts

## Rule

> No rollback target = no autonomous promotion.

---

# 20. Observability

Create a single autonomous-evolution dashboard with:

```text
Learning events/day
Successful tasks
Failed tasks
Feedback rate
Fitness trend
Provider success
Provider p95 latency
Provider fallback rate
Cache hit rate
Token estimation error
Estimated cost
Actual cost
Generated skills
Rejected skills
Promoted skills
Rollback count
Security rejection count
Benchmark regression count
```

Most importantly:

```text
AUTONOMOUS CHANGES
------------------
proposed
validated
promoted
rejected
rolled back
```

---

# 21. Testing Strategy

Autonomous systems require stronger testing than ordinary feature code.

## 21.1 Unit tests

Test:

- fitness calculations
- token estimation
- adaptive thresholds
- provider scoring
- cache policies
- feedback aggregation
- error fingerprinting

## 21.2 Integration tests

Test:

- telemetry → database
- database → fitness
- feedback → learning
- learning → proposal
- proposal → validation
- validation → promotion
- rollback

## 21.3 Failure tests

Explicitly simulate:

- database unavailable
- Redis unavailable
- Firestore unavailable
- provider timeout
- provider 429
- malformed LLM output
- security scanner unavailable
- benchmark failure
- generated skill failure
- cancellation
- concurrent evolution jobs

## 21.4 Regression tests for current known issues

Mandatory before new autonomous features:

```text
Production DB degradation
Production SQLite fallback
Credential leakage
AutoSkillCreator security fail-open
MockRef silent loss
MCP lifecycle/async errors
```

---

# 22. Coverage Policy

Use the project's previously discussed tiered coverage philosophy.

## Core modules

Target:

```text
>= 80%
```

Failure threshold:

```text
< 80% => CI failure
```

## Critical-path tests

Target:

```text
>= 95%
```

Critical path includes:

- authentication
- provider routing
- cost guard
- persistence
- self-evolution gates
- skill installation
- rollback

## Overall project

Do not use overall coverage alone as the safety gate.

A reasonable transitional policy:

```text
Overall >= 30%
Core >= 80%
Critical path >= 95%
```

Then raise the overall target gradually as the suite grows.

---

# 23. Zero-Cost Rules

The system should follow these rules:

### Rule 1 — Reuse existing infrastructure

Prefer:

```text
existing PostgreSQL/Supabase
existing Redis
existing provider free tiers
existing Render services
existing CI
```

over adding another paid service.

### Rule 2 — No heavy dependency unless justified

Before adding a dependency:

```text
Can standard library solve it?
Can existing dependency solve it?
Can a lightweight package solve it?
Is the runtime memory cost acceptable?
```

### Rule 3 — Optional research features remain optional

EWC/PyTorch should not become a mandatory production dependency unless a concrete model-training requirement justifies it.

### Rule 4 — No fake savings

Every optimization must report:

```text
baseline
actual result
confidence
```

---

# 24. Recommended Implementation Order

## Sprint 1 — Safety

1. Fix production DB degradation.
2. Remove unsafe SQLite production fallback.
3. Harden AutoSkillCreator fail-closed behavior.
4. Remove credential exposure.
5. Fix silent skill-loss paths.
6. Add regression tests.

**Exit condition:** no known P0 autonomous-safety regression.

---

## Sprint 2 — Persistence

1. Move learning events to persistent PostgreSQL/Supabase.
2. Define learning schemas.
3. Add indexes.
4. Add retention policy.
5. Add tenant isolation.
6. Migrate existing learning data where possible.

**Exit condition:** learning survives process restart/deploy.

---

## Sprint 3 — Measurement

1. Improve telemetry.
2. Capture actual token usage.
3. Add cache hit/miss telemetry.
4. Add provider latency statistics.
5. Add feedback events.
6. Add error fingerprints.

**Exit condition:** every learning decision can be traced to measurable evidence.

---

## Sprint 4 — Learning Loop

1. Connect telemetry → FitnessEngine.
2. Connect feedback → FitnessEngine.
3. Connect error patterns → proposals.
4. Connect PerformanceOracle → candidate generation.
5. Measure prompt improvements.

**Exit condition:** the system can demonstrate a complete observe-to-proposal loop.

---

## Sprint 5 — Controlled Adaptation

1. Adaptive fitness thresholds.
2. Provider dynamic ranking.
3. Token-ratio calibration.
4. Smart TTL.
5. Request deduplication.
6. Model cascading.

**Exit condition:** adaptations are bounded, measurable, and reversible.

---

## Sprint 6 — Autonomous Promotion

1. Candidate versioning.
2. Security gate.
3. Test gate.
4. Benchmark gate.
5. Canary/shadow validation.
6. Automatic rollback.
7. Audit trail.

**Exit condition:** an autonomous change can safely move from proposal → validation → promotion → rollback.

---

# 25. Definition of Done

The self-evolution system should NOT be considered complete merely because it can generate new code.

It is complete when it can demonstrate:

```text
1. Observe
2. Persist
3. Analyze
4. Identify weakness
5. Generate candidate
6. Security-check candidate
7. Test candidate
8. Benchmark candidate
9. Compare against baseline
10. Canary candidate
11. Measure production behavior
12. Promote only if better
13. Roll back automatically if worse
14. Record the entire lifecycle
```

---

# 26. Success Metrics

Use measurable metrics instead of marketing-style claims.

## Learning

```text
% of tasks with usable telemetry
% of tasks connected to fitness
feedback coverage
error-pattern detection rate
```

## Improvement

```text
fitness delta
quality delta
latency delta
error-rate delta
token delta
cost delta
```

## Autonomy safety

```text
candidate rejection rate
security rejection rate
benchmark regression rate
rollback rate
unsafe promotion count
```

Target:

```text
unsafe autonomous promotion = 0
```

## Cost

Measure:

```text
LLM calls/request
tokens/request
cache hit rate
provider fallback rate
estimated vs actual cost
```

Do not promise a specific percentage improvement before measurement.

---

# 27. Architectural Principles

## Principle 1 — Evidence before adaptation

```text
No data
  -> no learning

Insufficient data
  -> no major change

Good evidence
  -> bounded change
```

## Principle 2 — Fail closed for safety

Security failure:

```text
reject
```

Validation failure:

```text
reject
```

Rollback unavailable:

```text
do not promote
```

## Principle 3 — Persistence before intelligence

A system cannot reliably learn from state that disappears on restart.

## Principle 4 — Measurement before optimization

First measure:

```text
baseline
```

Then optimize.

## Principle 5 — Reversibility before autonomy

Every autonomous action must be reversible.

## Principle 6 — Tenant isolation before shared learning

Cross-user intelligence comes after privacy boundaries.

## Principle 7 — Lightweight by default

The production path should not require PyTorch, sentence-transformers, or other heavyweight components unless a measured requirement justifies them.

---

# 28. Final Recommended Roadmap

```text
                    SUPREMEAI SELF-EVOLUTION
                           |
                           v
                 +-------------------+
                 | P0 SAFETY         |
                 | DB / Secrets      |
                 | Skill Security    |
                 +---------+---------+
                           |
                           v
                 +-------------------+
                 | P1 PERSISTENCE    |
                 | Telemetry Store   |
                 +---------+---------+
                           |
                           v
                 +-------------------+
                 | P1 MEASUREMENT    |
                 | Fitness / Feedback|
                 | Errors / Tokens   |
                 +---------+---------+
                           |
                           v
                 +-------------------+
                 | P1 LEARNING LOOP  |
                 | Analyze -> Propose|
                 +---------+---------+
                           |
                           v
                 +-------------------+
                 | P2 ADAPTATION     |
                 | Routing / Cache   |
                 | Token / Cascade   |
                 +---------+---------+
                           |
                           v
                 +-------------------+
                 | P2 VALIDATION     |
                 | Benchmark/Canary  |
                 +---------+---------+
                           |
                           v
                 +-------------------+
                 | P3 AUTONOMY       |
                 | Safe Promotion    |
                 | Auto Rollback     |
                 +-------------------+
```

---

# 29. Bottom Line

The uploaded report's core diagnosis is strong: SupremeAI already has many components of a self-evolution system, but several loops are only partially closed.

The most important improvement is **not adding more AI components**.

It is connecting the existing components into a reliable control loop:

> **Telemetry → Persistent Evidence → Fitness → Candidate → Security → Test → Benchmark → Canary → Measurement → Promotion/Rollback**

That is the safest path to making SupremeAI genuinely self-improving while preserving the project's lightweight and zero/near-zero-cost philosophy.

The first implementation priority should therefore be **P0 safety and persistence**, not adaptive thresholds, EWC, cross-user learning, or more autonomous code generation.