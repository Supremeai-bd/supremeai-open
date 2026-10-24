---
id: role-based-agent-ecosystem-plan
subject: "Role-Pool Agent Ecosystem — Dynamic Branch Slots, 15-Min Activity Rule, Conflict-Free Concurrency (Registry v2.1)"
document_role: architecture
planning_authority: Planning & Audit Circle (Agent-1)
canonical: true
status: implementing
evidence_state: verified
disposition: retain
last_verified: 2026-09-27
supersedes: [7-fixed-role model v1 of this document]
superseded_by: []
target_scope: supremeai_internal
related_docs:
  - docs/master_docs/AGENT_SLOT_REGISTRY.yaml
  - docs/master_docs/OPS-06-MULTI-AGENT-BRANCHING-LIFECYCLE.md
  - docs/agents/AGENT_WORK_BOUNDARIES_CHARTER.md
  - AGENTS.md
source_issue: 1439
---

> **STATUS (2026-09-27, epic #1850 Phase F truth-sync):** historical planning document.
> The final locked architecture (19 workflow files: 6 pipelines + 2 retained + 11
> libraries) landed via epic #1850 — see `integration-gate.yml`, `pr-gate.yml`,
> `nightly-ops.yml`, `ci.yml`, `ops-console.yml`, `issue-ops.yml` for the live state.
> Workflow names referenced below may differ from the final state.

# 🏛️ Role-Pool Agent Ecosystem — Implementation Plan v2

> **Status:** `implementing` · **Owner:** Planning & Audit Circle (Agent-1) · **Source:** Issue #1439 (founder directive, revised 2026-09-27)
> **Change from v1:** the earlier "7 fixed roles, one agent each" model is **superseded**. The founder's model is **role POOLS with dynamic branch slots**: any work lane can have 1..N agents at any time; branch names stay stable per pool and only increment numerically when the previous branch is still hot.

---

## 1. The Model (founder's words → architecture)

**Six work lanes (role pools).** Each pool may run **1 or more agents simultaneously**. Within a pool every agent shares the **same rules and the same GitHub App** (no per-agent special-casing — registry `role_pools.*.app` stays the single identity for the whole pool):

| Pool | Lane purpose | Branch pattern | GitHub App (fixed per pool) |
|---|---|---|---|
| `planner` | Full codebase audit, gap identification, implementation planning, backlog issues | `planner-{N}` | planner-and-auditor |
| `coder` | Business-code implementation from atomically claimed issues | `coder-{N}` | coder |
| `pr-helper` | PR gate verification, delta audit, single merge door, rollup | `pr-helper-{N}` | pr-helper (`supremeai-pr-helper[bot]`) |
| `ci` | CI/CD workflows, pipeline fixes, failure triage | `ci-{N}` | ci-action (`supremeai-ci-action[bot]`) |
| `browser` | Browser/frontend E2E exploration & verification (NEW pool — was a coder-pool side duty, agent-13) | `browser-{N}` | browser-explorer |
| `platform` | 3rd-party platform health & connectivity sweeps (Render/Upstash/CF/Supabase/…) | `platform-{N}` | platform-agent (`supremeai-platform-agent[bot]`) |

**Capacity is dynamic.** There is no fixed slot count and no global active-slot cap: the number of agents per pool is whatever the work needs, bounded only by the branch-pattern numeric space (≤100 per pool) and the merge-train queue.

---

## 2. Branch Slot Acquisition — the 15-Minute Rule (race-safe)

### 2.1 The rule (founder's directive, verbatim semantics)

> "branch last 15 min e active thakle new branch create korbe; name same thakbe, sudu numerically +1 add hobe"

An agent joining pool `P` walks the pool's numbered branches from `P-1` upward:

- If `P-n` **was active within the last 15 minutes** (latest commit younger than 15 min — another agent is working there) → skip it, look at `P-(n+1)`.
- If `P-n` is **stale** (>15 min since its last commit) or **does not exist** → claim it. No new branch is created when a stale one can be reused; a new number is only minted when every existing branch is hot.

### 2.2 Acquisition algorithm (CAS — compare-and-swap, no race windows)

Two agents may race for the same stale branch. Git itself provides the atomic lock:

```
acquire_branch(pool P):                       # runs after atomic issue claim
  for n in 1..100:
    if not branch_exists(P-n):
        # atomic create from origin/main HEAD via POST /git/refs
        # → HTTP 201 = WON (git ref creation is atomic)
        # → HTTP 422 "Reference already exists" = lost race → next n
        won = api_create_ref(P-n, origin/main.HEAD)
        if won: return P-n
    else if last_commit_age(P-n) <= 15 min:   # active → heartbeat says occupied
        continue                              # next n
    else:                                     # stale → reuse via fast-forward CAS
        # push claim commit, fast-forward-only; rejected if another claim landed
        won = push(P-n, claim_commit(P, agent_id))    # non-FF push = lost race
        if won:
            reset_branch_to(P-n, origin/main.HEAD)    # clean slate (see 2.4)
            return P-n
  error: pool exhausted (100 hot branches) — practically unreachable
```

- **Claim commit format:** `[slot-claim] pool=<P> agent=<id> ts=<ISO8601>` — one empty commit; it is simultaneously the lock, the ownership record, and the first heartbeat.
- **Activity = latest commit timestamp on the branch** (queried via `GET /repos/{owner}/{repo}/branches/{P-n}`, no extra infra). Every push refreshes it — the normal work cadence *is* the heartbeat. No separate keepalive mechanism.
- **Why CAS is safe:** `POST /git/refs` is atomic on GitHub (422 if the ref exists); a fast-forward-only push to an existing branch is rejected if anyone advanced the ref first. Losers simply walk to the next number. There is no state in which two agents believe they own the same branch.

### 2.3 Slot lifecycle state machine

```
        create (atomic 201)                push (heartbeat)
 FREE ────────────────────► ACTIVE ───────────────────► ACTIVE
   ▲                            │  last commit > 15 min │
   │  reuse via CAS claim       │                       ▼
   └────────────────────────────┴────────────────── STALE (re-claimable)
   merge → branch reset to origin/main (clean for next claimant)
```

- `ACTIVE`: last commit ≤ 15 min old. The working agent implicitly holds the lock.
- `STALE`: > 15 min idle — the agent died, finished, or is thinking. The slot is immediately re-claimable by the CAS push; the claimant resets the branch to `origin/main` first so no stale work leaks into the new task.
- Registry `expires_on` (7-day auto-deactivate) remains as a slow garbage-collection backstop; the 15-min rule is the fast one.

### 2.4 Stale-branch hygiene (no legacy work leakage)

On winning a stale branch, the claimant **resets it to `origin/main`** before doing any work:

```
git fetch origin
git checkout P-n && git reset --hard origin/main
git push --force-with-lease origin P-n   # lease = the exact SHA we CAS'd onto
```

`--force-with-lease` (not bare `--force`) keeps the race window closed: if anything moved between the CAS claim and the reset, the push aborts and the agent walks to the next number.

---

## 3. Conflict Prevention — Seven Layers (defense in depth)

The founder's requirement: *"1 or more agents aksathe kaj korle and aki slot ao multiple agents kaj korle kono conflict hobe na; merge conflict / branch behind or ahead — ei doroner aro somossha jeno na hoy."* No single mechanism can promise that; a stack of cheap guards can:

| # | Layer | Mechanism (status) | What it makes impossible |
|---|---|---|---|
| L1 | **Issue atomicity** | `scripts/ci/atomic_claim.sh` — label-swap CAS on the issue (✅ exists) | Two agents working the same issue |
| L2 | **Branch CAS acquisition** | 15-min rule + atomic ref create + FF-only claim push (🆕 this plan §2) | Two agents pushing the same branch |
| L3 | **Path-scope lanes** | Charter file-domain separation: coder→`backend/`,`frontend/`; ci→`.github/workflows/`; planner→`docs/plans/`,`docs/master_docs/`; platform→infra config (✅ charter exists) | Cross-lane file collisions by construction |
| L4 | **File collision detection** | `scripts/git/cross_pr_collision_detector.py --strict` before every push (✅ exists) | Two branches (same or different pool) silently modifying the same files |
| L5 | **Single merge door** | Only `pr-helper` pool merges; self-merge forbidden (✅ exists) | Concurrent uncoordinated lands on main |
| L6 | **Merge train single-flight** | One batch CI at a time; conflicting member → `queue:hold` quarantine + bisect, never blind retry (✅ exists) | Merge races and lost updates at land time |
| L7 | **Drift management** | Mandatory pre-PR rebase onto `origin/main`; `auto-update-pr-drift` for open PRs (update-branch **merge**, not rebase, so reviews stay valid); merge train always builds the batch from fresh `main` (✅ exists) | "Behind/ahead" surprises at review or merge time |

### 3.1 Edge-case table (every failure mode the founder named, and the layer that kills it)

| Scenario | What happens | Guarded by |
|---|---|---|
| 2 agents, same pool, different branches, **same file** | Collision detector blocks the second push before it leaves the workstation; second agent rebases + coordinates on the issue thread | L4 (+L3 usually prevents it entirely) |
| 2 agents race for the **same stale branch** | Git atomics: one wins the FF-push, loser auto-walks to next number | L2 |
| Agent dies mid-work (branch hot, then silent) | 15 min later the branch is STALE → next claimant resets it to main; the dead agent's half-work never mixes in | L2 + §2.4 |
| Branch **behind main** at PR time | Pre-PR rebase is a gate (PR Helper step-2 merge-conflict check); drift-updater keeps open PRs current | L7 |
| Branch **ahead** with stale unmerged commits from a *previous* agent | Reset-on-acquire wipes it; claim commit starts clean from main | L2 + §2.4 |
| Two PRs land at the same moment | Single merge door + single-flight merge train → serialized batch; conflict member quarantined | L5 + L6 |
| Batch member conflicts mid-rollup | Quarantined (`queue:hold`, `hold:merge-conflict`), bisect published, rest of batch lands; owner agent fixes and re-queues | L6 |
| Rebase would invalidate an in-flight review | Drift-updater uses update-branch (merge commit), review diffs stay attached | L7 |
| Same agent tries to claim a second issue's work on a busy branch | Issue claim (L1) and branch claim (L2) are independent — it must acquire a fresh branch number for the second issue | L1 + L2 |
| Pool temporarily floods (many hot branches) | Numeric space absorbs it; merge train batches N PRs into 1 CI run (cheapest possible drain) | L6 |

### 3.2 Why "conflict" here is *detected-and-routed*, never *lost*

Every layer either **prevents** (L1–L3), **detects before damage** (L4), or **serializes and quarantines** (L5–L7). The only way work is ever discarded is the deliberate §2.4 reset of a branch that was provably idle >15 min — and that is the correct semantics for an abandoned lane.

---

## 4. Registry v2.1 (changes shipped with this plan)

1. **`+ browser` pool** — `branch_pattern: browser-{N}`, app `browser-explorer`. Agent-13 (currently "browser testing specialist inside coder pool") migrates here; browser/E2E verification work stops being a coder side-duty.
2. **`acquisition_rules` block (new)** — codifies §2: 15-minute staleness window, CAS protocol, claim-commit format, numeric bound 100, reset-on-acquire, force-with-lease.
3. **`validation_rules` fixed** — the contradictory `Active slots MUST be <= 10` (OPS-06 says ≤9, registry said ≤10, reality was 11 — issue #1800) is **removed**. Replacement: *"Active branch claims per pool ≤ 100 (pattern bound). Concurrency is governed by issue-claim + branch-claim atomicity, not a global cap."* This resolves #1800 with a new **Option D — dynamic pools** (no fixed cap at all).
4. **Legacy `slots:` block** — kept one release for session continuity, annotated as deprecated: `agent-1-planner → planner-1`, `agent-3-coder-1 → coder-1`, `agent-5-ci-action → ci-1`, `agent-13 → browser-1`, `agent-11-longrun → platform-1`, etc. Migration table included; legacy entries auto-expire via `expires_on` (7 days) and are then deleted.
5. **Branch-naming regex** — `pr-pipeline.yml` + `branch-naming-guard.yml` already accept `(planner|coder|pr-helper|ci|platform)-[0-9]+`; **`browser` must be added** (CI-lane change, separate issue — the regex exists in 2 inline copies that must move in lockstep; the W1 consolidation in `docs/plans/CI_WORKFLOW_CONSOLIDATION_PLAN.md` collapses them to one).

---

## 5. Migration Phases (atomic, one issue = one branch = one PR)

| Phase | Deliverable | Lane | Issue |
|---|---|---|---|
| M1 | This plan (v2) + registry v2.1 + OPS-06 pool-section update | planner | #1439 (this PR) |
| M2 | `scripts/git/acquire_lane_slot.sh` — the §2 CAS algorithm as a CLI (gh + git; `--pool planner --agent-id <id>`; prints won branch; exit 1 on exhaustion) + unit tests | coder | new |
| M3 | Add `browser` to VALID_PATTERN in `pr-pipeline.yml` + `branch-naming-guard.yml` (both copies, lockstep) | ci | new |
| M4 | Legacy slot-branch migration: create pool branches for active agents, update AGENTS.md/OPS-06 cross-refs, delete legacy `slots:` block after expiry | platform + planner | new |
| M5 | Concurrency pilot (like #1801): two agents claim two issues in the same pool, both acquire branches via M2 script, land via merge train — verify zero conflicts end-to-end | browser/coder pilot | new |

**Dependency:** M2 → M5, M3 → M5; M1 (this PR) blocks nothing (docs are descriptive until M2/M3 land).

---

## 6. Acceptance Criteria

1. Two agents, same pool, started within the same 15-minute window, both succeed: different branch numbers, no manual coordination, no failed push.
2. A stale (>15 min) branch claimed by a new agent contains **zero** commits from the previous claimant after reset-on-acquire.
3. `browser-1` branch passes Branch Naming Guard (M3).
4. Registry validates: no active-slot cap violation possible; `browser` pool resolves; legacy block has an expiry path.
5. The M5 pilot demonstrates: 2 same-pool PRs → 1 merge-train batch → both land; or 1 lands + 1 quarantined with `hold:merge-conflict` and a bisect comment — **either** outcome is success (the guard worked).
6. #1800 closed as resolved-by-Option-D with founder ack.

---

## 7. Planner Boundary Compliance

Agent-1 authored this plan and the registry/OPS-06 doc edits (governance documents — planner domain). No workflow files modified in this PR (the regex change is CI-lane, delegated as M3). Implementation delegated per phase table. Single merge door: agent-2 merges.
