# S07 — PR Improvement & Zero-Regression Evaluator Spec (task #486)

Status: r1 · 2026-10-17 · Author: Z.ai Code (session web-26454b1b)
Scope: NEW `scripts/ci/pr_improvement_regression_guard.py` (pure-new-file
lane) + integration hunks for `.github/workflows/pipeline.yml` and
`.github/workflows/landing.yml` (protected paths — ship as the appendix
in §5, per CI_GUARDS r1 precedent) + offline contract tests
`tests/test_s07_pr_evaluator.py` (35 tests).

## 1. Normative criteria

A PR is certified PASS if and only if BOTH families hold. Every check
is deterministic, lexical, zero-dependency, offline (<3s), fail-closed.

Beneficial:
- scope_contract_alignment — every touched file is declared in the
  task contract's Touching Files (strict subsets allowed).
- positive_test_gain — at least one verified test assertion added
  (assert / expect( / self.assert / it( in test files) OR the request
  declares fixed_failing_tests (workflow-supplied from test runs).
- contract_schema_validation — touching api-schemas/ requires
  schema_validation == "verified" from the workflow's parse step
  (fail-closed otherwise).
- rejection_of_cosmetic_churn — the diff must carry net semantic
  content: whitespace-only moves, full-line comments, docstring fences,
  pure identifier renames, and pure relocations pair off and do not
  count. A diff with zero net semantic lines FAILS.

Zero-Regression:
- zero_test_suppression — no unittest.skip / pytest.mark.skip /
  it.skip / test.skip / xfail added; no assertion commented out; no
  assertion line deleted unless the identical stripped line is re-added
  (relocation allowance).
- zero_scope_leakage — hard-protected paths (.github/, .env, *.pem,
  *.key, id_rsa, *credential*, *.p12) fail even when declared;
  declaration cannot override protection.
- zero_dependency_bloat — additions to package.json
  dependencies/devDependencies blocks, requirements*.txt,
  pyproject.toml, go.mod, Cargo.toml, Gemfile fail unless
  allow_new_dependencies is explicitly true (ops decision, recorded).
- backward_compatibility — removed public symbols (def/function/class/
  export const/export interface/route decorators/argparse params) fail
  unless the symbol is re-added elsewhere in the diff (relocation) or
  a migration note naming the symbol is provided.

## 2. Evaluation request contract (data-only, no shell-outs)

The workflow computes git-diff facts and passes them as JSON; the guard
never touches git or the network:

```json
{
  "pr_number": 487,
  "declared_files": ["scripts/ci/x.py", "tests/test_x.py"],
  "changed_files": [
    {"path": "scripts/ci/x.py", "added": ["line..."], "removed": ["line..."]}
  ],
  "fixed_failing_tests": [],
  "migration_notes": [],
  "allow_new_dependencies": false,
  "schema_validation": null
}
```

Verdict shape: {verdict: PASS|FAIL, beneficial, zero_regression,
violations[{check, severity, evidence}], stats, evaluated_at}.
CLI: --evaluate request.json (exit 0 = PASS, 2 = FAIL incl. input
errors — fail-closed), --self-test.

## 3. Precedent and doctrine alignment

- Boundary Guard parity: hard-protected list mirrors the bridge lane's
  protected paths; guards cannot be social-engineered via declarations.
- Zero-regression "no test suppression" codifies doctrine (w5): gate
  chains may adjust landed test files, but agents never suppress tests.
- Fail-closed posture matches issue_template_guard (#473) exit codes
  (0/2) and stale_claim_releaser (#470) ValueError discipline.

## 4. Tier mapping (task #486 contract)

1. Tier 1: python3 -m unittest test_s07_pr_evaluator (35 tests) covers
   all four mandated cases (valid PASS, churn FAIL, suppression FAIL,
   out-of-scope FAIL) plus 31 more; the guard's own --self-test covers
   the same matrix standalone.
2. Tier 2: the workflow can replay the evaluator over recent merged
   PR diffs (evaluation requests are plain JSON — replayable).
3. Tier 3: stdlib only, zero network, deterministic.

## 5. Appendix — integration hunks (protected paths)

pipeline.yml (PR gate, after test job):

```yaml
  pr-evaluation:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: {fetch-depth: 0}
      - name: PR Improvement & Zero-Regression Gate
        run: |
          python3 scripts/ci/diff_to_request.py > /tmp/eval_request.json
          python3 scripts/ci/pr_improvement_regression_guard.py \
            --evaluate /tmp/eval_request.json
```

landing.yml (final pre-squash barrier, before the merge step):

```yaml
      - name: Final zero-regression barrier
        run: |
          python3 scripts/ci/diff_to_request.py --base "$BASE_SHA" \
            > /tmp/eval_request.json
          python3 scripts/ci/pr_improvement_regression_guard.py \
            --evaluate /tmp/eval_request.json
```

diff_to_request.py (git-diff facts -> evaluation request; declares
files from the task issue contract body) is a thin workflow adapter and
may ship with the maintainer's own wiring; the evaluator contract above
is the stable interface.
