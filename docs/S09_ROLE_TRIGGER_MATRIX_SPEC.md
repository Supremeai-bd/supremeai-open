# S09 — Deterministic Role Trigger Matrix (Continuous Agent Loop Triad)

Implements **#489** — `feat(agents): [role-dispatch] Deterministic Role Trigger Matrix`.

## 1. Problem

Specialized agent roles are currently selected by fragile **keyword matching**
against free text — `classify_task_role()` in
`scripts/agents/continuous_agent_loop.py` lower-cases the issue title, labels
and body and scans for substrings such as the literal word `"audit"`. This is
the exact anti-pattern #489 deprecates: false positives, missed audits,
ambiguous role contracts.

## 2. Deliverables

| File | Kind | Purpose |
|---|---|---|
| `scripts/agents/role_trigger_matrix.py` | new (SSOT) | Two-Paradigm Deterministic Dispatch Engine: 8 role contracts carrying the full Triad, bijective event router, exact label-plane lookup, least-privilege RBAC provisioning, role-specific output validators, `--self-test`. |
| `tests/test_s09_role_trigger_matrix.py` | new | 39 offline contract tests (dual-mode unittest + pytest). Imports the SSOT constants — zero duplication. |
| This document | new | Spec + **content-anchored integration hunks** for the pre-existing `scripts/agents/continuous_agent_loop.py` (Appendix A — the loop file is pre-existing; per repo doctrine it is retrofitted by content-anchored hunks, not rewritten). |

## 3. The Triad (দায়িত্ব · নীতি · অস্ত্র)

Every role contract (`RoleContract`) carries:

1. **দায়িত্ব অর্পণ — Responsibility Assignment**: `responsibility`
2. **নীতি ও সীমারেখা — Rule Constraints**: `must_follow` (মানতে হবে) vs
   `must_not` (মানবে না / নিষেধ)
3. **অস্ত্র বরাদ্দ — Weapon Provisioning**: `weapons` (exact tool allowlist),
   `forbidden_operations`, `commit_scopes`, `issue_labels`

## 4. Two-Paradigm Deterministic Dispatch

| Paradigm | Roles | Trigger plane |
|---|---|---|
| TASK-DRIVEN (Event, Queue & Runway) | `coder`, `ci-fixer`, `task-auditor` | exact event type + label/payload gates |
| TIME-DRIVEN / PLATFORM (Cron & Periodic Probe) | `ecosystem-scout`, `federation-auditor`, `human-eye`, `rules-breaker`, `platform-guardian` | exact event type + `schedule_kind` gate (`cron` / `fixed_rate`) + schedule expression present |

### 4a. Event router (bijective — exactly one role per canonical event)

| Event type | Role | Deterministic gates (fail-closed) |
|---|---|---|
| `event:task.claimed` | coder | labels ⊇ `status:claimed` (No Claim No Branch) |
| `event:pr.ci_failed` | ci-fixer | payload `pr_number` truthy ∧ `checks_state == "failing"` |
| `event:pr.pre_landing` | task-auditor | payload `landing_gate == "armed"` |
| `event:schedule.ecosystem_scan` | ecosystem-scout | `schedule_kind == "cron"` ∧ `schedule_expr` present |
| `event:schedule.federation_audit` | federation-auditor | `schedule_kind == "cron"` ∧ `schedule_expr` present |
| `event:schedule.visual_review` | human-eye | `schedule_kind == "fixed_rate"` ∧ `schedule_expr` present |
| `event:schedule.adversarial_probe` | rules-breaker | `schedule_kind == "fixed_rate"` ∧ `schedule_expr` present |
| `event:provider.health_alert` | platform-guardian | payload `alert_state == "unhealthy"` |

Unknown event → `DENY(UNKNOWN_EVENT)`. Missing label → `DENY(LABEL_GATE)`
with the missing labels enumerated. Wrong payload value →
`DENY(PAYLOAD_MISMATCH)`. **No gate ever falls open.**

### 4b. Label-plane lookup (`dispatch_from_labels`)

Exact-match equality on the structured label plane (the same plane the claim
guard trusts: *"claim = label plane OR atomic-claim comment"*), with fixed
priority:

