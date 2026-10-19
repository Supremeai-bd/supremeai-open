# Continuous Agent Loop & Skill-Centric Architecture — Full Plan

> Saved from the SupremeAI planning session. Owner-directed design notes + implementation roadmap.
> Status: **Plan / Roadmap** (not yet implemented in full). Companion to `AGENTS.md`, `AGENT_RULES.md`, `docs/AGENT_LOOP_SPEC.md`.

---

## 1. Core Philosophy

- The **Continuous Agent Loop** is a **Lazy Team Leader & Safety Dispatcher**, NOT a worker.
  It decides *when, who, what, how, and with what tools*, then dispatches an agent.
  It never executes the task itself.
- **Agent** = the worker that completes a task.
- **Skill** = the reusable method/procedure for doing a kind of work.
- Do NOT replace the whole agent system with skills. Extract reusable workflows into skills
  incrementally; keep runtime, security, MCP, memory, and governance as-is.

### Target Architecture

```
Admin & Governance          (permission, policy, approval, security)
        │
Universal Agent Runtime     (understand task → select skill → execute → verify)
        │
Developer Skill | Auditor Skill | Healing Skill | Learning Skill | ...
        │
MCP Tools + Services + Memory   (GitHub, browser, CI, Redis, Cloudflare, DB)
```

### Benefits

- Less duplication across Developer/Auditor/Healing agents.
- Flexibility: one agent can use many skills as needed.
- Easier maintenance: updating a skill upgrades all compatible agents.
- Lower resource overhead (fewer per-task agent services).
- Better learning loop: verified solutions in memory usable by any compatible skill.

### What must NOT become a skill

| Concern | Where it stays |
|---|---|
| Reusable work procedure | Skill |
| Task scheduling & execution state | Runtime / Orchestrator |
| Long-running background workers | Service / Worker |
| Tool access & credential isolation | MCP / Security layer |
| Shared knowledge & verified experience | Memory |
| Admin approval & protected policy | Governance core |

> Skills do NOT run in the background by themselves. Hourly auditors and event-driven
> workers still need the Runtime/Orchestrator + scheduler/webhook.

---

## 2. The 8-Step Agent Lifecycle (loop contract)

1. **Understand** — pick & load the highest-priority task (issue/task board).
2. **Load Rules** — verify `AGENTS.md` / `AGENT_RULES.md` freshness vs `origin/main`.
3. **Inspect State & Preflight** — clean workspace + 3-second self-check.
4. **Atomic Claim & Branch** — `No Claim → No Branch`; rebase onto `origin/main`.
5. **Role Dispatch & Scope** — classify role via `role_trigger_matrix.py`; smallest safe diff (≤30 files, ≤200 KB).
6. **3-Tier Verification** — Reflection → Smoke → Automated regression.
7. **Pre-Push Rebase & Record** — 0 commits behind `origin/main`; PR with test evidence.
8. **Freshness Check & Next** — board re-poll, then next cycle.

### Two dispatch paradigms

**Task-driven (event/issue based):**
- Coder (🔪) — features, bug fixes, refactoring.
- CI Fixer (⚡) — failing PRs / runway CI.
- Auditor (📋+🔬) — boundary & security gate verification AND 12-satellite sync & drift audit.
  **Task Auditor and Federation Auditor are counted as ONE merged type**, not two separate agents.
  (Single auditor role covers both pre-landing compliance and federation drift.)

**Time-driven (cron/schedule based):**
- Ecosystem Scout (🔭) — external AI innovation & research tracking. Cadence: 12h.
- Human Eye (📸) — UI/UX & visual premium review. Cadence: 24h.
- Rules Breaker (🔨) — chaos/weakness testing. Cadence: 24h.
- Platform Guardian (🔌) — third-party API & rate-limit monitoring. Cadence: 24h.

> Note: Federation Auditor (🔬) is merged into the single Auditor type above (§2 task-driven),
> not a separate time-driven agent. Its 12-satellite sync/drift audit runs under the Auditor role.

---

## 3. Role-Cadence Config (time-driven dispatch)

Store cadences in a small config (not hardcoded), e.g. `agent_cadence.json`:

```json
{
  "ecosystem-scout": { "hours": 12 },
  "federation-auditor": { "hours": 12, "merged_with": "auditor" },
  "human-eye": { "hours": 24 },
  "rules-breaker": { "hours": 24 },
  "platform-guardian": { "hours": 24 }
}
```

- Keep a `last_run` timestamp store per role (memory or small state file).
- Loop check: "this role has not run in N hours → dispatch now."
- Stagger heavy audits so they never overlap.
- CI-failure → ci-fixer trigger: federation CI watchdog mirrors the failure as an issue
  with `status:runway` → loop picks it → `classify_task_role` → ci-fixer.

---

## 4. Empty-Board Handling (no issue → audit → issues)

- When the board is empty, the loop does **not** audit the project itself.
- It either creates a "full-project audit" issue, or dispatches an auditor agent with a
  mandate to create issues from findings.
- Next tick picks up those issues and dispatches role-based agents.
- An idle tick is a **healthy** tick, not a failure.

