# Guardian Evaluation Contract

Data contract for the CI Guardian's automated evaluation of incoming Pull
Requests. The machine contract is SSOT'd in
[`api-schemas/guardian-evaluation.schema.json`](../api-schemas/guardian-evaluation.schema.json);
this document is the human-readable companion and the normative statement of
the decision rules, criteria catalog, and the autonomous merge eligibility
threshold.

**Related:** issue #37 (`feat(governance): PR evaluation schema and constitutional gate
contracts`), the Merge Gate implementation (#96, since consolidated into
`landing.yml` by #155), [`AGENT_RULES.md`](../AGENT_RULES.md) §13/§15,
[`docs/AGENT_LOOP_SPEC.md`](./AGENT_LOOP_SPEC.md) §4 (evidence-tier SSOT).

---

## 1. Purpose

Every PR that targets a federation repository is evaluated by a CI Guardian —
on the public boundary by the auto-landing workflow
(`.github/workflows/landing.yml`) fed by the guard jobs of
`.github/workflows/pipeline.yml`, and on the private monorepo by its CI
Guardian. The evaluation consumes only machine-checkable facts: workflow job
outcomes, guard-script exit codes, and GitHub PR state fields.

This contract exists so that:

1. **A verdict is always backed by facts.** Every criterion result records
   `detail` (what was actually checked) and `source` (where the fact came
   from). Fabricated or hardcoded pass statuses are forbidden —
   [`AGENT_RULES.md`](../AGENT_RULES.md) §13: *services degrade honestly; fake
   health/pass status is forbidden.*
2. **The author always receives healing guidance.** A criterion that fails
   MUST carry `healing_instructions`; the guardian aggregates them into the
   PR comment, so `HOLD`/`REJECT` verdicts arrive with actionable remediation
   steps, not just a red X.
3. **Public and private guardians speak one language.** The same schema and
   decision rules apply on both sides of the federation boundary (parity
   doctrine, [`docs/AGENT_LOOP_SPEC.md`](./AGENT_LOOP_SPEC.md) §6), so a
   private-side `REJECT` means exactly what a public-side `REJECT` means.

## 2. Decision Rules (normative)

The guardian emits exactly one of three verdicts per evaluated head state:

| Decision | Meaning | Condition |
|----------|---------|-----------|
| `PASS`   | All-green; PR is eligible for autonomous landing | **Every** criterion has status `pass`. No skipped, no failed. |
| `HOLD`   | Healable finding; PR waits in the queue | At least one **healable-class** criterion is `fail` or `skipped`, and no integrity-class criterion failed. |
| `REJECT` | Integrity violation; PR must be reworked | At least one **integrity-class** criterion (`security_scan`, `scope_boundary`, `duplicate_free`) is `fail`. |

Fail-closed properties (mirroring the real gate):

- **No partial credit.** `autonomous_merge_eligible` is `true` if and only if
  every criterion passed. There is no score threshold below 100 that lands a
  PR — the real gate watches every check to terminal state and fails on any
  failure (`.github/workflows/landing.yml`, evaluate step).
- **Unknown is not pass.** A check that could not run is recorded with status
  `skipped` and blocks eligibility. The landing workflow already treats an
  unresolved mergeability state the same way (it polls and then refuses
  fail-closed on `UNKNOWN`).
- **REJECT is reserved for integrity.** Template misses, stale branches, or a
  red test are fixable in-channel (`HOLD`); leaked credentials, proprietary
  content crossing the public boundary, or duplicate work orders are not —
  they demand rework (`REJECT`).
- **`PASS` never ships healing instructions** — there is nothing to heal;
  `HOLD`/`REJECT` always do.

## 3. Criteria Catalog

The catalog maps 1:1 onto the real public-boundary enforcement surfaces. The
`GUARD-*` identifiers are the federation-side guard IDs listed in
[`AGENT_RULES.md`](../AGENT_RULES.md) §15; workflow jobs are the enforcement
points in `.github/workflows/pipeline.yml` and `.github/workflows/landing.yml`.

| # | Criterion | Class | Enforcement surface | GUARD-* |
|---|-----------|-------|---------------------|---------|
| 1 | `template_adherence` | healable | PR body follows the template with Test Evidence present | `GUARD-TEMPLATE` |
| 2 | `issue_reference` | healable | PR title/body references an open issue | issue-reference-guard job |
| 3 | `branch_naming` | healable | Head branch matches the naming convention | branch-naming-guard job |
| 4 | `duplicate_free` | integrity | One issue = at most one open PR, anywhere in the federation (U4, Public-First SSOT §2.3.5) | `GUARD-DUPLICATE` |
| 5 | `scope_boundary` | integrity | Diff touches only declared scope; no proprietary paths/content cross the public boundary | `GUARD-SCOPE` + boundary_sanitization_guard |
| 6 | `test_evidence` | healable | Verification tiers recorded with dynamic evidence; skipped/failed tiers render FAIL, never a hardcoded PASS | `GUARD-EVIDENCE` |
| 7 | `security_scan` | integrity | Secret scan clean (gitleaks, 10 secret families) | secrets-scan job |
| 8 | `loop_contract_parity` | healable | Agent-loop contract surfaces agree (envelope, tiers, guards) | loop_contract_parity_guard (#118) |
| 9 | `checks_green` | healable | Every check on the PR head reached terminal success | evaluate step, `GUARD-MERGE` |
| 10 | `mergeable_state` | healable | `mergeable == CLEAN` (never `CONFLICTING`, never unresolved `UNKNOWN`) | evaluate step (mergeability poll) |

Suggested weights (informational score only — see §4): criteria 1/2/4/9 → 10,
criteria 3/8/10 → 5, criteria 5/6/7 → 15. Sum = 100.

## 4. Scoring and the Autonomous Merge Eligibility Threshold

- `score` (0–100) = sum of weights of criteria with status `pass`. Skipped and
  failed criteria contribute 0. **The score is a reporting aid, never a
  gate** — no threshold below 100 grants eligibility.
- The **autonomous merge eligibility threshold** is the strict conjunction:
  `autonomous_merge_eligible == true` ⇔ all criteria `pass` ⇔
  `decision == "PASS"`. The schema enforces both equivalences as cross-field
  contracts (a document claiming `PASS` with a skipped criterion, or `HOLD`
  with eligibility, does not validate).
- This design is intentionally anti-gaming: partial credit cannot be traded
  for a landing, a skipped tier cannot masquerade as progress, and an
  integrity failure cannot be diluted by green everything-else.

## 5. Example Evaluation Result

Abridged `HOLD` example (in a real run the `criteria` array records the full
catalog — see §2's "no pass by absence" rule). This snippet validates against
[`api-schemas/guardian-evaluation.schema.json`](../api-schemas/guardian-evaluation.schema.json):

```json
{
  "schema_version": "1.0",
  "pr_number": 191,
  "head_sha": "9cb54c0012345678901234567890123456789abc",
  "repository": "Supremeai-bd/supremeai-open",
  "guardian_id": "merge-gate-public",
  "evaluated_at": "2026-10-16T03:30:00Z",
  "decision": "HOLD",
  "decision_reason": "checks_green failed: 1 of 8 checks failing on head 9cb54c0; all other criteria green.",
  "criteria": [
    {
      "criterion": "template_adherence",
      "status": "pass",
      "weight": 10,
      "detail": "PR body matches template sections: Summary, Linked Issue, Type of Change, Test Evidence, Rollback.",
      "source": "pipeline.yml/issue-reference-guard + landing.yml/evaluate"
    },
    {
      "criterion": "checks_green",
      "status": "fail",
      "weight": 10,
      "detail": "gh pr checks --watch: check 'test-matrix (3.12)' failed; 7 others green.",
      "source": "landing.yml/evaluate",
      "healing_instructions": [
        "Read the failing job log in the PR checks view.",
        "Reproduce locally: bun run test:unit (or the failing suite's command).",
        "Push a fix commit; the guardian re-evaluates the new head automatically."
      ]
    },
    {
      "criterion": "mergeable_state",
      "status": "pass",
      "weight": 5,
      "detail": "mergeable == CLEAN after polling (no unresolved UNKNOWN).",
      "source": "gh pr view .mergeable"
    }
  ],
  "score": 85,
  "autonomous_merge_eligible": false,
  "healing_instructions": [
    "checks_green: read the failing 'test-matrix (3.12)' job log; reproduce with the suite's command; push a fix commit."
  ],
  "guard_results_url": "https://github.com/Supremeai-bd/supremeai-open/actions/runs/1234567890"
}
```

## 6. Federation Applicability

- **Public boundary** (`Supremeai-bd/supremeai-open`): the guardian verdicts
  materialize as the Merge Gate's `LANDED`/`BLOCKED` comments —
  `PASS` ⇒ autonomous squash-merge + bridge dispatch; `HOLD`/`REJECT` ⇒ the
  landing is held and the reason is posted on the PR.
- **Private monorepo** (`Supremeai-bd/supremeai`): the CI Guardian evaluates
  bridge-intake work orders and internal PRs with the same schema; results
  feed the private audit ledger. Contract parity follows the same doctrine as
  the agent-loop parity guards (`loop_contract_parity_guard`, #118).
- **Versioning:** rule changes (new criterion, re-classified severity,
  changed decision mapping) MUST bump `schema_version` and update §2/§3 here
  in the same change, so consumers can never mix contract generations.

## 7. Verification Contract

1. **Schema check:** `python3 -c "import json; json.load(open('api-schemas/guardian-evaluation.schema.json'))"` must exit 0 (boot-smoke tier).
2. **Contract self-test:** example documents for `PASS`/`HOLD`/`REJECT` and
   the negative paths (a `PASS` containing a skipped criterion, a `REJECT`
   without an integrity failure, a failing criterion without healing
   instructions) must validate/reject exactly as §2 prescribes. The schema's
   cross-field `allOf` contracts encode these rules mechanically.
3. **Markdown link check:** every relative link in this document must resolve
   on `main` — broken links are defects ([`AGENT_RULES.md`](../AGENT_RULES.md)
   §8, Document Circle / Navigation Policy).
4. **Fixture validation (planned):** issue #45's `scripts/validate_schemas.py`
   CLI will validate `api-schemas/*.schema.json` and matching fixture files
   in CI; example documents from §5 become fixtures at that point.