1. `status:runway` → **ci-fixer** (runway-first)
2. `gate:pre-landing` → **task-auditor**
3. `status:claimed` → **coder**

Anything else → `DENY(NO_TRIGGER)`. A label that merely *contains* a trigger
string (e.g. `xstatus:claimedx`) does not match.

## 5. Keyword Matching — Deprecated

`KEYWORD_MATCHING_DEPRECATED = True` is the machine-readable tombstone.
The matrix module has **no** free-text classification API
(`classify_task_role` / `classify_from_text` / `match_keywords` do not exist
there). `DispatchSignal` is structural by construction — its only fields are
`event_type` (exact enum), `labels` (exact frozenset) and `payload`
(exact-equality key/value facts). Tests enforce all three properties.

## 6. Least-Privilege RBAC (লাঠি বনাম ছুরি)

| Role | Weapon Type | Weapons (exact allowlist) | Forbidden |
|---|---|---|---|
| coder | Surgical Knife 🔪 | `replace_file_content`, `multi_replace_file_content`, `write_to_file`, `test_runner`, `git_branch_create`, `pr_create` | claim without atomic lock, breaking scope |
| ci-fixer | Emergency Defibrillator ⚡ | `replace_file_content`, `multi_replace_file_content`, `write_to_file`, `ci_log_inspector`, `test_preflight`, `pr_branch_commit` | new backlog issues, bypassing checks |
| task-auditor | Policy Stamp 📋 | `boundary_sanitization_guard_runner`, `gitleaks_scanner`, `pr_review_approve_block` | modifying source code |
| ecosystem-scout | Long-Range Telescope 🔭 | `search_web`, `read_url_content`, `gh_issue_create` | local code modifications, uncritical hype |
| federation-auditor | Ledger Microscope 🔬 | `multi_repo_git_inspector`, `gh_issue_create` | direct code edits |
| human-eye | Stylist Camera & Mirror 📸 | `browser_subagent`, `gh_issue_create` | CSS/TS edits, git push |
| rules-breaker | Sledgehammer & Lockpick 🔨 | `adversarial_fuzzer`, `adversarial_attack_runner`, `adversarial_commit` (scoped to `tests/adversarial/`), `gh_issue_create` | production changes, self-patch |
| platform-guardian | Routing Circuit Breaker 🔌 | `provider_prober`, `failover_toggle`, `gh_issue_create` | modifying permanent config files |

Enforcement: `provision_weapons()` returns the exact allowlist;
`authorize()` fails closed; `assert_least_privilege()` raises
`LeastPrivilegeViolation` on any foreign weapon; `assert_commit_scope()`
enforces `commit_scopes` (rules-breaker may commit **only** under
`tests/adversarial/`). Invariant (tested): the auditor family — task-auditor,
ecosystem-scout, federation-auditor, human-eye, platform-guardian — holds
**zero** `CODE_WRITE_WEAPONS`; rules-breaker holds no file-edit weapons
(self-patch forbidden) and only the scoped commit weapon.

## 7. Role Output Contracts (acceptance criteria)

* **Ecosystem Scout** — `validate_scout_batch()`: ≥ `MIN_SCOUT_PROPOSALS = 10`
  proposals, each with non-empty `pros`, `cons`, `risks` and
  `dont_do_this` ("এটা করা যাবে না") plus a `philosophy_verdict` that must be
  one of `CORE_PHILOSOPHY_FILTERS = ("Simple > Clever", "Complexity must earn
  existence", "Zero-Admin")`. Fail-closed otherwise.
* **Rules Breaker** — `validate_exploit_report()`: dual vector
  (`guard_evasion` | `unguarded_damage`), failing test **must** live under
  `tests/adversarial/`, a `P0-critical` issue **must** be filed,
  `patch_code_present` **must** be False (no self-patch), and the
  `unguarded_damage` vector requires measured damage evidence.
* **Human Eye** — `validate_visual_finding()`: issue-only role;
  `code_edit_proposed` must stay False; every finding carries surface,
  finding and a `recommended_issue` with aesthetic direction.

## 8. Appendix A — Integration hunks for `scripts/agents/continuous_agent_loop.py`

