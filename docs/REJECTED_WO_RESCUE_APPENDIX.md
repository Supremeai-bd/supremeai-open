# Rejected WO Rescue Pipeline — Operator Wiring Appendix (Issue #545)

**Deliverable**: `scripts/ci/rejected_wo_rescue.py` — the Intake Error
Classifier (Triage Plane) + rescue-plan SSOT for the Self-Healing Bridge.
**Doctrine compliance**: zero pre-existing-file edits; every hunk below is
applied by the operator/admin seat (protected or pre-existing paths).

## 1. Board evidence — triage verdict for all 8 live rejections

Ran the classifier against the verbatim intake-bot comments (2026-10-17):

| WO | Rejection reason (verbatim marker) | Mode | Healable | Rescue action |
|----|------------------------------------|------|----------|---------------|
| #546 | `patch failed: AGENTS.md:1 / README.md:1` | PATCH_APPLY_CONFLICT | ✅ | resubmit_pure_new_files, drop AGENTS.md+README.md (new-file patches collide with pre-existing satellite files) |
| #511 | `task: (unparseable)` | TASK_ID_INVALID | ✅ | resubmit_with_task_id (`bridge-YYYYMMDD-<slug>`) |
| #509 | `task: (unparseable)` | TASK_ID_INVALID | ✅ | resubmit_with_task_id |
| #508 | `task: (unparseable)` | TASK_ID_INVALID | ✅ | resubmit_with_task_id |
| #507 | `task: (unparseable)` | TASK_ID_INVALID | ✅ | resubmit_with_task_id |
| #504 | `task: (unparseable)` | TASK_ID_INVALID | ✅ | resubmit_with_task_id |
| #503 | `task: (unparseable)` | TASK_ID_INVALID | ✅ | resubmit_with_task_id |
| #461 | `task: (unparseable)` | TASK_ID_INVALID | ✅ | resubmit_with_task_id |

**8/8 healable, 0 fatal** — matching the operator's own re-queue signal
(`SaifulHaqueNiloy` re-applied `bridge:queued` on every one of them).
Historical WO #523 (`continuous_agent_loop.py:882` + mode mismatch) also
classifies as PATCH_APPLY_CONFLICT → same drop-paths doctrine.

## 2. Bridge intake wiring (operator: `.github/` + `scripts/bridge/`)

In the intake rejection handler, after the fail-closed reason is composed and
`bridge:rejected` is applied, call the triage plane and apply its label plan:

```python
# scripts/bridge/<intake bot> — rejection handler tail
from ci.rejected_wo_rescue import triage  # landed module

verdict = triage(rejection_comment, issue_number=wo_number, task_title=wo_title)
if verdict["healable"]:
    apply_labels = verdict["labelPlan"]["apply"]  # handoff:ci-fixer, status:unclaimed
    # NOTE: bridge:rejected is NEVER removed (audit provenance per #545)
    post_comment(json.dumps(verdict["rescuePlan"], indent=2))  # ci-fixer reads this
```

Classifier verdict contract (consumed verbatim, no re-interpretation):

```json
{
  "classification": "HEALABLE_RESCUE | FATAL_DROP",
  "mode": "PATCH_APPLY_CONFLICT | TASK_ID_INVALID | BEHIND_MAIN |
           MISSING_REFLECTION | PR_CI_FAILED | FATAL_SECRET |
           FATAL_AST_VIOLATION | FATAL_BOUNDARY_TAMPERING | ADMIN_REVIEW |
           UNKNOWN",
  "healable": true,
  "conflictPaths": ["AGENTS.md"],
  "labelPlan": {"apply": ["handoff:ci-fixer", "status:unclaimed"],
                 "keep": ["bridge:rejected"], "remove": []},
  "rescuePlan": {"action": "...", "...": "..."}
}
```

Fail-closed default: any unrecognized rejection text classifies
`FATAL_DROP/UNKNOWN` — the pipeline never guesses a rescue.

## 3. `scripts/agents/role_trigger_matrix.py` — ci-fixer trigger expansion

Append to the ci-fixer RoleContract triggers (fragment SSOT:
`CI_FIXER_TRIGGER_CONTRACT` in the landed module):

```python
# issue #545: bridge rejection rescue routing
("event:pr.ci_failed",)  # in-flight PR repair
("event:bridge.rejected",)  # bridge intake rescue
# label matcher handled in dispatch: "handoff:ci-fixer"
```

Reflection check greps that must pass after wiring:

```
git grep -n "handoff:ci-fixer\|event:bridge.rejected" scripts/agents/
```

## 4. `scripts/agents/continuous_agent_loop.py` — rescue flow hook

Insert a rescue branch (new private method, called when the loop picks up an
issue labelled `handoff:ci-fixer`). The 5-step flow and its sequence guard
live in the landed module (`RESCUE_FLOW_STEPS`, `validate_transition`):

```
INSPECT  -> parse rejection comment via rejected_wo_rescue.triage()
REBASE   -> fetch origin main, assert ancestor, rebase, abort+quarantine on conflict
RETROFIT -> apply rescuePlan (drop paths / retrofit task id / add reflection section)
VERIFY   -> re-run 3-tier verification contract (--verify-only)
RESUBMIT -> push bridge/<task-id> and update the work order
```

Fail-closed: `validate_transition` forbids skipping, looping, and unknown
states; a failed REBASE quarantines the branch and releases the claim.

## 5. `scripts/ci/auto_bridge_pr_opener.py` — label propagation

When opening PRs from queued WOs, copy `handoff:ci-fixer` onto the PR so
`event:pr.ci_failed` repairs route back to the same role without re-triage.

## 6. Verification contract

```bash
python3 scripts/ci/rejected_wo_rescue.py --self-test          # 36 assertions
python3 -m pytest tests/test_rejected_wo_rescue.py -q          # 36 passed
python3 -m unittest tests.test_rejected_wo_rescue              # 36 passed (dual-mode)
python3 scripts/ci/cross_platform_invariant_guard.py --files \
    scripts/ci/rejected_wo_rescue.py tests/test_rejected_wo_rescue.py   # clean
```

## 7. Rollback

Pure addition: delete `scripts/ci/rejected_wo_rescue.py`,
`tests/test_rejected_wo_rescue.py`, and this appendix. No existing file,
workflow, or label state is modified by the agent-side payload.