---

## 5. Implementation Roadmap (incremental, no big-bang rewrite)

1. **Baseline first:** run all test suites (root pytest, gateway, vscode, sdk-ts, mcp-tower,
   satellite guard, boundary guard, preflight). Commit the pending audit remediation only
   when green.
2. **Inventory:** list every agent capability/workflow in `scripts/agents/` and every skill
   in `skills/`. Mark duplicates.
3. **Extract pilot skill:** e.g. ecosystem-scout research flow → `skills/` (follow
   `skills/tests/test_skills_foundation.py` pattern). Add parity test.
4. **Role-cadence config + `last_run` store** (see §3).
5. **Empty-board → issue creation** (see §4).
6. **Learning feedback loop:** verified solutions (git diff scope + SHA-256 + controller-run
   tests) feed memory → usable by compatible skills.
7. **Rollout:** remove duplicate workflows only after parity tests pass.

---

## 6. Gaps to Close (honest assessment)

1. **Execution gap:** loop only suggests; something must execute (MCP/agent/CI). Add an
   auto-execution bridge or it stays a "suggester".
2. **Audit noise:** "whole project audit → issues" can create vague/noisy issues. Enforce
   strict scope + acceptance criteria + P0/P1 prioritization.
3. **Verification gaming:** agents may skip tests. Controller-run tests + diff scope +
   SHA-256 evidence verification must be mandatory.
4. **Conflict / retry:** concurrent agents conflict; atomic claim exists but rebase failures
   need retry/backoff.
5. **Learning wiring:** memory → skill feedback link is currently weak; make it explicit.
6. **Cost / priority:** 12-satellite audits every 12–24h are token-expensive; add P0/P1
   preemption + dedup.

---

## 7. Verification Commands (run before any PR)

```bash
python -m pytest -q
cd gateway && pytest
cd vscode && npm run compile && npm test
cd sdk/typescript && npm run typecheck && npm test
cd infrastructure/mcp-control-plane && npm run test:tower-ci
python scripts/ci/satellite_board_guard.py --check
python scripts/ci/boundary_sanitization_guard.py
python scripts/ci/deploy_preflight_guard.py --step2-secrets
python scripts/agents/check_loop_contract_parity.py
```

## 8. PR Discipline (AGENTS.md)

- ≤30 files, ≤200 KB diff.
- Atomic claim (`status:claimed` + `<!-- atomic-claim -->` comment) before branch.
- Pre-work rebase + pre-push rebase (0 commits behind `origin/main`).
- Board freshness re-check before declaring done.
- `Closes #N` in PR body so issues auto-close on squash merge.

---

## 11. Implementation Status (updated)

Implemented so far:
- `scripts/agents/agent_cadence.json` — role-cadence config (ecosystem-scout 12h, auditor 12h, human-eye/rules-breaker/platform-guardian 24h; merged auditor aliases).
- `continuous_agent_loop.py` — `load_cadence_config`, `canonical_role`, `load/save_last_run_store`, `role_is_due`, `due_roles`, `mark_role_run`, `create_full_project_audit_issue`.
- Empty-board branch now creates a scoped full-project audit issue before dispatching the idle auditor (both scheduled tick and manual pick-next).
- Cadence gating in `dispatch_idle_audit`: only dispatches roles whose per-role window elapsed; otherwise healthy skip (no duplicate audit spam). `last_run` recorded on dispatch.
- Pilot skill extracted: `skills/agent-cadence-dispatcher/` (SKILL.md + scripts/dispatch.py) wrapping the cadence helpers; parity test `skills/tests/test_agent_cadence_skill.py`.
- Controller-side evidence verifier: `scripts/ci/controller_evidence_verify.py` (git diff scope, SHA-256 digests, controller-run tests; fail-closed). Tests: `tests/test_controller_evidence.py` (10 passed).
- Learning feedback loop: `scripts/agents/learning_feedback.py` (record verified solutions to JSONL, promote to skill draft). Tests: `tests/test_learning_feedback.py` (6 passed).
- Execution bridge: `scripts/agents/execution_bridge.py` (validate task envelope, dry-run dispatch record, --execute fail-closed until MCP wired). Tests: `tests/test_execution_bridge.py` (12 passed).
- Tests: `tests/test_agent_cadence.py` (11 passed) + `skills/tests/test_agent_cadence_skill.py` (3 passed) + `tests/test_controller_evidence.py` (10 passed) + `tests/test_learning_feedback.py` (6 passed) + existing suites green.

Pending (next iterations):
- Auto-execution bridge (MCP) for task envelopes — requires MCP Tower integration; design documented in AGENTS.md §2 (Pathway 1/3). Implementation deferred to a dedicated task.


1. Test & commit the pending audit remediation (current uncommitted diff).
2. Build agent-capability + skill inventory (one markdown/json).
3. Extract one pilot skill + parity test.
4. Add role-cadence config + `last_run` store.
5. Add empty-board → issue creation.
6. Open PR when all tests green.

---

## 10. AI Ranking, Mistake Reduction & Plan-vs-Execution Gap Closure

### 10.1 AI Ranking Policy (assign best first, then guard)

