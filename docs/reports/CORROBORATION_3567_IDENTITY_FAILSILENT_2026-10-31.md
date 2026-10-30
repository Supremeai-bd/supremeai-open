# Corroboration — #3567 datum re-verified live (third agent, fresh tools/list capture)

> **Agent:** GLM Agent 08 (Job ID 486735) · **Captured:** 2026-10-31 ~01:2x+08 (17:2xZ)
> **Method:** direct JSONRPC `tools/list` over the tower MCP session (158 tools returned),
> schema-level read of the six identity-bearing inputSchemas — no cached board, no issue-plane
> text reuse. Report-only corroboration; no claim, no code edit, no closure ask (the datum's
> own Never-do governs).

## Captured schema facts (machine-read this cycle)

| Tool | identity field | additionalProperties |
|---|---|---|
| `work_claim` | `agentId` | ABSENT |
| `bridge_work_renew` | `agentId` | ABSENT |
| `bridge_work_release` | `agentId` | ABSENT |
| `bridge_lease_manage` | `agentId` | ABSENT |
| `bridge_submit` | `agentIdentity` | ABSENT |
| `bridge_submit_patch` | `agentIdentity` | ABSENT |

This is the exact split #3567 asserts: four lease-plane tools name it `agentId`, two
submit-plane tools name it `agentIdentity`, and `additionalProperties` is absent on all six —
a caller spelling the field the wrong way gets fail-silent schema-tolerant acceptance instead
of a loud 4xx. Behavioral echo (first-hand, prior cycles of this agent): `work_claim` accepts
`{"issueNumber": N, "agentId": "GLM Agent 08 (Job 486735)"}` and `bridge_submit_patch`
requires `agentIdentity` — both succeed silently against the mismatched names above.

## Datum disposition

- #3567's premise is **LIVE, not stale** as of this capture (U3 re-verify passed; nothing to
  skip). The tower-lane remedy (schema unification + `additionalProperties: false`) remains
  undeployed on the live plane.
- Loop dispatched this row to solver; per the row's own Never-do and the loop's report-only
  branch, the correct solver output is evidence via the bridge and no auto-close. Closure
  belongs to the verdict plane after the tower-lane fix deploys.

## Never-do (বাংলা)

- নতুন কোড-এডিট নয়, নতুন রাডার লেন নয় (R84-ই মূল লেন), #3530/#3567 কোনোটিই এখান থেকে
  close/reopen করা হবে না — রায় মালিকের।
