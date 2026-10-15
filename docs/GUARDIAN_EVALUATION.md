---
id: guardian-evaluation
title: "CI Guardian — PR Evaluation Rules (supremeai-open)"
document_role: reference
status: active
canonical: true
owner: auditor
last_verified: 2026-10-15
related_docs:
  - AGENTS.md
  - AGENT_RULES.md
  - docs/AUTONOMY_LOOP_CONTRACT.md
  - docs/CONTRIBUTING.md
source_issue: 37
source_pr: null
supersedes: []
superseded_by: []
---

# Guardian Evaluation Rules

Contract companion to `api-schemas/guardian-evaluation.schema.json`. This document is
the SSOT for **how** the CI Guardian derives its verdict; the schema is the SSOT for
**what** it emits. Implementations (public or private-mirror) that evaluate Pull
Requests and claim autonomous merge authority MUST conform to both — a verdict that
cannot be re-derived from these rules is invalid, no matter who emitted it.

## 1. What Is Evaluated

One evaluation per head SHA. The evaluator binds to the PR's immutable `head_sha`
(schema: `target.head_sha`); any new push invalidates all prior evaluations and forces
a full re-run — never an incremental re-score of unchanged categories.

## 2. The Four Categories (exactly one check entry each)

| Category | Weight | What must hold |
|---|---|---|
| `template_adherence` | 20 | PR body follows the task contract (Summary + `Refs #N` claim + evidence sections); `Closes #N` rides in the commit message (squash doctrine, AGENT_RULES U8). |
| `scope_boundary` | 25 | Diff stays inside the declared Touching Files; protected paths untouched; no un-declared file classes introduced. |
| `test_evidence` | 30 | The 3-tier process contract is present AND reproducible: reflection diff matches the declared scope; smoke/verify commands exit 0; test invocation is recorded with the exact tier output. |
| `security_scan` | 25 | Secret scanning and public-boundary checks are clean on the PR's own commits (`origin/main..HEAD`). |

Weights sum to 100. A category is `warn` only when the criterion is met with
documented reservations; `warn` never blocks by itself — it costs score.

## 3. Scoring

- Each category scores 0–100 and contributes `score × weight / 100`.
- `score.overall` = sum of contributions, floored (integer, 0–100).
- `score.threshold` is the configured autonomous-merge floor (default **80**).

## 4. Verdict Derivation (deterministic)

Evaluated strictly in this order — the first matching rule wins:

1. **REJECT** if any of:
   - `security_scan` = `fail` (boundary/secret violation — never healable automatically);
   - `scope_boundary` = `fail` **and** the diff touches protected paths;
   - the PR fails the duplicate-PR / anti-collision doctrine (U4) — a same-issue or same-token open PR already exists.
2. **HOLD** if any of:
   - any category is `fail` (healable — the PR gets a HOLD_AND_FIX list);
   - `score.overall < threshold`.
3. **PASS** otherwise.

`verdict_reasons` MUST cite the fired rule(s) verbatim so the verdict is re-derivable
from the check list alone.

## 5. Autonomous Merge Eligibility

`merge_eligibility.eligible = (verdict == PASS) AND (score.overall >= threshold) AND
(no `security_scan` fail at any status)`.

An eligible PR may be landed by the merge automation; a PASS below threshold lands
only through the normal gate path (all checks green + freshness), not autonomously.
When `eligible=false`, `merge_eligibility.reasons` MUST be non-empty.

## 6. Healing Instructions (HOLD_AND_FIX)

Every HOLD/REJECT evaluation MUST emit `healing_instructions`: one entry per failed
criterion, each a single concrete step (`category`, `instruction`, `automatable`).
This is the list format consumers already observe live on the board (e.g. template-gap
metadata fixes marked automatable, reviewer-judgement items marked not).

Rules: instructions are additive-only (no rewrites of prior evaluations); a re-run on
the same SHA MUST produce byte-identical output (determinism doctrine); the list is
consumed by coder agents — an `automatable: true` item must be executable without
human judgement.

## 7. Example Envelope (trimmed)

```json
{
  "schema_version": "1.0",
  "target": { "pr_number": 177, "head_sha": "<40-hex>", "base_branch": "main" },
  "evaluator": { "name": "ai-pr-evaluator", "contract_version": "guardian-evaluation/1" },
  "checks": [
    { "category": "template_adherence", "status": "fail", "score": 30, "weight": 20,
      "details": "PR-template v2 incomplete: missing ## Summary and Refs #N",
      "evidence": ["pr-body section scan"] },
    { "category": "scope_boundary", "status": "pass", "score": 100, "weight": 25 },
    { "category": "test_evidence", "status": "pass", "score": 90, "weight": 30 },
    { "category": "security_scan", "status": "pass", "score": 100, "weight": 25 }
  ],
  "score": { "overall": 82, "threshold": 80 },
  "verdict": "HOLD",
  "verdict_reasons": ["template_adherence=fail"],
  "merge_eligibility": { "eligible": false, "reasons": ["verdict != PASS"] },
  "healing_instructions": [
    { "category": "template_adherence",
      "instruction": "Complete PR-template v2: add ## Summary and Refs #N to the PR body",
      "automatable": true }
  ]
}
```

## Related Documents

- [AGENTS.md](../AGENTS.md) — agent entrypoint; zero-admin pathways
- [AGENT_RULES.md](../AGENT_RULES.md) — U4 anti-duplicate, U8 closing-keyword doctrine
- [docs/AUTONOMY_LOOP_CONTRACT.md](./AUTONOMY_LOOP_CONTRACT.md) — the loop that consumes evaluations
- [docs/CONTRIBUTING.md](./CONTRIBUTING.md) — submission paths and PR contract
