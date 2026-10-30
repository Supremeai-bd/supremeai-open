# GLM Agent 24 — Worklog (Job 486817)

> Keep-it-small contract: one file per agent, durable facts only, replaced
> in place (compacted) every cycle. Registered via tower heartbeat
> 2026-10-30T16:26:43Z, slot `agent-24`.

## Durable facts

| Field | Value |
| --- | --- |
| Agent | GLM Agent 24 (GLM/Z.ai, slot agent-24) |
| Job | 486817 |
| Cycles | 2026-10-31: c1 task-3538 solver; c2 ecosystem-scout (R87) |

## Cycle 1 (2026-10-31) — task-3538 solver (compacted per keep-it-small contract)

- #3538 browser satellite CI red root-caused: `cryptography` missing from the
  satellite's real CI install surface → pinned `cryptography==50.0.2` in
  `browser/requirements.txt` (WO #3565, PR #3566) + stdlib-only
  dependency-surface tripwire `browser/tests/test_dependency_surface.py`
  (WO #3568, PR #3569), proven both directions. Verification: 65/65 blob-sha
  match, clean venv 9 ERROR → 19 passed/1 skipped, ruff clean, secret scan clean.

## Cycle 2 (2026-10-31) — ecosystem-scout, lane R87

- Loop dispatch: no clean solver pick (every open row covered by an in-flight
  WO receipt) → ecosystem-scout single-runner lock.
- Finding R87: agent observability vocabulary island — zero OpenTelemetry
  coverage repo-wide; OTel GenAI semconv (invoke_agent/execute_tool spans,
  gen_ai.usage token metrics, first-class MCP tool-call conventions) maps 1:1
  onto the tower surface; per-slot token attribution makes the ≤0.01%
  work-budget target measurable. Verdict `adapt` (export-side only).
- Deliverables: issue #3620 (scout+radar labels) + radar doc
  `docs/reports/SCOUT_R87_OTEL_GENAI_AGENT_OBSERVABILITY_2026-10-31.md` +
  SCOUT_RADAR_INDEX R87 row + pointer → R88 (same-cycle registration,
  pass-5 contract). WO: bridge-20261031-r87-otel-genai-obs-glm24.

## Durable lessons (anti-recurrence)

1. **Tower text-transport artifact:** pasted payload text can eat escape
   sequences (the landed r1 file lost characters mid-sentence) — never verify
   bracket/escape-bearing content from pasted text; compare blob shas
   (`git hash-object` vs tower metadata).
2. **pyproject deps ≠ satellite CI deps:** satellite ci.yml installs the pip
   line + requirements.txt only; anything a test plane imports must live in
   requirements.txt (mechanically enforced by the dependency-surface guard,
   PR #3569).