- Always try to assign the **highest-ranked available AI** (model quality, reasoning depth,
  tool-use reliability) to a task first — especially for critical/complex tasks.
- Ranking is a *preference*, never a *trust*. A high-ranked model can still hallucinate,
  skip tests, or drift out of scope. Ranking reduces probability of error; it does not
  eliminate it.
- Therefore every AI output, regardless of model rank, must pass the same guard chain.
  No agent gets a "trusted" shortcut.

### 10.2 Layered Guard Stack (mistake → near-zero)

Apply guards in order; any single failure blocks progression (fail-closed):

1. **Constitution freshness** (`step_2_rules`): rules match `origin/main` or abort.
2. **Workspace isolation** (`step_3_inspect_state`): clean tree or abort.
3. **Atomic claim gate** (`step_4_branch`): `status:claimed` + `<!-- atomic-claim -->` before branch.
4. **Start-of-work rebase guard** (`pre_work_rebase_guard`): 0 commits behind upstream.
5. **Scope boundary guard** (`boundary_sanitization_guard`): only approved paths touched.
6. **3-Tier verification** (`step_6_verify`): py_compile → JSON/schema → full tests.
7. **Pre-push rebase guard**: branch still 0 behind `origin/main` before push.
8. **Controller-side evidence verification** (memory decision): do NOT trust the coder's
   self-report; verify git diff scope, SHA-256 of touched files, and controller-run
   tests exit 0.
9. **Board freshness re-check** before declaring done.
10. **Satellite board guard** (`satellite_board_guard`): satellites keep 0 issues/PRs.

> Principle: **system guards enforce boundaries; agents do not police themselves.**
> (AGENT_RULES.md — "System guards enforce boundaries; agents do not police themselves.")

### 10.3 Plan vs Execution — Gaps & How to Fulfill

| Gap | Why it happens | How to fulfill |
|---|---|---|
| **Execution gap** — loop only suggests, nobody runs it | No auto-execution bridge; relies on human/agent pickup | Add an MCP/agent execution bridge (Pathway 1/3) that consumes the task envelope and runs it; or a scheduled runner that invokes the loop output. |
| **Audit noise** — "audit whole project → issues" creates vague/noisy tasks | No scoping/acceptance criteria on generated issues | Generated issues must carry: scope (touching files), acceptance criteria, priority (P0–P3), group. Reject issues missing these fields. |
| **Verification gaming** — agents skip or fake tests | Self-reported evidence not independently verified | Controller runs tests itself; checks git diff scope + SHA-256; rejects on mismatch (memory decision `evidence_verification_ground_truth`). |
| **Conflict / retry** — concurrent agents collide | Atomic claim exists but rebase failures abort silently | Add retry/backoff on rebase conflict; on persistent conflict, release claim and re-queue the issue. |
| **Learning wiring weak** — verified solutions don't feed skills | Memory not connected to skill selection | On successful merge, write verified solution → memory → skill registry; skill loader prefers memory-backed skills. |
| **Cost / priority** — 12-satellite audits every 12–24h are expensive | Fixed cadence ignores real priority | P0/P1 preemption: skip scheduled audits when high-priority issues are open; dedup identical audits. |
| **Cadence drift** — fixed schedules miss "since last run of role X" | Cadence is global, not per-role | Per-role `last_run` store (§3) + per-role interval check. |
| **Dispatch not firing** — PRs merge but satellites don't update | Landing runs skipped (push-to-main events, merged-flag race, missing token) | Use `workflow_dispatch(pr_number)` reconciliation; ensure `BRIDGE_DISPATCH_TOKEN` set; verify satellite `repository_dispatch` handler exists. |
| **Dead code / unwired features** — helpers defined but unused | Incomplete wiring (e.g. `callLiveAI`/`responseFor`) | Wire or remove; CI/import check to catch unused exports. |
| **Secrets / config drift** — new `.env.example` vs actual env | Manual sync | Preflight guard (`deploy_preflight_guard`) in CI; block merge on mismatch. |

### 10.4 Fulfillment Checklist (close the gaps)

- [ ] Auto-execution bridge consumes task envelopes (MCP Tower / JIT lease).
- [ ] Generated audit issues require scope + acceptance + priority (fail-closed on missing).
- [ ] Controller-side evidence verification (diff scope, SHA-256, test exit 0) mandatory on every PR.
- [ ] Retry/backoff on rebase conflict; claim release + re-queue on failure.
- [ ] Memory → skill feedback wired (verified solution → skill registry).
- [ ] P0/P1 preemption + dedup for scheduled audits.
- [ ] Per-role `last_run` cadence tracking.
- [ ] Landing dispatch reconciliation via `workflow_dispatch`; `BRIDGE_DISPATCH_TOKEN` verified.
- [ ] Dead-code/import guard in CI.
- [ ] Preflight guard blocks merge on env mismatch.

### 10.5 Operating Principle

> Assign the best AI available first (to reduce error probability), but never trust any AI
> output without the guard chain. The guards — not the model rank — are what bring the
> mistake rate to near zero. System enforces; agents do not police themselves.

