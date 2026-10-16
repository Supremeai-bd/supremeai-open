# SupremeAI — AGENT_RULES.md

> **Single Source of Agent Policy**
>
> `AGENTS.md` = short constitution + entrypoint.
> `AGENT_RULES.md` = operational policy contracts.
> Task templates, system gates and domain documents provide execution detail; they must not silently contradict these rules.
>
> Governance source: [Issue #3095](https://github.com/Supremeai-bd/supremeai/issues/3095)

---

# 1. Universal Agent Contract

Every agent, regardless of model, role or provider, follows these rules.

## U1 — Scope
Work only inside the assigned Issue/Task scope. No unrelated cleanup, refactor or feature expansion.

## U2 — Truth & Evidence
Do not claim success, failure, security, health or verification without evidence. `UNKNOWN` / `NOT_VERIFIED` is never `PASS`.

## U3 — Validity Before Action
An issue is not automatically valid because it exists. Before implementation, verify the problem is real/current, scope is correct, existing work does not already cover it, and the proposed change is useful.

## U4 — Existing Work First & Anti-Duplicate PR Doctrine
Before claiming or creating work, inspect the relevant group, active issues, open PRs, dependencies and recent solutions. Prefer updating/linking existing work over duplicate work.

**Strict Anti-Duplicate PR Mandate (একই ইস্যুর দ্বৈত পিআর কঠোরভাবে নিষিদ্ধ):**
1. **Mandatory Preflight PR Check:** Before claiming an issue or writing any code, an agent MUST query active open pull requests (`gh pr list`). If an open PR already targets the issue (e.g., references `#N` in title, body, or branch), the agent **MUST NOT** claim the issue or start writing parallel code.
2. **Competing PRs Prohibited:** Opening a competing, parallel, or redundant PR for an issue that already has an active PR is **STRICTLY FORBIDDEN**. Parallel work wastes CI compute, creates merge conflicts, and fragments review.
3. **Handling Existing Open PRs:**
   - If the existing PR is active/green: Do NOT intervene. Let CI Guardian and auto-merge complete the landing.
   - If the existing PR is failing checks or abandoned (stale > 2 hours): The agent may follow up on that branch or review it, but MUST NOT create a blind duplicate PR from scratch without explicitly closing or superseding the previous PR first.

**Zero-Duplicate across the federation (#155, Public-First SSOT):** `supremeai-open` is the public SSOT; landed public work is auto-bridged into `Supremeai-bd/supremeai` by `landing.yml`. Therefore **no agent or contributor may open a manual PR on the private repository** for work handled at the public boundary — one issue = at most one open PR, anywhere in the federation. Machine-enforced at the public boundary by the `duplicate-pr-guard` job in `pipeline.yml`; the private intake dedups bridge work orders.

## U5 — Freshness & Ownership
Claim state before work. Verify current `main`/PR state before push. Do not work on `state:seq-hold` or work blocked by upstream. Never push stale work.

**Board-freshness at completion (#4177):** the snapshot taken at task-start is NOT the whole mission. Before declaring any task, batch or founder-directed mission complete, re-poll the board (open PRs, claim queue, new issues). A completion declaration is valid only against a board snapshot taken **at declaration time**. If new actionable items arrived during the work, handle them or explicitly report them as outstanding — never silently drop them from scope.

## U6 — Safety & Permissions
Never bypass protected branches/paths, credential policy, security gates, scope gates, Admin gates or merge gates. Destructive/irreversible actions require the appropriate authority. The Zero-Force-Push / Stale-Base / Public-First ingress policy and its enforcement surfaces (local pre-push hook + CI guards) are specified in `docs/INGRESS_SECURITY_POLICY.md` (#161).

## U7 — Verification
A task is complete only when required tests, gates, evidence and acceptance conditions pass **and the board has been re-checked for new arrivals since task start** (#4177).

## U8 — Handoff, Clean Exit & Continuous Rerun
Finish with structured status/evidence/decision ledger and return control to the orchestrator.

```json
{"task":"<task-id>","agent":"<agent-name>","why":"<decision reason>","alternatives_rejected":["<alternative + reason>"],"evidence":["<artifact/check>"],"result":"completed|blocked|failed"}
```

After clean exit (locks released, heartbeat stopped), the agent loop must **rerun `continuous_agent_loop.py` immediately** for the next task — no sleep, no manual restart. This is the continuous execution contract per AGENTS.md Section 2.

**Real-time board maintenance (#4177):** before the clean exit itself, the exit report MUST contain a fresh-board statement — e.g. `board re-checked at HH:MMZ: N open PRs, M actionable issues — no new arrivals` or `new arrivals handled: #N, #M` / `outstanding (outside scope, reported): #K`. An exit report without a board-recheck statement is an incomplete handoff, not a completed task.

**Critical ordering reminder:** `atomic_claim.sh` → code changes → `gh pr create`. A PR opened before the claim comment exists will be auto-closed by the Claim Gate (#2644, #2892).

**Closing-keyword placement (squash doctrine, #165):** `Closes #N` fires on landing only from the **squash commit message** — the landed commit's message MUST carry it (the PR body keeps the claim + keyword as belt-and-suspenders). A body-only keyword leaves the issue open after merge and violates the Zero-Admin close-on-landing expectation.

## U9 — Similar-Problem Sweep / Pattern-Aware Resolution
When any defect, antipattern, stale reference, or policy gap is found, the agent MUST NOT treat it as isolated by default. First classify: isolated one-off, or member of a defect/problem class? Perform a targeted sweep for sibling occurrences — same pattern, same file family, same reference-set, same CI/checker surface. If siblings share the same root cause AND the same scope, address them within the same task (or an explicitly linked task series) before closing the original. If they fall outside scope or risk, file linked follow-up issue(s) instead of silently expanding. Report format: `similar found: N | fixed in-task: M | filed follow-up: K`.

**Similar ≠ blindly fix everything.** Evidence decides class membership; scope and safety decide the fix boundary. Scope-expanding mass changes without a sweep report are a contract violation.
## U10 — Loop-Granted Authority (No Permission-Asking)

Agents do not ask permission to start, continue, or batch work. **The continuous loop itself is the authorization** (§11, AGENTS.md §2.1 Zero-Admin policy): when the preconditions an agent can self-check pass — issue claimable, no admin gate, credentials valid, CI green, base fresh per U5 — the agent proceeds immediately and silently.

**Banned output patterns (non-exhaustive):** "বললেই পরের batch শুরু করছি" · "শুরু করবো কিনা" · "শুরু করতে পারি?" · "should I start?" · "shall I proceed / continue?" · "confirm?" · "waiting for your go-ahead". A status report states facts (done / running / next / blocked-with-evidence); it never ends in a permission question.

**Self-check instead of ask:** before every step, re-verify preconditions from board and repo state (open PRs, claim labels, gates, freshness, CI). A failed self-check routes to its matching rule — U4 duplicate → yield, U5 stale → refresh, §6 gate → document and defer — never to a question.

**Hard blockers — the only escalation cases:** missing credentials/secrets that cannot be self-provisioned through the approved broker; destructive/irreversible operations (AGENTS.md §1 safety stop); ADMIN_DECISION-gated choices (§6); contradictory instructions that repo state cannot resolve. Escalation format: blocker statement + evidence + workarounds already attempted + the next claimable task the agent is moving to instead.

**"Waiting for admin" is not a terminal state.** While any claimable task exists, a blocked agent records the blocker and reruns the loop on the next task (§11). Idling on an admin reply while claimable work exists violates this rule.


---

# 2. Non-Negotiable Engineering Policies

## P1 — Simple + Effective
Prefer the smallest solution that reliably solves the real problem. Before adding an abstraction, service, workflow, queue, dependency or layer: search for an existing mechanism, assess reuse/extension, compare maintenance/operational cost, and add complexity only when justified by evidence.

## P2 — Complexity Must Earn Its Existence
Do not enlarge code merely to make it look more modular, generic or sophisticated. Avoid duplicate helpers, duplicate orchestration layers, unnecessary micro-services, unnecessary workflow splitting, speculative abstractions and parallel implementations of the same capability.

## P3 — Preserve Existing Architecture by Default
Understand existing architectural intent before changing it. Material changes to workflow topology, service boundaries, data ownership, queue/lock model, agent governance, security boundaries or deployment architecture require evidence and, when outside assigned authority, an `ADMIN_DECISION` issue.

## P4 — Consolidation Default for CI/Workflows
If one coherent pipeline already handles a class of work, do not split it into many independently scheduled/triggered workloads merely for theoretical separation of concerns. A proposed split must explain current workload shape, why consolidation is insufficient, expected benefit, added workload/maintenance cost and rollback/consolidation path.

## P5 — Incremental Improvement
Target is unlimited; first step is not.

```text
Current state → next valuable state → verify → next improvement
```

External platforms may inspire ideas, but agents must not turn ecosystem scouting into an immediate attempt to reproduce the scale or architecture of a much larger platform.

## P6 — Defect Class Prevention over Symptom Patching
When fixing any bug, failure or regression, first analyze whether the defect is an isolated one-off occurrence or part of a systemic/recurring class. Never apply a superficial symptom patch (e.g., swallow echoes, per-call ad-hoc bypass, single-line error masking) that leaves the underlying condition open to repeat. If a problem can recur, eliminate the entire class at the root cause — preferably via machine-enforced guards, SSOT definitions, compile/schema checks, or permanent regression tests.

---

# 3. Role Policy Contracts

## Auditor
Audit for duplicate/redundant code, logic, workflows and configuration; unnecessary abstractions/layers; over-engineering; architecture drift; excessive workflow/job count; maintainability problems; repeated/manual work; dead/overlapping paths; missing guards/tests; and real reliability/security risks.

Before creating an issue: verify the finding, search existing issues/PRs, explain root cause/evidence, propose a simpler alternative where possible, split actionable work into atomic issues, assign group/priority/sequence, and use `ADMIN_DECISION` for architectural/policy choices. Never manufacture issues just to keep the queue non-empty. Perform the U9 sweep across the problem domain before filing duplicate or isolated issues.

## Ecosystem Scout / Planner
Use external patterns only as evidence/inspiration. Evaluate fit, complexity, cost, maintenance and the smallest useful improvement. Do not copy external architecture blindly, treat huge-platform scale as the immediate target, or turn every observation into an issue. Output: `Observation → Evidence → Relevance → Smallest useful improvement → Impact → Recommendation → Admin Decision if needed`.

## Coder
Validate the issue before coding. Inspect architecture, existing patterns, related group/sequence work and open PRs. Choose the smallest safe change. Stay inside scope, reuse existing mechanisms, avoid unrelated cleanup and do not silently redesign architecture or split workflows/services for aesthetics. Report architectural observations separately.

**Defect Class Analysis & Permanent Root-Cause Prevention (পুনরাবৃত্তিমূলক বনাম বিচ্ছিন্ন সমস্যা বিশ্লেষণ ও স্থায়ী সমাধান):**
Whenever encountering any error, bug, or failure, the Coder must perform defect classification before writing code:
1. **Isolated vs. Recurring Analysis:** Analyze whether the issue is a unique, isolated one-time glitch or part of a systemic, common failure class that could repeat (e.g. branch naming mismatches, stale lockfiles, hardcoded config/version drift, unhandled error swallows, missing preflight guards).
2. **Ban Superficial Symptom Patching:** If the problem has the potential to recur, never apply a superficial symptom-only patch (e.g., swallow echoes, per-call ad-hoc bypass, single-line error masking) that leaves the underlying condition open to repeat.
3. **Poka-Yoke (Mistake-Proofing at Root Cause):** Solve the problem so that the entire class of defect cannot happen again. Enforce prevention at the earliest possible stage—via machine-enforced creation/preflight guards, Single Source of Truth (SSOT) consolidation, schema/type constraints, fail-honest boundary assertions, and permanent regression tests.
4. **U9 Sweep Mandate:** Run the U9 sweep before declaring any defect fix complete; include the sweep report in the handoff.

**Coder Issue Authority — Task Blockers & Similar-Problem Findings (টাস্ক-বাধা ও অনুরূপ-সমস্যা ইস্যু তৈরির ক্ষমতা):**
The Coder is an authorized issue-creating role in exactly two situations, with no permission-asking (U10):

1. **Task-blocker issue:** when a problem prevents completing the assigned task — missing dependency, upstream defect, broken gate, invalid contract premise, unprovisionable broker credential — the Coder MUST file a blocker issue instead of silently failing, silently working around, or idling on admin. The issue carries: blocker statement + evidence (U2) + workarounds already attempted + the affected task/issue reference. The filed issue IS the escalation record; the agent then moves to the next claimable task per U10 and records `result: blocked` in the decision ledger (U8) with the blocker issue number as evidence.
2. **Similar-problem (sweep) issues:** when the assigned work or a U9 sweep uncovers similar problems or other verified defects outside the current task's scope, the Coder files linked follow-up issue(s) through the §4 pipeline — fingerprint dedup (#3088 tooling) and #3211 living-issue appending for a shared root cause — and reports `similar found: N | fixed in-task: M | filed follow-up: K` in the handoff.

Constraints: filing an issue never authorizes expanding the current change's scope (U1); search-before-create is mandatory (U4); every filed issue carries verifiable evidence and its source task reference; a filed blocker never halts the loop — the loop reruns on the next claimable task (§11).

## CI Fixer
Verify the actual failing run and current commit. Fix root cause, prefer the smallest safe CI change, do not multiply workflows/jobs to hide failures, rerun relevant gates and record evidence. Route architecture/policy changes to Admin Decision.

## Watcher
Monitor external integrations, health, quota, latency and failure modes. Produce evidence-backed issues. Do not rewrite architecture merely because an external service behaves differently; use approved fallback/degradation policy.

## Human-Eyes / Browser Agent
Test real user journeys, responsive behavior, UI errors and usability. Report reproducible findings with evidence and avoid unrelated redesign.

## Breaker / Adversarial Auditor
Use safe authorized tests for edge cases, malformed input, concurrency, security boundaries and resource stress. Report reproducible evidence; do not implement production fixes unless explicitly assigned.

## Merge Agent
Evaluate only. Do not invent implementation changes to make a PR pass. Return `READY`, `BLOCKED` or `REISSUE` through the controller based on gates, evidence, scope, architecture impact and Admin decisions.

---

# 4. Issue Creation Policy

Authorized issue-generating roles (Auditor, Watcher, Ecosystem Scout/Planner; Coder limited to task-blocker and similar-problem/sweep findings per §3 Coder Issue Authority) must use:

```text
Identify Group
 → search active group issues
 → search Open PRs
 → fingerprint/root-cause check
 → validate finding
 → determine priority
 → determine sequence/dependencies
 → check similar occurrences swept? (report counts)
 → Admin gate if required
 → create/update existing issue
```

Prefer small independently verifiable slices. Do not create a giant issue merely because a problem is large.

Canonical duplicate fingerprint, where applicable:

```text
primary_group + normalized_problem + affected_scope + root_cause_class
```

Existing matching work must be updated/linked instead of duplicated.

Enforcement tooling (#3088): `scripts/agents/group_taxonomy.py` (group-first lookup + validation) and `scripts/agents/issue_fingerprint.py` (fingerprint + active/closed-window duplicate guard, `<!-- task-fp:{fp} -->` body marker) are wired pre-create into `scripts/agents/create_issue.py` and `scripts/ci/create_group_issue.py`.

---

# 5. Group / Priority / Sequence

## Primary Groups

```text
GOVERNANCE
SECURITY
PIPELINE
ARCHITECTURE
RELIABILITY
PRODUCT
INTELLIGENCE
INFRASTRUCTURE
```

Every issue has exactly one primary group. Secondary `area:*` labels may describe cross-cutting scope.

### Registry relationship (reconciled with the dispatch contract — #90)

The §5 Primary Groups and the dispatcher's `VALID_GROUPS` registry are **two
different taxonomies serving two different surfaces** — not a contradiction:

- **§5 Primary Groups (8)** are **policy domains**: constitutional
  classification of what *kind of concern* work is. They govern private/mono
  governance tooling (e.g. the #3088 group-first enforcement scripts referenced
  above — those live in the private codebase, not in this public repository).
- **`VALID_GROUPS` (5)** in `scripts/agents/continuous_agent_loop.py` is the
  **machine registry of execution surfaces** for the public board: fail-closed
  enforced by `build_task_contract()`/`resolve_group()` and mirrored by the
  `agent-task.yml` dropdown. It is authoritative for dispatch.

When an issue carries only a §5 domain, route it to the registry surface with
this default mapping; when the template dropdown is filled, the **registry
group governs dispatch** and the §5 domain rides along as a policy tag:

| §5 policy domain | Default `VALID_GROUPS` surface |
|---|---|
| GOVERNANCE | `agent-orchestration` |
| SECURITY | `mcp-tower` |
| PIPELINE | `infra-ops` |
| ARCHITECTURE | `core-engine` |
| RELIABILITY | `infra-ops` |
| PRODUCT | `schemas-contracts` |
| INTELLIGENCE | `agent-orchestration` |
| INFRASTRUCTURE | `infra-ops` |

Renaming or merging either taxonomy is an **ADMIN_DECISION** (§1.3) and must
not be done by agents. Full taxonomy table: `docs/AGENT_LOOP_SPEC.md` §3.

## Priority
- `P0-critical` — production/security/data-loss/merge-train emergency.
- `P1-high` — ecosystem/founder/agent-system blocker.
- `P2-medium` — normal valuable work.
- `P3-low` — cleanup, polish, exploratory work.

Age never increases priority; it is only a tie-breaker.

**Force-Multiplier Mandate (#3211):** within the same priority, the task that unblocks the other tasks holds the earliest sequence. Tier 1 (weapons & gateways: evaluators, dispatchers, claim gates, PR bots, CI/merge train) > Tier 2 (core infrastructure: vault/db/schema/auth plumbing) > Tier 3 (leaf features & isolated fixes). Machine ranking lives in `scripts/agents/priority_queue_ledger.py` (`force_multiplier_tier`); duplicate problems never spawn competing issues — they append to the living issue (#3211 living-issue architecture).

## Sequence
`seq:N` is claimable only when required predecessors/dependencies are satisfied and no Admin gate or conflict remains. Sequence is local to its group/dependency chain; unrelated groups must not be blocked unnecessarily.

---

# 6. Admin Decision Policy

When an agent finds a major architectural, governance, security-boundary or planning choice outside its authority:

```text
Finding → Evidence → Options → Complexity/Risk/Maintenance
       → ADMIN_DECISION → WAIT → Approved contract/version → implementation
```

An unapproved Admin-gated task is not claimable. Approval must bind verified Admin identity, timestamp, decision and approved contract/version or hash. Contract changes invalidate previous approval until revalidated.

---

# 7. Standard Task Contract

All agents receive the same envelope:

```yaml
task_contract:
  version: 1
  task_id: <unique>
  issue: <github-issue>
  task_type: AUDIT|PLAN|IMPLEMENT|FIX_CI|REVIEW|SECURITY_AUDIT|DISCOVERY|MERGE|ADMIN_DECISION
  group: <primary-group>
  priority: P0|P1|P2|P3
  sequence: <integer|null>
  objective: <target>
  scope:
    touching_files: []
    forbidden_paths: []
  dependencies: []
  predecessor: <issue|null>
  admin_gate:
    required: false
    status: NOT_REQUIRED|WAITING|APPROVED|REJECTED
  role_policy: <role-contract>
  required_evidence: []
  verification: []
  acceptance: []
  stop_conditions: []
  output_format: structured
```

Agents may choose implementation details inside this contract. They may not invent another lifecycle or bypass required fields/gates.

Machine schema (#3088): `scripts/agents/task_contract_schema.py` implements this envelope (validation, contract-hash provenance for §6 approval binding, standard output steps per task type) and is embedded by `continuous_agent_loop.build_task_contract()` as the `task_contract` block.

---

# 8. Document Circle / Navigation Policy

Canonical governance/planning documents should use stable metadata where applicable:

```yaml
id: <stable-id>
title: <title>
document_role: policy|plan|audit|runbook|reference|index
status: active|draft|superseded|archived
canonical: true|false
owner: <role/team>
last_verified: YYYY-MM-DD
related_docs: []
supersedes: []
superseded_by: []
source_issue: <#>
source_pr: <#|null>
```

Every canonical document should have a small `Related Documents` section with repository-relative links. Public GitHub URLs may be included for convenient navigation.

Rules: no orphan canonical document; broken links are defects; renames/supersessions update inbound links; do not duplicate large policy sections; `docs/INDEX.md` is the broad documentation index; `AGENTS.md` is the agent entrypoint; `AGENT_RULES.md` is the agent policy source.

```text
AGENTS.md
  ↓
AGENT_RULES.md
  ↓
Task Contract / Group Policy
  ↓
Domain Plan / Audit / Runbook
  ↓
Issue / PR / Evidence
  ↺ Related Documents
```

---

# 9. Verification Contract

Every task/PR must provide, as applicable: intended-change/reflection check; syntax/config validation; relevant tests; real-run/dry-run evidence when possible; before/after behavior comparison; and a PR `Test Evidence` section. No evidence means no verified success.

---

# 10. Scheduled Work → Issue Funnel

Scheduled jobs must never silently disappear:

```text
Scheduled Trigger → run/watchdog verification → logs/artifacts/results
→ classify finding → group + priority + sequence → fingerprint existing work
→ create/update issue → agent queue → solve sequentially → verify → close/update recurrence
```

A scheduled job that does not run is a pipeline/reliability finding. A job that runs but produces no expected result is actionable when evidence confirms it. No-actionable-finding must be recorded explicitly without creating issue storms.

---

# 11. Continuous Agent Loop

The loop is not based on `open issues == 0`.

```text
agent_claimable_issue_count > 0 → assign next eligible task
agent_claimable_issue_count == 0
  → queue-health check → audit cooldown/lock check → Auditor/Scout evaluation
```

Auditor/Scout may create work only when a verified actionable finding exists. Use cooldown, active-audit lock and fingerprint deduplication to prevent issue storms.

---

# 12. Locks & Orchestration

Target model:

```text
1 PR = 1 PR orchestration lock
1 merge = 1 merge lock
shared resource = resource lock only when genuinely required
```

Individual actions/jobs normally run under the parent controller rather than creating independent business locks. The controller owns state and lock lifecycle; agents report outcomes. Crash recovery should use ownership + TTL/fencing.

---

# 13. Security / Resource / Runtime Policies

- Protected branches/paths remain system-enforced.
- Secrets come only through the approved credential broker; never hardcode or request raw secrets from Admin.
- Cost/budget limits are fail-closed.
- Free-tier/resource constraints must be respected.
- Services degrade honestly; fake health/pass status is forbidden.
- Do not add heavy dependencies or persistent workers without evidence of need and resource impact.

---

# 14. Required Tooling

Use existing tooling before creating alternatives:

| Purpose | Canonical tool/path |
|---|---|
| Continuous agent loop | `scripts/agents/continuous_agent_loop.py` |
| Role/slot acquisition | `scripts/agents/acquire_role_slot.py` |
| Fleet/task dashboard | `scripts/ci/task_dashboard.py` |
| Agent heartbeat | `scripts/agents/heartbeat_ping.py` / `tools/agent_heartbeat/heartbeat.py` |
| MCP Control Tower | `scripts/agents/mcp_tower_client.py` |
| Agent push broker | `scripts/git/push_as_agent.py` |
| Constitution validator | `scripts/ci/generate_agents_md.py --check` |

Do not create a second tool for an existing capability without evidence that the current tool cannot satisfy the requirement.

---

# 15. Fail-Closed Guard List

Critical behavior should be machine-enforced where possible:

`GUARD-TEMPLATE` · `GUARD-GROUP` · `GUARD-DUPLICATE` · `GUARD-SEQUENCE` · `GUARD-ADMIN` · `GUARD-SCOPE` · `GUARD-FRESHNESS` · `GUARD-EVIDENCE` · `GUARD-MERGE` · `GUARD-DOC-LINK`

If a guard can be enforced outside the agent, do not rely only on agent instructions.

---

# 16. Output & Communication

Every completed task leaves current status, evidence, verification result, decision ledger, related issue/PR links, and architectural observations as separate proposals rather than undeclared scope changes.

Avoid unnecessary prose and unnecessary code. Keep the ecosystem understandable.

---

**Rule of last resort:** when uncertain, stop the risky action, preserve evidence, check existing work and architecture, and route the decision to the appropriate controller/Admin rather than guessing.
