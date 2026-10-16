# Zero-Issue Satellite Doctrine (একক উন্মুক্ত হাব নীতি)

> Codification of `Supremeai-bd/supremeai-open#425` (P1-high, `repo:open`).
> Machine-enforced by `tests/test_zero_issue_doctrine.py` — run
> `python3 -m pytest tests/test_zero_issue_doctrine.py -q` from the repo root.

## 1. Executive Mandate

In accordance with the Zero-Admin Policy (admin manual effort budget ≤ 0.01%)
and the Federation Single Pane of Glass vision:

> **`Supremeai-bd/supremeai-open` is the SOLE canonical issue and task tracking hub for the entire SupremeAI federation.**
>
> **All 12 satellite repositories plus the private monorepo must maintain a ZERO-ISSUE (or absolute minimum single-blueprint) footprint.**

Scattering issues across multiple repositories fragments context, blinds
external AI agents and community contributors, and creates administrative
overhead requiring manual cross-checking of 13+ GitHub issue boards.

## 2. Canonical `repo:` Label Map (SSOT)

Every issue on the hub carries exactly one canonical target label:

| Label | Target repository |
|---|---|
| `repo:monorepo` | `Supremeai-bd/supremeai` |
| `repo:studio` | `Supremeai-bd/supremeai-studio` |
| `repo:core` | `Supremeai-bd/supremeai-core` |
| `repo:api` | `Supremeai-bd/supremeai-api` |
| `repo:mcp` | `Supremeai-bd/supremeai-mcp-control-plane` |
| `repo:agents` | `Supremeai-bd/supremeai-agents` |
| `repo:skills` | `Supremeai-bd/supremeai-skills` |
| `repo:command` | `Supremeai-bd/supremeai-command` |
| `repo:browser` | `Supremeai-bd/supremeai-browser` |
| `repo:vscode` | `Supremeai-bd/supremeai-vscode` |
| `repo:infra` | `Supremeai-bd/supremeai-infrastructure` |
| `repo:sdk` | `Supremeai-bd/supremeai-sdk` |
| `repo:open` | `Supremeai-bd/supremeai-open` (this hub itself) |

Note: `repo:archive` exists in `landing.yml` routing for historical patch
streams and is NOT a task-targeting label; new work never targets the
archive.

## 3. Architectural Invariants

1. **100% Federation Issues on the Hub** — every bug report, feature
   proposal, refactoring task, performance optimization, and bridge work
   order targeting ANY federation component is authored, ranked, claimed,
   and tracked strictly on `Supremeai-bd/supremeai-open`, tagged with its
   canonical `repo:` label from §2.
2. **Zero-Issue Satellite Invariant** — satellite repositories must not
   host separate discussion threads, user issues, or task backlogs.
   **Allowed exception (maximum 1 per satellite):** issue `#1` as the
   permanent Architectural Blueprint / SSOT epic for that repository.
   All other satellite issues must be closed or migrated to the hub.
3. **Intake Zero-Residue Guarantee** — when bridge work orders land on the
   private monorepo, internal workflows must not create lingering tracking
   issues that require manual admin closing. Any PR landed via
   `landing.yml` marks the upstream work order on the hub as `bridge:landed`
   and closes it without leaving orphan issues in the monorepo.
4. **Cross-Repo CI Failure Telemetry** — if a CI pipeline fails on `main`
   in any satellite or the monorepo, it must report/dispatch a unified
   alert to the hub (tagged `bridge:ci-failure` + `repo:<name>`) rather
   than leaving an isolated, unmonitored issue on the satellite. The
   dispatcher already ranks `bridge:ci-failure` at claim tier -1 (before
   P0) — contract locked by `tests/test_ci_failure_priority.py`.

## 4. Phase Plan & Status

- [x] **Phase 3 — Constitution & Federation Map Codification**: THIS
  document is the permanent machine-enforced governance rule; enforcement
  battery ships in the same payload (`tests/test_zero_issue_doctrine.py`).
- [x] **Phase 4 — Agent Dispatcher Priority Enforcement (verification,
  no code change needed)**: `scripts/agents/continuous_agent_loop.py`
  defines `UPSTREAM_REPO = "Supremeai-bd/supremeai-open"` as the sole
  issue source and passes `--repo UPSTREAM_REPO` to every `gh issue` /
  `gh pr` invocation (whole-board listing, claim labeling, PR dedup).
  The enforcement battery asserts this mechanically (T3/T5 below).
- [ ] **Phase 1 — Satellite Issue Template Lockdown (operator-side)**:
  deploy `.github/ISSUE_TEMPLATE/config.yml` in all 12 satellites with
  `blank_issues_enabled: false` and a contact link pointing at the hub's
  issue chooser. Canonical content (verbatim, for each satellite):

  ```yaml
  blank_issues_enabled: false
  contact_links:
    - name: "SupremeAI Federation Central Issue Hub"
      url: "https://github.com/Supremeai-bd/supremeai-open/issues/new/choose"
      about: "All bug reports, feature requests, and agent tasks for this repository are centralized on supremeai-open."
  ```

  Operator-side because `.github/` in satellites is outside the public
  bridge boundary (bridge-protected path; satellites receive streams, not
  agent commits).
- [ ] **Phase 2 — Monorepo Issue Drainage (operator-side)**: review
  remaining non-architectural issues in the private monorepo, migrate
  active tasks (CORS fixes, gateway endpoints) into actionable hub issues
  labeled `repo:monorepo`, close satellite duplicates. Requires private
  issue-board access.

## 5. Enforcement Battery (`tests/test_zero_issue_doctrine.py`)

Offline, stdlib-only, fail-closed with honest skips (a check that cannot
run in a given tree skips with an explicit reason instead of failing):

| ID | Assertion |
|---|---|
| T1 | The doctrine document exists and contains the full §2 label map and all §3 invariant clauses |
| T2 | `landing.yml` dispatch table streams to all 12 satellite repositories |
| T3 | The agent loop declares `UPSTREAM_REPO = "Supremeai-bd/supremeai-open"` (hub SSOT) |
| T4 | `AGENTS.md` codifies the Ephemeral Transit predecessor doctrine (§2.3.6) |
| T5 | The agent loop never queries any non-hub repository for issues |

## 6. Acceptance Criteria Mapping (issue #425)

1. Satellites at 0 open issues (or exactly 1 static blueprint issue) —
   operator enforcement via Phase 1 lockdown + Phase 2 drainage; doctrine
   codified here.
2. All operational tasks across all 12+2 repositories searchable,
   filterable, and actionable from
   `https://github.com/Supremeai-bd/supremeai-open/issues` — guaranteed by
   invariant §3.1 + the canonical label map (§2), with CI telemetry (§3.4)
   keeping the hub authoritative during incidents.
3. Zero manual admin effort to monitor distributed issue lists — delivered
   by the intake zero-residue guarantee (§3.3) + the landing pipeline that
   auto-closes work orders (already operational: work orders #344, #350,
   #367, #368, #381, #410, #414 closed autonomously at landing).
