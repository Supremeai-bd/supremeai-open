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
    "group":     "agent-orchestration",// VALID_GROUPS registry — fail-closed
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
    "memory_integration": {                       // G1 (#283): STATIC capability descriptor — constants only
      "protocol": "mcp-memory-sidecar-v1",
      "transport": "MCP streamable HTTP (initialize → tools/list → tools/call)",
      "tools": ["memory.get_similar_tasks", "memory.record_task"],
      "env_enable": "SUPREMEAI_MEMORY (value 0 disables)",
      "env_endpoint": "MCP_TOWER_URL",
      "degradation": "fail-honest: bounded timeout, circuit breaker, never blocks the cycle",
      "spec": "docs/AGENT_LOOP_SPEC.md §2b"
    },
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

## 2b. Memory sidecar integration (G1, audit #283) — the loop that learns

The Tower bridges the Python memory server under the `memory.*` prefix
(episodic `record_task` / `get_similar_tasks`, long-term `remember_fact`).
The loop consumes it in two places while staying stateless itself
(AGENTS.md §2):

| When | Tool | Effect |
|------|------|--------|
| after `build_agent_prompt()` | `memory.get_similar_tasks` | top-k similar past executions are appended to the specialist prompt as a bounded "Past task experience" section |
| after step 7 (and on verify-fail) | `memory.record_task` | outcome signature (`success`/`failure` + one-line summary) is recorded — the failure signal is what stops the federation repeating mistakes |

**Protocol:** MCP streamable HTTP against `MCP_TOWER_URL` (default public
Tower) — `initialize` → `notifications/initialized` → `tools/list` (live
schema discovery; argument payloads are adapted to the advertised
`inputSchema` via a best-effort value map) → `tools/call`. Both dotted
(`memory.get_similar_tasks`) and sanitized (`memory_get_similar_tasks`) call
names are tried (Tower registry quirk, WO #251 evidence).

**Degradation contract (fail-honest):** 8s bounded timeout; process-lifetime
circuit breaker trips after 2 consecutive transport/contract failures;
visibility-scoped environments (zero-credential guests see no `memory.*`
tools) degrade quietly; the cycle NEVER blocks on memory.
`SUPREMEAI_MEMORY=0` disables the integration entirely.

**Envelope parity (§4b rule 3):** the envelope carries only the STATIC
`memory_integration` capability descriptor (constants, byte-identical across
builds and copies). Live experience data never enters the envelope — it
flows to the executing specialist at dispatch time only. `--verify-only`
tier count and the `CONTRACT_VERSION` parity marker are unchanged.

## 3. Group taxonomy — `VALID_GROUPS` (fail-closed)

Agents **cannot** invent arbitrary group names. Any task contract with an
unlisted group raises `ValueError` inside `build_task_contract()` **and**
`resolve_group()` — invalid work never reaches private CI.

| Group | Domain |
|-------|--------|
| `agent-orchestration` | continuous loop, agent dispatch, specialist roles, task envelopes, agent lifecycle |
| `mcp-tower` | MCP Control Plane tools, health probes, bridge adapters, remote endpoints, server infra |
| `core-engine` | core federation business logic, state machines, models |
| `schemas-contracts` | OpenAPI schemas, contract definitions, protocol envelopes |
| `infra-ops` | deployment configs, CI actions, cloud runtime configurations |

**Resolution order (deterministic):**
1. `--group <name>` CLI flag (must be in registry, else exit 2)
2. Issue body/label scan (first registry match, sorted order)
3. Default: `agent-orchestration`

`.github/ISSUE_TEMPLATE/agent-task.yml` carries a **dropdown aligned to this
registry** — keep the two in sync when the taxonomy changes.

**Relationship to `AGENT_RULES.md` §5 (#90):** §5's eight Primary Groups
(GOVERNANCE, SECURITY, PIPELINE, ARCHITECTURE, RELIABILITY, PRODUCT,
INTELLIGENCE, INFRASTRUCTURE) are *policy domains* of the constitutional
taxonomy — a different surface from this *execution registry*. They are
reconciled by a default-routing map in `AGENT_RULES.md` §5 ("Registry
relationship"); on the public board the registry group below is authoritative
for dispatch, and a §5 domain never substitutes for a registry group. Changing
either list is an ADMIN_DECISION.

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
   | `--verify-only` | shared | full verification tiers (count SSOT: §4) + parity marker line |
   | `--issue` / `--pick-next` / `--loop` / `--max-tasks` / `--role` / `--allow-adhoc` | shared | dispatch selection & role |
   | `--emit-prompt` / `--emit-contract` | shared, deprecated | shim → same envelope (removal gated on parity) |
    | `--agent-name` / `--iterations` / `--model` / `--check-claimable` | private-mirror only | consumed by the private agent-loop workflow; public copy may reject or ignore them but the mirror MUST keep accepting them until that workflow migrates |

3. **Envelope parity** — the same issue on both copies must yield a
   `task_envelope` whose contract sections are byte-identical modulo
   `problem_statement.state` timestamps.

4. **Port rule** — changes to the shared core (envelope builder, `VALID_GROUPS`
   registry, guards) land in this repo first, then port to the private mirror
   **via a bridge work order** (never hand-edit the private copy).

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
   same issue fails the gate (AGENT_RULES U4).
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

## 6. Submission flow (Pathway 1 wiring)

Agents consume the envelope, implement inside `scope.touching_files`, then
submit **without intermediate filesystem drafts**:

- **Pull request** (zero-credential): fork/branch → PR to `supremeai-open:main`
  using `submission.pr_body_template` + issue reference.
- **Bridge lane** (collaborator): push `bridge/<task-id>` branch to this repo →
  Bridge Work Order issue → private gate battery lands the change
  (or `bridge_submit_patch` MCP tool per AGENTS.md §8).

## 7. Verification quick-start

```bash
git grep -n "VALID_GROUPS" scripts/agents/continuous_agent_loop.py
python scripts/agents/continuous_agent_loop.py --verify-only
python scripts/agents/continuous_agent_loop.py --issue 63 --task-envelope
python scripts/agents/continuous_agent_loop.py --task-envelope --allow-adhoc --group not-a-group   # → exit 2 (fail-closed demo)
```
