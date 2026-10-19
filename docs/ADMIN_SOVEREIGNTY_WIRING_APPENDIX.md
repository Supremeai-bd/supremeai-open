# S15 — Admin Sovereignty Guard: Wiring Appendix (issue #528)

Status: OPERATOR/ADMIN-APPLIED INTEGRATION (protected paths and
pre-existing files — the agent lane never edits .github/, root rules
files, or private-monorepo sources; per the #523 rejection doctrine all
pre-existing-file edits ship as appendices).

The decision SSOT landed as scripts/ci/admin_sovereignty_guard.py
(D1 quarantine_decision, D2 filter_pick_next, D3 work_queue_marking,
D4 ci_claim_gate). This appendix wires it into every enforcement layer
listed by issue #528.

## 1. Label provisioning (Admin seat)

Create the sovereign label once (color per spec: dark red B60205):

```bash
gh label create authority:admin-only --color B60205 --description "Admin manual execution only - autonomous agents strictly quarantined"
```

Existing issues that need quarantine get the label added manually; the
guard also matches casing variants fail-closed.

## 2. Continuous agent loop quarantine (operator seat)

In scripts/agents/continuous_agent_loop.py import the SSOT and gate the
three steps plus pick-next (reference calls — placement is operator's):

```python
from scripts.ci.admin_sovereignty_guard import (
    DENIAL_CODE,
    filter_pick_next,
    quarantine_decision,
)

# step_1_understand / step_3_inspect_state / step_4_branch (before checkout):
decision = quarantine_decision(issue_labels, issue_number)
if not decision.allowed:
    log("[Admin Sovereignty Gate]", decision.message)
    return None

# --pick-next candidate selection:
eligible, quarantined = filter_pick_next(candidate_list)
for q in quarantined:
    log("[pick-next]", "skipped", q["candidate"].get("number"), "-", q["reason"])
```

Fail-closed contract: any labels parse error raises ValueError — the
loop must treat a ValueError as skip (never claim on uncertainty).

## 3. MCP Tower enforcement (operator seat — deploy surface)

In infrastructure/mcp-control-plane/src/tools/bridge.tools.ts, the
work.claim handler calls the same decision (ported 1:1 from D1):

```typescript
// normalize: strip + lowercase each label, then compare
const adminOnly = labels.map((l) => l.trim().toLowerCase())
  .includes("authority:admin-only");
if (adminOnly) {
  return {
    isError: true,
    content: [{ type: "text", text:
      `CLAIM_DENIED_ADMIN_ONLY: Issue #${issueNumber} is strictly reserved for human Admin execution. Autonomous bots cannot claim.` }],
  };
}
```

bridge.work_queue marks each issue from D3:

```typescript
// per issue: claimable + executionLane
const marking = adminOnly
  ? { claimable: false, executionLane: "admin-only" }
  : { claimable: true, executionLane: "swarm" };
```

## 4. CI claim gate (pipeline.yml — protected path)

In the merge-gate stage, block agent-opened PRs that close admin-only
issues (D4 semantics; the step below is reference — the operator adds
it alongside the existing claim gate):

```yaml
      - name: Admin sovereignty claim gate (issue 528)
        shell: bash
        run: |
          python3 scripts/ci/admin_sovereignty_guard.py --self-test
          LABELS=$(gh api repos/${{ github.repository }}/issues/${{ github.event.issue.number }} --jq '.labels[].name' | paste -sd, -)
          python3 scripts/ci/admin_sovereignty_guard.py --check \
            --issue ${{ github.event.issue.number }} \
            --labels-json "[$(echo "$LABELS" | sed 's/[^,]*/"&"/g')]"
```

Exit 2 from --check fails the step: agent-opened PRs closing
authority:admin-only issues can never auto-merge.

## 5. Issue templates (.github/ISSUE_TEMPLATE/ — protected path)

Add to agent-task.yml dropdowns:

```yaml
      - type: dropdown
        id: execution_authority
        attributes:
          label: Execution Authority
          options:
            - autonomous-agent (Swarm-claimable by any agent)
            - authority:admin-only (Human Admin manual execution only - agents strictly quarantined)
        validations:
          required: true
```

Template maintainer maps the second choice to the authority:admin-only
label via the existing label-routing automation.

## 6. Constitution: Rule U11 (root rules files — pre-existing)

Append verbatim to AGENT_RULES.md (and AGENTS.md index):

```text
Rule U11 (Admin Sovereignty & Quarantine Doctrine): Issues labeled
authority:admin-only are reserved exclusively for human Admin execution.
Agents must immediately yield: never claim, never branch, never push,
never open PRs against them. Any label parse uncertainty is a skip.
Violation of U11 is a hard boundary breach, not a style issue.
```

## 7. Rollback

Remove the U11 text, the pipeline gate step, and the loop/Tower calls.
The guard module is inert when not invoked and can be deleted
independently; the label is repo metadata removed via gh label delete.
