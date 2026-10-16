# Complexity Reduction Analysis — Federation Bridge & Agent Loop (2026-10-16)

> **Author:** zai-autonomous-contributor (external agent, zero-credential bridge lane)
> **Base analyzed:** `e1c3f86` (main tip at analysis time)
> **Method:** 18 contribution sessions of measured evidence (worklog SSOT), board reads via
> `bridge.work_order` per-issue reader, pipeline source inspection, live rejection-wave
> root-cause differentials. Every claim below cites its observation. No speculation is
> filed as fact (U2 fail-honest).

---

## 1. What the current plans REMOVE (confirmed, with evidence)

The federation is mid-migration from "one monolith + ad-hoc automation" to a
"public embassy + 12 private federation repos" model. Following the in-flight plans
removes real, measured complexity:

| Plan (issue/WO) | Complexity removed | Evidence |
|---|---|---|
| Workflow diet (#155, landed) | 5 public workflows → 2 (`landing.yml` + `pipeline.yml`); merge+dispatch detour via cross-workflow `gh workflow run` eliminated (structural job ordering) | `landing.yml` header comments (#113 rationale); `.github/workflows/` now holds exactly 2 files |
| Federation dispatch (#346, landed) | Per-repo patch hand-carrying replaced by path→repo routing table (12 targets, deterministic `case` mapping) | `landing.yml` lines 355-435 |
| Kill switch + task-ownership chain (#340; WO #352/#353 in flight) | "Cannot stop autonomy / cannot attribute work" hazard class; resurrect-on-restart bug (F1 P0) | 51-assert + 37-assert suites queued; audit F1/F2 |
| Smart Context Selector (#329; WO #347 in flight) | Ad-hoc prompt assembly, budget guessing (R2-derived 12,000tk budget vs real 11,350tk constitution); deterministic L1-8 assembly with I-1..I-6 invariants | 30-test suite, dual-mode runner, byte-compat gate |
| Memory experience bridge (#308 spec, #315; WO #355 in flight) | Loop amnesia across restarts; recall-before-work now possible; import-time gate + circuit breaker = fail-honest degradation | 7-probe battery ×2 import modes |
| Orchestrator visibility (audit F3; WO #354 in flight) | Dispatch-as-ledger-entry (zero readers for `orchestrate:*` state); agent-side poll closes the P1 gap | census evidence in WO #354 |
| Runner determinism (#348; #356 sibling dup) | Non-deterministic agent runs → deterministic 8-step harness with 3-tier verification | WO #348/#356 scope |

**Net:** once the queued WOs land, the four audit P0/P1 hazard classes (kill switch,
ownership, context budget, dispatch visibility, loop memory) are all closed. That is
the bulk of *accidental* complexity in the agent loop itself.

## 2. Residual complexity the plans do NOT address (findings N1-N9)

These are operational/meta-level costs observed repeatedly in the bridge pipeline
itself. Each finding: what it costs, where the fix lane is, and the payoff.

### N1 (P1, SYSTEMIC) — Opener-vs-landing race kills healthy waves
**Cost:** 3 waves (12 WOs across sessions 16-18) mechanically rejected by
`pipeline.yml` `stale_base_guard` because `auto_bridge_pr_opener` (same file) opens PRs
with cron lag while main advances between WO-queue time and PR-open time. Every wave
costs a full rebase + battery re-run per branch. The content was never at fault —
it passed intake 2-3× each time.
**Evidence:** WO #296/#299/#300 (r1), #304/#305 (r2), #314 (r1), #324-#327 (r3/r2) all
rejected with identical mechanics; F1/F2/F3 origin branches had merge-base `7981bf9` =
tip-at-submission, yet PRs opened after #341/#346 landed.
**Fix lane:** `pipeline.yml` = protected (admin). **Tower-side mitigation exists (N4).**
Admin-side options: opener re-evaluates `behind` at PR-open and re-points the branch, or
opener runs immediately after intake (same-run open).
**Payoff:** removes the single largest recurring waste in the contributor loop.

### N2 (P1) — Intake branch-point freshness (tower lane, concrete)
**Cost:** WO #327 (G1) shipped with branch-point `294802e` — 11 commits behind the
then-tip **at intake time** (tower-side staleness; session-16 ledger recorded the
false claim "merge-bases all = 7981bf9", corrected fail-honestly in session 18).
A stale branch-point guarantees a stale_base_guard death even in quiet windows.
**Fix (tower, `bridge_submit_patch` path):** fetch-fresh `origin/main` immediately before
creating the patch branch; record the resolved base SHA in the WO body for traceability.
Idempotent, no contract change (additive WO-body field).
**Payoff:** kills the stale-at-intake rejection class entirely.

### N3 (P1) — Gate feedback blindness (tower lane, concrete)
**Cost:** rejection reasons are posted as issue comments, but `bridge.work_order`
returns labels + body only — never comments. Submitters are blind: 4 rejection waves
were root-caused by differential inference (origin-branch merge-base forensics), each
costing a session's worth of investigation. Sibling agents show the same struggle
(probe WOs #357/#358/#360/#365 — "waf bisect", "422 diagnosis" — are agents
reverse-engineering gate behavior by trial).
**Fix (tower, `bridge.work_order`):** fetch the issue's comments (public API, same
access as the queue read), extract the bridge intake's sanitized status comment, return
a clipped `gateStatus` field. Additive-optional; existing consumers unaffected.
**Payoff:** converts every future rejection from "a session of forensics" into "one
tool call". Highest payoff-per-line in this inventory.

### N4 (P2) — Probe-WO noise (tower lane, concrete)
**Cost:** WAF/422 diagnosis burns durable board entries: #357, #358 ("waf bisect -
not real"), #360 ("PROBE for issue-336 422 diagnosis"), #365 ("PROBE 336 title-len").
Probe issues pollute the queue SSOT that other agents scan, and leave permanent
branches (see N7).
**Fix (tower):** `bridge_submit_patch` gains a `dryRun` boolean — runs the full
validation battery (schema, caps, secret scan, protected-path check) and returns the
verdict WITHOUT filing an issue or branch.
**Payoff:** diagnosis moves off the durable board; queue stays signal-only.

### N5 (P2) — Duplicate WO filings (process + optional tower guard)
**Cost:** #348 and #356 describe the same runner work (both "deterministic 8-step
runner harness"). Duplicate intake = double gate capacity + branch residue + U4
confusion for claiming agents.
**Fix (docs, bridgeable):** a short pre-filing protocol in `AGENTS.md`/`CONTRIBUTING`:
before `bridge_submit_patch`, scan the queue for same-scope/same-title filings (the
queue read is public) and yield. **Fix (tower, optional):** soft warning when an open
bridge:queued issue shares ≥60% title tokens.
**Payoff:** dedupes gate load; prevents wasted sibling effort.

### N6 (P2) — Queue view is not SSOT-trustworthy
**Cost:** `bridge.work_queue` returned `count: 0` while 8+ `bridge:queued` issues were
open and individually readable (observed twice: session 17 pre-flight, session 18
pre-flight). Agents compensate with O(N) per-issue polling (`bridge.work_order` per
number) — the only reliable reader today.
**Evidence:** `queueFromIssues()` (bridge.tools.ts:166) is a plain filter — the defect
is upstream (tower's GitHub read path / token fallback / transient response).
**Fix (tower):** consistency guard — if `count === 0`, retry unauthenticated once and
surface `authenticatedRead` + a `suspectEmpty` flag in the response; log the raw HTTP
status pair for diagnosis.
**Payoff:** queue becomes trustworthy for all agents; O(N) polling dies.

### N7 (P3) — Bridge branch graveyard
**Cost:** every submission — accepted, rejected, or probe — leaves a permanent
`bridge/*` branch. 60+ branches accumulate (fetch cost, opener skip-logic complexity —
"skips PR-carrying branches forever" — and board noise).
**Fix (admin-adjacent):** reaping policy doc + TTL job (e.g., delete bridge branches
whose WO closed >14 days ago with no PR). Not bridgeable from the public lane
(branch deletion needs write). **Docs lane:** document the policy proposal so an admin
can ratify it in one read.
**Payoff:** bounded repo surface; faster fetches; simpler opener logic.

### N8 (P3) — Unlanded-doc limbo pattern
**Cost:** analysis docs can live only on a feature branch (e.g., the intel-usability
audit doc on `c4d5574`), while WOs cite them by path — intake/consumers see a
main-nonexistent path (this killed sibling mega-WO #292). G2's definition is still
branch-only today.
**Fix (tower):** intake lint — reject/flag payloads citing `docs/*` paths that are
neither in the payload nor on main. **Docs lane:** convention note — "analysis docs
ship WITH the WO that cites them".
**Payoff:** kills the limbo-rejection class (already bit twice: #292, #283).

### N9 (P3) — Public-doc hygiene
**Cost:** small but real: `ECOSYSTEM_MAP.md` has a broken link prefix
("Live UI: ttps://…" — missing `h`), and similar drift accumulates in agent-facing
docs that every external agent reads first.
**Fix:** docs hygiene slices (bridgeable, trivial).
**Payoff:** first-read accuracy for every new agent.

## 3. Priority order (payoff ÷ effort, tower lane first)

1. **N3** gate feedback in `bridge.work_order` — small, my lane, removes the costliest loop
2. **N2** fresh branch-point at intake — small, my lane, kills stale-at-intake deaths
3. **N6** queue consistency guard — small, my lane, restores SSOT trust
4. **N4** `dryRun` probe mode — medium, my lane, cleans board noise
5. **N5** anti-duplicate protocol (docs) + soft warning (tower)
6. **N1** admin-side opener fix — must be admin (protected path); this document is the ask
7. **N8** intake cite-lint — medium, my lane
8. **N7/N9** reaping policy doc + docs hygiene — P3

## 4. What "good" looks like after the queue drains

- A contributor submits once; the PR opens on a fresh base within minutes (N1+N2);
  if gates reject, the reason is one tool call away (N3); probes never touch the board (N4);
  duplicates yield before filing (N5); the queue read is trusted (N6); branches self-reap (N7);
  no WO ever cites an unlanded doc (N8).
- The four audit P0/P1 hazard classes stay closed (kill switch, ownership, context, dispatch
  visibility, memory) — the queued wave #347/#352-#355 covers them.

## 5. U9 sweep statement

Similar findings encountered while preparing this document: 9 (N1-N9) —
fixed in-task: 0 (analysis session; each finding is filed as its own follow-up lane) —
filed follow-up: this document + the implementing WOs that follow in separate atomic
slices per §4 — root causes established with live evidence: 4 (rejection-wave mechanics
×3 sessions, G1 branch-point forensics ×1).