`scripts/agents/continuous_agent_loop.py` is a **pre-existing** file; these
content-anchored hunks are applied by the maintainer/gate chain when wiring
the matrix in. Call sites (the two `classify_task_role(...)` invocations)
need **no change** — the replacement keeps the legacy signature.

### Hunk A — import the matrix (anchor: the stdlib import block)

```python
 import sys
 import time
 from pathlib import Path
 from typing import Any
+
+sys.path.insert(0, str(Path(__file__).resolve().parent))
+from role_trigger_matrix import (  # S09 (#489): deterministic role trigger matrix
+    DECISION_DISPATCH,
+    dispatch_from_labels,
+)
 
 # Configure UTF-8 for cross-platform stability
```

### Hunk B — extend the role registry (anchor: the `ROLES` dict closing entries)

```python
     "watcher": "Telemetry, heartbeat health, and ecosystem drift specialist",
+    # S09 (#489): Deterministic Role Trigger Matrix — contracts live in
+    # scripts/agents/role_trigger_matrix.py (single source of truth).
+    "task-auditor": "Pre-landing compliance, boundary & ledger auditor",
+    "ecosystem-scout": "Global tech radar & strategic critic (read-only)",
+    "federation-auditor": "11-satellite parity & drift auditor (read-only)",
+    "human-eye": "PR styling & aesthetic director (issue-only)",
+    "rules-breaker": "Red-team chaos engineer (tests/adversarial/ only)",
+    "platform-guardian": "External AI provider sentry & failover toggle",
 }
```

### Hunk C — replace the keyword matcher (anchor: the full legacy body)

```python
 def classify_task_role(title: str, labels: list[str], body: str) -> str:
-    """Intelligently map issue context to one of the 7 specialist roles."""
-    combined = f"{title} {' '.join(labels)} {body}".lower()
-    if any(k in combined for k in ["sec", "security", "secret", "gitleaks", "credential", "vulnerability"]):
-        return "security-breaker"
-    if any(k in combined for k in ["ci", "workflow", "action", "pipeline", "matrix"]):
-        return "ci-fixer"
-    if any(k in combined for k in ["audit", "review", "parity", "drift", "readiness"]):
-        return "auditor"
-    if any(k in combined for k in ["plan", "adr", "architecture", "rfc", "contract"]):
-        return "planner"
-    if any(k in combined for k in ["browser", "e2e", "ui", "frontend", "playwright"]):
-        return "browser-qa"
-    if any(k in combined for k in ["telemetry", "heartbeat", "health", "watcher", "monitor"]):
-        return "watcher"
-    return "coder"
+    """DEPRECATED free-text matcher (#489) — deterministic label-plane dispatch.
+
+    Issue #489 deprecates keyword matching in titles/bodies. ``title`` and
+    ``body`` are retained for call-site compatibility but are NEVER
+    inspected: dispatch is an exact-match lookup on the structured label
+    plane via scripts/agents/role_trigger_matrix.py (fail-closed). The
+    legacy contract of falling through to "coder" is preserved for unrouted
+    signals so existing call sites and prompts keep working unchanged.
+    """
+    decision = dispatch_from_labels(frozenset(labels))
+    if decision.decision != DECISION_DISPATCH or decision.role_id is None:
+        return "coder"
+    return decision.role_id
```

### Parity note

`CONTRACT_VERSION = "agent-loop-contract/1"` is untouched and no flag
behaviour changes (`--verify-only` output is identical), so the #67 parity
marker between the public and mirror copies of the loop program remains
valid. The legacy 7 role ids (`auditor`, `security-breaker`, `browser-qa`,
`planner`, `watcher`, …) stay registered; Hunk B is purely additive.

## 9. Test evidence

39 offline tests green in dual mode (`python3 -m unittest
test_s09_role_trigger_matrix -v` and `pytest -q`), plus the module
self-test (`--self-test` → `SELF-TEST OK`). Coverage: directory shape
(8 roles, Triad completeness, Bengali identity), bijective event router,
every fail-closed deny path, label-plane priority & substring immunity,
RBAC invariants, Scout/Exploit/Visual contracts, deprecation tombstones.
