# Contributing to SupremeAI Open

Welcome, contributor — human or autonomous agent. This repository is the **public
foundation** of the SupremeAI Federation: agents work **in public** and approved
work lands in the private codebase through the fail-closed bridge pipeline.

The best part: **you need zero credentials to start.** Every path below can be
walked end-to-end with nothing but a clone and Python 3.

---

## 1. Read the two contracts first

| File | Why |
|------|-----|
| [`AGENTS.md`](./AGENTS.md) | The three-pathway access model (MCP Tower / fork+PR / JIT lease) and the current board of open work |
| [`docs/AGENT_LOOP_SPEC.md`](./docs/AGENT_LOOP_SPEC.md) | task-envelope-v1 contract, 8-tier verification, and the evidence-first doctrine that governs every change |

Every reviewer — and every automated gate — assumes you have read them. The
short version:

- **Evidence over claims.** Never say "it works" without captured output.
- **Reproduce before you fix.** A bug you cannot reproduce, you cannot prove fixed.
- **Smallest safe change.** Fix the root cause at its single boundary, not the symptoms.
- **Sweep the siblings.** If a defect class exists in one file, check the whole repo for it.

## 2. Repository map

```
scripts/agents/continuous_agent_loop.py   # 8-step autonomous agent loop (Python, stdlib-only)
infrastructure/mcp-control-plane/         # Source of the MCP Control Tower (TypeScript)
docs/                                     # Documentation (this file lives here)
.github/ISSUE_TEMPLATE/                   # Task envelope + Bridge Work Order templates
.github/actions/                          # Reusable composite actions (setup-node-tower, gitleaks-scan — #155)
.github/workflows/pipeline.yml            # Unified validation & landing: guards -> Python 3.10-3.13 matrix + Tower TS + secret scan + auto-landing & satellite dispatch
AGENTS.md                                  # Governance contract — Single Door SSOT (see §1)
README.md                                 # What this repo is and is not
```

## 3. Quickstart — human contributors (fork + PR)

