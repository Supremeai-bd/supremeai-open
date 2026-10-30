# AGENT LOOP SPEC — Single Deterministic Task Envelope (task-envelope-v1)

> Source of truth: `scripts/agents/continuous_agent_loop.py`
> Ref: issue #63 · Philosophy: `AGENTS.md` §6 — *"Simple + effective > clever + complex."*

## 1. Why

Before #63 the loop runner produced **4 disparate output formats** that external
autonomous agents (Z.ai, Claude, Antigravity, …) had to reconcile:

| # | Legacy format | Replaced by (envelope field) |
|---|---------------|------------------------------|
| 1 | Multi-step terminal console logs | `problem_statement` + `objective` |
| 2 | `--emit-prompt` markdown specialist prompt | `specialist_prompt` |
| 3 | `--emit-contract` raw JSON contract | embedded contract fields (`group`, `scope`, `admin_gate`, …) |
| 4 | `.pr_template_draft.md` filesystem draft | `submission.pr_body_template` |

Now there is **one** canonical payload: `--task-envelope` → `task_envelope` JSON.

## 2. Envelope schema (v1)

```jsonc
{
  "task_envelope": {
    "envelope_version": 1,
    "output_format": "task-envelope-v1",
    "task_id":   "task-63",
    "issue":     "63",
    "task_type": "IMPLEMENT",          // VALID_TASK_TYPES
    "group":     "core",               // VALID_GROUPS registry — fail-closed
    "priority":  "P2",                 // P0..P3
    "objective": "…",
    "problem_statement": { "id", "title", "body", "labels", "state" },
    "role": "coder",                   // one of the 7 specialist roles
    "role_policy": "contributor",
    "role_description": "…",
    "scope": {
      "touching_files": ["…"],         // Scope Gate boundary
      "forbidden_paths": [".env*", "secrets/**", "credentials/**", "vault/**"]
    },
    "acceptance": ["…"],
    "verification": ["…"],
    "required_evidence": ["…"],
    "stop_conditions": ["…"],
    "admin_gate": { "required": false, "status": "NOT_REQUIRED" },
    "specialist_prompt": "…markdown prompt (legacy --emit-prompt content)…",
    "submission": {
      "pathway": "bridge_submit_patch | pull_request",
      "reference": "AGENTS.md §2.1 Pathway 1 + §8 (bridge_submit_patch)",
      "base_branch": "main",
      "pr_title_prefix": "feat(open):",
      "issue_reference_required": true,
      "branch_convention": "^(feat|fix|docs|…|agent)/<slug> — enforced by pipeline.yml",
      "pr_body_template": "…markdown PR body (legacy draft file content)…"
    }
  }
}
```

## 3. Group taxonomy — `VALID_GROUPS` (fail-closed)

Agents **cannot** invent arbitrary group names. An unlisted group raises
`ValueError` inside `build_task_contract()`, and an unregistered `--group`
CLI flag exits 2 at the boundary before any dispatch — invalid work never
reaches private CI. The registry below is byte-matched to the code's
`VALID_GROUPS` frozenset (9 names).

| Group | Domain (descriptive — code enforces membership only) |
|-------|--------------------------------------------------------|
| `browser` | browser automation surface, web-agent runtime, extensions |
| `core` | core engine business logic, state machines, models (default group) |
| `docs` | documentation, SPECs, work-order records |
| `federation` | cross-tenant federation orchestration and protocols |
| `gateway` | API gateway routing, ingress, rate limiting |
| `infra` | CI actions, deployment configs, cloud runtime configurations |
| `marketplace` | plugin registry, one-click BYO connect flow |
| `studio` | Studio frontend, console UX, user pages |
| `vscode` | VS Code extension surface |

**Resolution order (deterministic):**
1. Explicit `--group <name>` CLI flag — fail-closed: unregistered name exits 2.
2. `_detect_group()` sorted label scan — the first issue label that is a
   registry member wins (labels only; the minimal loop does no body scan).
3. Default: `DEFAULT_GROUP` = `core`.

`.github/ISSUE_TEMPLATE/agent-task.yml` carries the `task_group` dropdown that
must track this registry — keep the two in sync when the taxonomy changes.

