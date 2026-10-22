# SupremeAI Federation Charter — Single Public Task Board & Zero-Issue Satellite Mandate

**Work Order:** Supremeai-bd/supremeai-open#626 (P1-high, governance)
**Agent:** zai-autonomous-contributor (Z.ai Code, zero-credential bridge lane)
**Constitution anchors:** AGENTS.md §5 + AGENT_RULES.md §5 (machine-enforcement pointers) — the condensed constitution (Law of Minimal Elegance) delegates the full doctrine to this charter
**Enforced by:** `scripts/ci/satellite_board_guard.py` (Milestone 3 building block) · central nightly job per #612 (operator wiring)

---

## 1. Purpose

Fourteen repositories ship one product. This charter makes the task-routing
topology mechanical instead of tribal: every piece of work enters the
federation through exactly one public door, satellites stay permanently
clean of tracker state, and the whole federation's board health is
answerable with one command.

It formalizes and enforces the **Universal Single Task Board SSOT &
Zero-Issue Satellite Doctrine** proposed in #626. The constitution's
condensed form (Law of Minimal Elegance — 88-line AGENTS.md standard)
delegates the full doctrine text to this governed charter; the
constitution files carry only the minimal machine-enforcement anchors.

## 2. The Canonical Rules

### Rule 1 — One Public Board (একক সেন্ট্রাল ডাকবাক্স)

`Supremeai-bd/supremeai-open` is the **sole public task board and front
desk** of the federation. All tasks, bridge work orders, CI failure alerts,
feature proposals, and community contributions across all 14 repositories
are submitted and tracked exclusively here. There is no second door.

### Rule 2 — Zero-Issue / Zero-PR Satellite Mandate (৮টি স্যাটেলাইটে ০/০)

The 8 active satellite repositories:

| # | Satellite | Role |
|---|-----------|------|
| 1 | `studio` | Web UI dashboard (Vercel) |
| 2 | `api` | Unified provider gateway & commands (Render) |
| 3 | `vscode` | IDE extension & native client hub |
| 4 | `browser` | Stealth automation sandbox (Render) |
| 5 | `core` | Decision intelligence & primary node (Render) |
| 6 | `agents` | Autonomous agent lifecycle & worker (Render) |
| 7 | `archive` | Append-only memory & ADRs |
| 8 | `mcp-control-plane` | MCP tower on Render |

must maintain **zero open issues and zero open PRs — permanently**. Direct
manual issue creation or PR opening on a satellite is deprecated; all
incoming work enters through `supremeai-open` and is ingested autonomously
via `landing.yml` or the bridge transit pipeline. A satellite tracker state
other than 0/0 is a **VIOLATION**, not a style preference.

### Rule 3 — Private Monorepo Boundary

The private monorepo (`Supremeai-bd/supremeai`) retains only internal
proprietary backlogs and decision registers. All public or cross-federation
work routes through `supremeai-open`. The private monorepo is out of this
charter's audit scope by design (private plane, §2.3.1 of AGENTS.md).

### Rule 4 — The 14 Persistent Anchor Hubs & Sub-Issue Architecture (১৪টি রুট হাব)

The sole public task board maintains strictly **14 persistent parent Anchor Hubs**:
- `[Federation Hub] 🚨 CI Pipeline Failures & Incident Desk (#761)`: all cross-repo CI breakages, workflow failures, and test crashes attach here.
- `[Federation Hub] 🌉 Bridge Transit, Orders & Rejections Desk (#760)`: all transit orders, patch distributions, and bridge rejections attach here.
- 12 Domain Repository Anchor Hubs (#749–#759, #762): all repository-specific features, bugs, and tasks attach here.

All incoming work items, failure alerts, and bridge work orders are ingested strictly as **Sub-Issues** within their assigned Anchor Hub. Loose root issues on `supremeai-open` are strictly prohibited.

## 3. Enforcement

### 3.1 The Guard (automated, this charter's teeth)

`scripts/ci/satellite_board_guard.py` audits all 12 satellites against the
0/0 mandate using the same zero-credential plane external bridge agents
operate on:

| Verdict | Meaning | Gate effect |
|---------|---------|-------------|
| `CLEAN` | 0 open issues, 0 open PRs | pass |
| `VIOLATION` | ≥1 open issue or PR (details listed) | **fail** |
| `UNREACHABLE` | private plane, absent repo, network fault, rate limit | skip with loud warning — never silent |

Exit codes (fail-loud, CI-friendly, mirrors `docs/federation_parity_check.py`):
`0` every reachable satellite CLEAN · `1` any VIOLATION · `2` all
UNREACHABLE (nothing verified) · `3` usage error.

Offline proof: `python3 scripts/ci/satellite_board_guard.py --self-test`
(5/5 checks, zero network).

### 3.2 Wiring (operator lane)

The central nightly job architecture is specified by #612. The operator
wires the guard into that job in `--check` mode (CI workflow files are a
protected path for automatic agent writes per the boundary guard). The
script is deterministic and side-effect free — safe for scheduled runs and
for local operator execution with identical semantics.

### 3.3 Remediation path (what happens on VIOLATION)

1. The violation is mirrored to the central board as a task issue (the
   federation CI watchdog pattern, #595).
2. A maintainer closes the stray satellite issue/PR with a link back to the
   central SSOT thread (admin lane — satellites accept admin writes only).
3. The next guard run returns `CLEAN` for that satellite.

Historical remediations (Milestone 1 of #626, admin lane): stray epics on
`supremeai-agents#1` (handled in bridge order #409), `supremeai-skills#1`
(seed implemented via #614 / #573), `supremeai-infrastructure#4` (subsumed
by federation integration issues #606–#608).

## 4. Why This Matters (the failure class this prevents)

Work tracked off-SSOT is work the autonomous agent loop cannot see: it
orphaned bridge orders (#504/#507/#509/#511/#546 class), produced
duplicated in-flight claims, and left CI failures unowned until they
escalated to P0. A 0/0 satellite plane makes the central board's queue the
complete truth — the Lazy Team Leader dispatcher (`scripts/agents/
continuous_agent_loop.py --pick-next`) can then route every task with full
information, and no contributor ever wonders where the "real" tracker is.

## 5. Amendment Policy

This charter is a governed document:

- The satellite registry in §2 Rule 2, `SATELLITES` in the guard script,
  and the constitution anchors (AGENTS.md §5, AGENT_RULES.md §5) MUST move
  together in the same change (constitution and its enforcement move as one
  commit — the #567 freshness principle applied to federation topology).
- Changes land via governance PRs on `supremeai-open` with Reflection
  Evidence, never by direct edit.
- The audit matrix in the nightly job output is the runtime evidence that
  this charter is being honored; a red matrix with no mirrored central
  issue is itself a doctrine violation.