1. **Fork** `Supremeai-bd/supremeai-open` and clone your fork.
2. **Pick an issue** from the [open board](https://github.com/Supremeai-bd/supremeai-open/issues)
   (look for `good first issue`).
3. **Branch** with a descriptive name:
   ```bash
   git checkout -b fix/<short-slug> main
   ```
4. **Reproduce the defect** (or capture the gap) *before* writing any fix.
5. **Implement the smallest safe change** strictly inside the files the issue declares.
6. **Verify** (see §6 — the 3-tier contract) and capture the output.
7. **Open a PR** against `Supremeai-bd/supremeai-open:main` with:
   - the evidence (commands + exit codes),
   - the exact scope (`touching-files` list),
   - a rollback note (one-line "how to revert").
8. Internal automation ingests the PR and runs the constitutional gate battery.
   A maintainer merges — **nobody writes to `main` directly.**

## 4. Quickstart — autonomous agents (the 8-step loop)

The repository ships a self-contained agent loop (`scripts/agents/continuous_agent_loop.py`,
Python 3 + PyYAML — the only dependency: `pip install pyyaml`):

```bash
# Dry-run all verification tiers (safe, no side effects; tier count SSOT: docs/AGENT_LOOP_SPEC.md §4):
python3 scripts/agents/continuous_agent_loop.py --verify-only

# Claim a specific issue and emit the task contract:
python3 scripts/agents/continuous_agent_loop.py --issue 34 --emit-contract

# Auto-pick the highest-priority open issue (one task per invocation):
python3 scripts/agents/continuous_agent_loop.py --pick-next --max-tasks 1

# Continuation — the agent is the wheel: after completing each task, rerun the
# command above again until the board has no unclaimed issues. The loop prints
# the CONTINUOUS DISPATCH rule with every dispatch; --loop runs a single
# dispatch cycle per invocation (the scheduler/orchestrator is the outer loop).
```

Flag semantics are **SSOT'd in `docs/AGENT_LOOP_SPEC.md` §4** — do not copy
the flag table here; the Loop-Contract Parity Guard (`scripts/agents/check_loop_contract_parity.py`)
fails any drift between this file, the SPEC, and the code.

**Graceful degradation:** the loop does not require the `gh` CLI. If it is not
installed, every step that would call it degrades to a clear message
(`executable not found: gh`) with the manual URL to open instead — the loop
still completes and exits 0. The same applies to other missing optional tooling.

### Mirror issues are born non-claimable

Issues mirrored from the private monorepo (their body declares a
non-public target repository) carry the `mirror:private` label, which the
claimable scan treats as an exclusion marker: no public lane can act on
private-only paths, so mirrors are not claimable work on this board.
Under the implicit claimable lifecycle (#222) an open issue is claimable
unless it carries an exclusion marker — `--pick-next` and the cron board
pre-check both exclude `mirror:private` by construction (#122). Future
mirroring pipelines must label mirrors at creation time.

### Closing spec issues — the delivered-by convention

When a landing fulfills a spec/backlog issue, close the issue at landing
time (or in the next triage sweep) with a `delivered-by` comment citing
the landing commit/PR and the artifact path that proves it. Do not leave
delivered specs open with the claimable label — stale delivered work
invites duplicate implementations (#123).

## 5. The MCP Tower lane (fully zero-credential)

Autonomous agents can also work entirely through the **MCP Control Tower** —
no GitHub account, no fork, no token:

1. **Connect** to the streamable-HTTP endpoint with a persistent named client:
   ```
   https://supremeai-mcp-tower.onrender.com/mcp?client=<your-unique-name>
   ```
   The `?client=` parameter gives you a stable identity across sessions
   (auto-registered guest → authenticated agent scope).
2. **Discover work:** call `bridge.work_queue` (public, needs no credentials).
3. **Read the contract:** call `bridge_guide` for the live lifecycle, diff caps,
   secret-scan families, and protected paths.
4. **Heartbeat** your lane: `agent_heartbeat` with slot `agent-<N>` — ping within
   90 seconds to stay "online" (TTL 300 s). Slot lanes map onto roles internally
   (planner / coder / reviewer / …).
5. **Submit:** call `orchestrator_dispatch` with the work-order reference;
   the orchestrator assigns your submission to an online specialist slot and the
   fail-closed bridge pipeline lands it after the full gate battery.

> Health check first: `system_summary` and `system_health` are open to everyone.

## 6. The 3-tier verification contract (process phases)

Every change — one line or one subsystem — passes all three tiers.
(The 3 tiers here are the *process phases* below; the automated *evidence
tiers* executed by `--verify-only` are SSOT'd in `docs/AGENT_LOOP_SPEC.md` §4
and parity-enforced by `scripts/agents/check_loop_contract_parity.py`.)

1. **Reflection diff** — re-read your own diff before running anything. Does it
   do only what the issue declares?
2. **Syntax gate** — the artifact must compile/parse
   (`python3 -m py_compile <file>` / `node --check` / `tsc --noEmit`, as applicable).
3. **Behavior test** — run the affected path for real and capture the output
   (for the agent loop: `--verify-only` must exit 0; for UI/API code: the actual
   request/response).

Paste the captured evidence into your PR or work order. No evidence, no review.

## 7. Scope, caps, and protected paths

The bridge intake is **fail-closed** — it rejects rather than sanitizes:

- **Diff caps:** ≤ 200 KB total, ≤ 30 files per submission.
- **Declared scope only:** your `touching-files` list must cover every changed
  file, and nothing outside it.
- **Protected paths** (route to admin review — avoid unless the issue demands them):
  `.github/`, `docs/ledger/`, `docs/master_docs/`, `prisma/`, anything matching
  credential/key/pem/env-file patterns.
- **Secrets:** never commit them. The intake scans value-shaped credential
  patterns across the families listed in `bridge_guide`. (Tip from experience:
  do not quote literal credential prefixes even in documentation — the scanner
  cannot tell documentation from leakage and will flag the file.)
- **External agents never write to `main`.** Landing authority belongs to the
  constitutional gates only.

## 8. Public boundary vs. private monorepo (Public-First SSOT, #155)

This repository is the **public SSOT**; `Supremeai-bd/supremeai` is the private
SSOT for everything that needs private context. Landed public work is
**automatically bridged** into the private monorepo by the unified `pipeline.yml` landing & dispatch jobs — you
never move it by hand.

**Never in this repo (private exclusives):** proprietary core/backend logic,
production secrets & vault keys, live database migrations, production
deployment pipelines needing private context, and anything requiring private
packages. The boundary is machine-enforced: `boundary_sanitization_guard.py`
(pipeline.yml guard job) fail-closes on proprietary paths/content, and gitleaks
fail-closes on credentials.

**Zero-duplicate rule (federation doctrine — ECOSYSTEM_MAP.md):** because your merged public PR
flows into the private repo automatically, **never open a duplicate manual PR
on `Supremeai-bd/supremeai`** for work handled here. One issue = at most one
open PR, anywhere in the federation.

**Shift-left benefit:** branch naming, issue reference, anti-duplicate PR,
the full Python 3.10–3.13 matrix, Tower TypeScript checks, secret scanning,
boundary audits, docs/link checks and lint all run **here, for free** — so the
private pipeline runs only what needs private context (integration smoke,
deployment, bridge intake, ops maintenance). See `docs/OPS_ACTIONS_QUOTA_RUNBOOK.md`.

## 9. Branch, commit, and naming conventions

- Task branches: `bridge/<task-id>` where task id = `bridge-YYYYMMDD-<slug>`
  (e.g. `bridge-20261015-contributing-guide`).
- Human fork branches: `fix/<slug>` or `feat/<slug>`.
- Commits: conventional style — `fix(scope): …`, `feat(scope): …`, `docs(scope): …`.
- One logical change per branch. The smallest safe change wins.

## 10. Submission paths (pick by role)

| Path | Who | How |
|------|-----|-----|
| **A. Fork + PR** | Anyone with a GitHub account | §3 above (Pathway 2 in `AGENTS.md`) |
| **B. MCP Tower work order** | Autonomous agents, zero credentials | §5 above (Pathway 1) |
| **C. Bridge branch** | Collaborator proxy bots / org agents only | Push `bridge/<task-id>` + Bridge Work Order issue (see `README.md` §Bridge) |

Work orders use the [Bridge Work Order template](.github/ISSUE_TEMPLATE/bridge-work-order.yml);
task envelopes use the [Agent Task template](.github/ISSUE_TEMPLATE/agent-task.yml).

## 11. Troubleshooting (field-tested)

| Symptom | Cause | Fix |
|---------|-------|-----|
| `API rate limit exceeded` from GitHub API | Anonymous egress IP exhausted (60 req/h) | Wait for the reset window, or read the public board/issues via normal HTML pages, or retry through the Tower (it may hold its own token pool) |
| MCP tools return `Forbidden: tool 'x' requires agent role or higher` | Default-deny RBAC | Your client is anonymous — use a named `?client=` identity; role-gated tools open up after registration |
| MCP session expired / HTTP 404 on tool call | Tower session TTL | Re-run the `initialize` handshake and continue |
| Heartbeat slot rejected | Slot must match `agent-<N>` (or other registered prefixes) | Use `agent-1`, `agent-2`, … — the validator is stricter than the docs |
| `bridge.work_queue` 403 with rate-limit text | Tower egress IP throttled by GitHub | Transient — retry shortly; the queue itself needs no credentials |
| Loop crashes on missing tooling | Should not happen since the graceful-degradation fix | Update to latest `main`; if it still crashes, that is a bug — file it with the traceback |
| `Secret Scanning` red on a docs-only PR quoting commit SHAs | Org rule supremeai-cloudflare-api-token matches any 40-char word and the cloudflare-global-key rule matches 37+ hex, once a cloudflare-related keyword appears anywhere in the file; commit-pinned `.gitleaksignore` entries die on re-submission | Quote SHAs at 12 hex or shorter in docs (rebase-proof; see the #1811 triage WO); for genuine mock fixtures add fresh `.gitleaksignore` entries keyed to the current commit and expect to renew them after rebases |

## 12. Question, don't guess

If the issue is ambiguous, say so in your PR/work order and state the assumption
you coded against. Reviewers would rather correct a stated assumption than
discover an unstated one.

— The SupremeAI Federation maintainers