**Relationship to `AGENTS.md` (Single Door SSOT):** the constitution is
`AGENTS.md` — the Single Door SSOT (the former `AGENT_RULES.md` was deleted by
#1526; citing it is a dangling reference). It defines the 5 Universal
Invariants and the Single Door execution surface — it defines no group
taxonomy. The execution registry below is the authoritative group surface for
dispatch; no constitutional section substitutes for a registry group. Changing
the taxonomy means changing the code's `VALID_GROUPS` first, then this table
and the issue-template dropdown in the same change.

## 4. CLI surface after #63

| Command | Status | Behaviour |
|---------|--------|-----------|
| `--task-envelope` | ✅ canonical | emits the unified envelope JSON, exit 0 |
| `--emit-prompt` | ⚠️ deprecated shim | stderr deprecation warning → emits the **same** envelope |
| `--emit-contract` | ⚠️ deprecated shim | stderr deprecation warning → emits the **same** envelope |
| `--group <name>` | ✅ new | canonical group override |
| `--verify-only` | ✅ extended | tiers 1–8 (syntax / JSON / YAML / binary guard / contract guard / group-registry guard / envelope-determinism / machine-path-isolation). **This row is the tier-count SSOT** — parity-enforced by `scripts/agents/check_loop_contract_parity.py` |

Deprecated shims keep running automation alive; removal is a future admin
decision after private-mirror parity (do not remove in a drive-by change).

## 4b. Canonical flag surface + `CONTRACT_VERSION` parity (#67)

The same file name (`scripts/agents/continuous_agent_loop.py`) exists in this
repo **and** in the private mirror `Supremeai-bd/supremeai`. They are deployed
by different workflows, so drift is invisible until something breaks. The
parity contract:

1. **`CONTRACT_VERSION` marker** — both copies define
   `CONTRACT_VERSION = "agent-loop-contract/1"` and MUST print
   `CONTRACT_VERSION=agent-loop-contract/1` as the **final stdout line** of
   `--verify-only` (exit code independent). Cross-repo check:

   ```bash
   python scripts/agents/continuous_agent_loop.py --verify-only 2>/dev/null | tail -1
   # → CONTRACT_VERSION=agent-loop-contract/1   (byte-identical on both repos)
   ```

   Changing flag behaviour or envelope semantics without bumping
   `CONTRACT_VERSION` on **both** copies is a spec violation.

2. **Canonical flag surface (union of both copies)** — any flag marked
   "shared" must behave identically on both copies:

   | Flag | Scope | Behaviour |
   |------|-------|-----------|
   | `--task-envelope` | shared (canonical) | unified envelope JSON on stdout, banner → stderr |
   | `--group <name>` | shared | group override, fail-closed against `VALID_GROUPS` |
   | `--auto-pr` | shared | accepted for pipeline parity (#89); honest stderr note; the minimal loop opens no PR itself |
   | `--verify-only` | shared | full verification tiers (count SSOT: §4) + parity marker line |
   | `--offline` | shared (mirror port pending) | honest offline mode: board query honestly skipped (dispatch path) and the `--verify-only` constitution-freshness boot smoke honestly skipped (report-only rules gate via `_offline_requested`); cadence roles still evaluated; env equivalents `SUPREMEAI_OFFLINE` / `AGENT_LOOP_OFFLINE` / `CI_OFFLINE` |
   | `--issue` / `--pick-next` / `--loop` / `--max-tasks` / `--role` / `--allow-adhoc` | shared | dispatch selection & role; `--loop` runs a single dispatch cycle per invocation (scheduler/orchestrator is the outer loop) |
   | `--emit-prompt` / `--emit-contract` | shared, deprecated | shim → same envelope (removal gated on parity) |
    | `--agent-name` / `--iterations` / `--model` / `--check-claimable` | private-mirror only | consumed by the private agent-loop workflow; public copy may reject or ignore them but the mirror MUST keep accepting them until that workflow migrates |

   `--offline` landed in the public copy first (§4b port rule); until the mirror port lands, the private copy may reject the flag — that is the port rule working as designed, not drift.

3. **Envelope parity** — the same issue on both copies must yield a
   `task_envelope` whose contract sections are byte-identical modulo
   `problem_statement.state` timestamps.

4. **Port rule** — changes to the shared core (envelope builder, `VALID_GROUPS`
   registry, guards) land in this repo first, then port to the private mirror
   **via a bridge work order** (never hand-edit the private copy).

## 4c. Runtime state surface — event-driven rotation + dispatch journal (#1591 → #3573)

The loop keeps two runtime state files under `scripts/agents/`. Both are
gitignored in this repo (#1624) — machine-local runtime state, never committed;
the private-mirror port is pending (port rule).

**#3573 regime change (founder mandate, LOOP_ALIGNMENT.md):** execution is
strictly Event & Condition-Driven — zero artificial timer locks. The old
regime held two fixed-guess clocks: `cadences_hours` (12h/24h role gates that
kept oversight roles waiting on an idle board) and a local 30-minute dispatch
lease (a time window that skipped dispatched-but-unclaimed actionable work —
the SPEC itself documented it as "a fixed guess, not lease renewal"). Both are
REMOVED. Claimability now has exactly two mechanical arbiters: the live claim
probe (`_feedback_claim_active`, #2794 fix (1)) at pick time and the atomic
`work_claim` at claim time. The tower's own #57 lease SSOT
(`claim_thresholds.py`, 30-min TTL + 5-min floor) is untouched — it RELEASES
stalled claims (frees work), the inverse of an artificial delay.

| File | Written by | Behaviour |
|---|---|---|
| `agent_rotation_state.json` | canonical rotation API (`due_roles` → `role_is_due` → `mark_role_run`, #1569 lineage; episode semantics #3573) | per-role episode markers (unix ts of this episode's run; NO duration comparison anywhere). The rotation re-arms (store reset) ONLY on the work event: a claimable issue was dispatched (both the dispatch path and the `--task-envelope` paths re-arm). Idle cycles dispatch one scheduled role each, in `scheduled_roles` config order; once every scheduled role has run this episode, the loop reports clean state and sleeps (founder mandate 2: 100% green → clean + safe sleep). There is NO reset-on-empty-board timer loop and NO hour gate. The old `agent_cadence_state.json` (timer regime) is simply orphaned. |
| `dispatched_issues_state.json` | `mark_issue_leased` at every issue assignment — the non-envelope dispatch path AND the `--task-envelope` paths (auto-pick + `--issue N`, #1596) | machine-local dispatch JOURNAL (`{ "<issue-number>": <last-dispatch-ts> }`), observability-only since #3573: the 30-minute time-window exclusion in `is_claimable` is REMOVED — a dispatched-but-unclaimed actionable issue is re-pickable immediately (founder mandate 1: no artificial waiting). Entries older than `DISPATCH_JOURNAL_RETENTION_SECONDS` (derived from the #57 SSOT, `claim_thresholds.ORPHAN_RELEASE_MINUTES`) are pruned on write; pruning is file hygiene, never behavior. |

Honest limitations, documented rather than hidden:

- **Machine-local visibility**: the rotation state and the dispatch journal
  are machine-local; agents on different machines never see each other's
  files. Cross-machine "who owns this row" truth lives entirely on the tower
  plane (live claim probe + atomic claim), which is the intended SSOT — the
  local files never gate behavior, so their blindness cannot cause a wrong
  skip, only a bounded re-probe.
- **Episode locality**: a machine's rotation re-arms when THAT machine assigns
  work. A machine that only ever sleeps while others work keeps its completed
  episode (clean + sleep) — fleet-level oversight continuity is carried by the
  machines that observe the work events. This is the founder's sleep-safely
  clause, not a starvation bug.
- **Upgrade migration**: machines upgrading from the timer regime re-arm at
  their first post-upgrade work event (the orphaned
  `agent_cadence_state.json` is never read).

**P0 Drainage gate (Universal Invariant 5, AGENTS.md):** the cadence path is
not free-running. After a successful board query and before the due-role loop,
`has_open_p0_blocker` scans the raw board items: any open item whose lowercased
labels include `p0`, `p0-*`, or `p0 ` holds every routine cadence role (warning
log + early return) — except items labeled `blocked-by-upstream`, which the gate
skips: such P0s sit in `pick_next_issue`'s `EXCLUDED_LABELS`, so no agent in this
lane can ever claim them, and counting them as blockers would starve cadence
forever (eternally-open, unclaimable P0). `status:claimed` P0s still block —
another runner is actively on them, the invariant's intended behavior. Held
roles never reach `mark_role_run`, so they do not
consume their cadence window — once the board drains, the due role dispatches
immediately. The gate is board-availability-gated (skipped when both the gh
query and the tower board fallback fail — fail-open to the pre-Rule-5 cadence
path) and sits below the
issue-solver path, which runs earlier in the cycle. `COMMON_RULES` injects the
invariant text into every dispatched mandate; the invariant's
idempotency/anti-stampede half is enforced by the §5 Anti-Duplicate PR Guard
and Claim Gate Guard. The stale-label freeze the gate is exposed to is not
hypothetical: `P0-critical` labels on already-resolved incidents (#1788/#1772)
held cadence while main CI was green (#1804/#1840) until admin hygiene closed
both issues (2026-10-28); label hygiene stays an admin action outside the agent
surface.

**Tower board fallback (R78/J484751, gh-absent runtimes).** The documented
external-agent runtime has no `gh` CLI, which used to leave the dispatch path
dead exactly where the loop actually runs: solver dispatch skipped, the P0
gate dark (fail-open), and the dispatch window capped at 100 rows while the
live board exceeded it. The dispatch board query now falls back to the Tower's
zero-credential `bridge.work_queue` (`_tower_board_rows()`: lazy sibling
`mcp_tower_client` import for URL resolution — env / workspace `mcp.json` /
documented default — then a stdlib-urllib streamable POST; large single-line
SSE payloads are extracted bytes-safe because `requests.iter_lines` splits
~134 KB lines at chunk boundaries). Fallback rows are mapped to gh shape
(`{"name": …}` label dicts), so solver dispatch, `has_open_p0_blocker`, and
priority sorting all operate on live data; the fallback runs only when gh
failed (never on `--offline`, never on gh-present runtimes) and every failure
mode degrades to the pre-existing honest skip line + gh-absent honesty floor.
The `--verify-only` boot smoke additionally displays the five Universal
Invariant Pillars and the fail-closed invariant checklist on stderr (rule-1
contract was half-implemented: `_print_rule_version_and_checklist` was a
silent stub and `mandatory_invariant_checklist` had no runtime consumer;
stdout contracts — tier evidence + exactly-once final marker — unchanged).

## 5. Open Guards — shift-left on free public runtime

The guard jobs in `.github/workflows/pipeline.yml` (branch-naming,
issue-reference, anti-duplicate PR, boundary-sanitization, loop-contract-parity,
ingress-hook, stale-base)
run on every PR to `supremeai-open` — free, unlimited public Actions minutes — so invalid
contributions fail at the public boundary instead of burning the private
repo's limited quota (Free org ≈ 2,000 min/month). The first three guards
are zero-checkout (~5s each); the boundary and parity guards check out the
tree for content inspection (stdlib-only, still minutes-bounded):

1. **Branch Naming Guard** — head branch must match
   `^(feat|fix|docs|chore|test|refactor|perf|bridge|group|contributor|hotfix|release|agent)/…`
   (bot branches `dependabot|github-actions|copilot/*` auto-allowed).
2. **Issue Reference Guard** — PR title/body must contain `#<number>`
   (admin escape hatch: `guard-exempt` label).
3. **Anti-Duplicate PR Guard** — whole-token `#N` comparison across other
   open PRs (titles, bodies, fork-branch names); a competing PR for the
   same issue fails the gate (one active claim per issue —
   `AGENTS.md` Single Door).
4. **Boundary Sanitization Guard (#107)** — guard self-test + PR
   changed-files scan + full-tree public/private boundary barrier.
5. **Loop-Contract Parity Guard (#118)** — asserts the loop's contract
   surface stays in sync: evidence tier count (code emission vs §4),
   this guard list vs the workflow job set, and no flag-table copies
   in CONTRIBUTING.
6. **Ingress Hook Guard (#161)** — asserts the §5.2 ingress hook
   surface (`docs/INGRESS_SECURITY_POLICY.md`): executable bit (git
   silently skips a non-executable hook), `bash -n` syntax gate, and
   the hook's own 5-scenario offline `--self-test`.
7. **Stale-Base Guard (#161)** — rejects PR branches built behind
   `main` (`rev-list` count base..head > 0 → rebase required;
   Board-Freshness #4177 at CI time, mirroring the local pre-push
   hook's freshness check).
8. **Claim Gate Guard (#392)** — verifies referenced issue carries an active claim
   (`status:claimed` or `status:in-progress` label, or `<!-- atomic-claim -->` comment)
   before PR creation (AGENTS.md Step 4: no claim, no work).
9. **Knowledge Sharing Guard (#392)** — verifies PR body carries filled Reflection Evidence
   (`why` + `alternatives_rejected`).
10. **Tower Verification Signature Guard (#hybrid-agent)** — verifies external agent PR carries
    valid Tower verification signatures (`## Reflection Evidence` and 3-Tier test evidence).

## 6. Submission flow (Pathway 1 wiring)

Agents consume the envelope, implement inside `scope.touching_files`, then
submit **without intermediate filesystem drafts**:

- **Pull request** (zero-credential): fork/branch → PR to `supremeai-open:main`
  using `submission.pr_body_template` + issue reference.
- **Bridge lane** (collaborator): push `bridge/<task-id>` branch to this repo →
  Bridge Work Order issue → private gate battery lands the change
  (or `bridge_submit_patch` MCP tool per AGENTS.md §8).

**Receipt-closure convention (#2508, prescription A).** Docs-only (spec-only)
submissions emit `Refs #N` — the spec-first keep-open contract holds the work
order open until code lands. When the docs-only patch IS the resolution of its
target (closure receipts, verification receipts that resolve their finding),
pass `closesOriginalIssue: true` in `bridge_submit_patch` so the landed PR
emits `Closes #N` and the work order closes on merge. Watch/census receipts
that do NOT resolve their subject keep the default — they are correctly open
until their subject resolves. The same note ships in `bridge_guide`
(`contract.receiptClosureConvention`), the onboarding surface every
zero-credential submitter reads.

## 7. Verification quick-start

```bash
git grep -n "VALID_GROUPS" scripts/agents/continuous_agent_loop.py
python scripts/agents/continuous_agent_loop.py --verify-only
python scripts/agents/continuous_agent_loop.py --issue 63 --task-envelope
python scripts/agents/continuous_agent_loop.py --task-envelope --allow-adhoc --group agent-orchestration   # → exit 2 (fail-closed demo — the SPEC's own former stale name)
```
