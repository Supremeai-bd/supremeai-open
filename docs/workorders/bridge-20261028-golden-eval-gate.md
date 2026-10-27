# Bridge Work Order — Wire the 90% Golden-Eval Regression Gate into the Release Pipeline (#1362, item 3)

> Author: zai-mcp-tower-agent (cron Job 477795, run 4) · 2026-10-28
> Status: admin-appliable patch — `.github/` is a protected path; the bridge lane cannot edit it (fail-closed by design, see #1554 precedent).
> Ships with: `evals/golden/suite.json` (100 cases), `evals/golden/run_eval.py` (stdlib-only runner), `evals/golden/fixtures.json` (10-case calibration subset).

## 1. Why

Issue #1362 acceptance item 3: *"Integrate an evaluation threshold gate into the PR release pipeline"* with **90% threshold blocking release pipelines**. The suite and runner land via this bridge submission; the wiring needs an admin-side commit because the pipeline file is protected.

## 2. What the runner guarantees before you wire it

- `python evals/golden/run_eval.py --self-test` — 12 deterministic probes of every rubric constraint (pass AND fail paths). Exit 0.
- `python evals/golden/run_eval.py` (fixture provider) — mechanics self-test over 10 recorded calibration cases: coverage `10/100`, accuracy `1.0`, verdict `PASS`, exit 0. The report labels this **"mechanics self-test — NOT a model-quality measurement"** (U2 honesty); the other 90 cases are listed as `no_fixture` and excluded from scoring — never fabricated PASS.
- `python evals/golden/run_eval.py --provider http --min-accuracy 0.90` — the real quality gate. Requires `SUPREME_EVAL_ENDPOINT` (POST `{prompt}` → `{response, latency_ms?, cost_usd?}`) and optional `SUPREME_EVAL_TOKEN`. Final stdout line is always `GOLDEN_EVAL_VERDICT=PASS|FAIL`; exit 0/1 gate, exit 2 config error (fail-closed).

## 3. Exact patch (git apply) — add two jobs to `.github/workflows/pipeline.yml`

Insert into the `jobs:` map (indent two spaces under `jobs:`):

```yaml
  golden-eval-harness:
    name: "G-GoldenEval harness — scorer self-test + fixture mechanics (#1362)"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Scorer self-test (must stay deterministic)
        run: python evals/golden/run_eval.py --self-test
      - name: Fixture mechanics run (calibration subset, honest coverage label)
        run: python evals/golden/run_eval.py

  golden-eval-gate:
    name: "G-GoldenEval — 90% quality regression gate (#1362)"
    runs-on: ubuntu-latest
    needs: [golden-eval-harness]
    steps:
      - uses: actions/checkout@v4
      - name: Live golden eval (90% threshold, fail-closed)
        env:
          SUPREME_EVAL_ENDPOINT: ${{ secrets.SUPREME_EVAL_ENDPOINT }}
          SUPREME_EVAL_TOKEN: ${{ secrets.SUPREME_EVAL_TOKEN }}
        run: python evals/golden/run_eval.py --provider http --min-accuracy 0.90
```

Admin notes:
1. If your release entrypoint is a different workflow, the same two jobs port verbatim — keep `golden-eval-gate` in the `needs:` chain of whatever job publishes/releases.
2. `golden-eval-harness` needs no secrets and should run on every PR (pins the scorer so rubric regressions fail fast, shift-left per SPEC §5).
3. `golden-eval-gate` fails closed while `SUPREME_EVAL_ENDPOINT` is unset (exit 2) — add the secret before enabling it on release paths, or start with `continue-on-error: true` for one week to observe live accuracy before enforcing.
4. Threshold lives in `suite.json` (`meta.threshold`) and can be overridden per-run with `--min-accuracy`; changing it needs no pipeline edit.

## 4. Rollback

Revert the admin commit that adds the two jobs; delete the `evals/golden/` directory if desired (purely additive — no existing code path imports it). No state, config, or credential side effects.
