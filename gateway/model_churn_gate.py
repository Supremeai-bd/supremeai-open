"""Token-churn regression gate for model bumps (radar P-03, issue #1662).

Blocks a model bump when the committed evaluation artifact shows output-token
cost growth >30% or diff churn >2x versus the baseline entry on the SAME
golden task set, without a same-task quality comparison demonstrating
non-regression (admin-ratified reopen of 2026-10-27: "block model changes
that increase token cost by >30% or diff churn >2x without quality
improvement").

Design notes
------------
- Fail-closed everywhere: a missing baseline, a malformed ledger, a malformed
  candidate artifact, a task-set mismatch, or a degenerate baseline metric all
  BLOCK. The gate never invents numbers to allow a bump.
- The gate consumes committed evaluation artifacts; it never runs models.
  Producing the artifact for a candidate model is the bump author's job
  (same-task, golden task set, recorded in the ledger schema below).
- Stdlib only, deterministic, no network, no LLM inference.

Ledger schema (``model_churn_baseline.json``)::

    {
      "schema": "model-churn-ledger/1",
      "entries": {
        "<model_id>": {
          "output_tokens": <int, total output tokens across the task set>,
          "diff_files_changed": <int, files touched by the model's diffs>,
          "task_set_id": "<golden task set identifier>",
          "quality_score": <float | null, same-task quality metric>,
          "measured_at": "<ISO-8601 date the measurement was taken>"
        }
      }
    }

Candidate artifact schema (what a bump author must present)::

    {
      "model_id": "<candidate model id>",
      "baseline_id": "<model id of the incumbent being replaced>",
      "output_tokens": <int>,
      "diff_files_changed": <int>,
      "task_set_id": "<must equal the baseline entry's task_set_id>",
      "quality_comparison": {"quality_score": <float>} | absent
    }

CLI (eval lane)::

    python -m gateway.model_churn_gate --ledger gateway/model_churn_baseline.json \
        --candidate candidate.json    # exit 0 = allow, 2 = block, 3 = config error
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

LEDGER_SCHEMA = "model-churn-ledger/1"

# Admin-ratified budgets (issue #1662, reopened 2026-10-27).
OUTPUT_TOKEN_GROWTH_MAX = 0.30  # >30% output-token cost growth blocks
DIFF_CHURN_RATIO_MAX = 2.0      # >2x diff churn blocks

# Verdict kinds.
ALLOW = "allow"
BLOCK = "block"

_REQUIRED_CANDIDATE_FIELDS = ("model_id", "baseline_id", "output_tokens", "diff_files_changed", "task_set_id")
_REQUIRED_BASELINE_FIELDS = ("output_tokens", "diff_files_changed", "task_set_id")


@dataclass
class ChurnVerdict:
    allowed: bool
    kind: str  # ALLOW | BLOCK
    model_id: str
    baseline_id: str | None
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def load_ledger(path: str | Path) -> dict:
    """Load and shape-validate a churn ledger. Raises ValueError when malformed."""
    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("ledger root must be an object")
    if data.get("schema") != LEDGER_SCHEMA:
        raise ValueError(f"unsupported ledger schema: {data.get('schema')!r}")
    if not isinstance(data.get("entries"), dict):
        raise ValueError("ledger 'entries' must be an object")
    return data


def _quality_case_holds(candidate: dict, baseline: dict) -> bool:
    """A same-task quality comparison demonstrating non-regression."""
    qc = candidate.get("quality_comparison")
    if not isinstance(qc, dict):
        return False
    cand_q = qc.get("quality_score")
    base_q = baseline.get("quality_score")
    if not isinstance(cand_q, (int, float)) or not isinstance(base_q, (int, float)):
        return False
    return float(cand_q) >= float(base_q)


def evaluate_bump(candidate: dict, ledger: dict) -> ChurnVerdict:
    """Evaluate a candidate-model bump against the ledger. Fail-closed."""
    model_id = candidate.get("model_id") if isinstance(candidate, dict) else None
    baseline_id = candidate.get("baseline_id") if isinstance(candidate, dict) else None

    def _block(kind_reason: str, detail: str) -> ChurnVerdict:
        return ChurnVerdict(False, BLOCK, str(model_id), baseline_id, [f"{kind_reason}: {detail}"])

    if not isinstance(candidate, dict):
        return _block("malformed_candidate", "candidate artifact must be an object")
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), dict):
        return _block("malformed_ledger", "ledger must be an object with an 'entries' object")

    missing = [k for k in _REQUIRED_CANDIDATE_FIELDS if candidate.get(k) is None]
    if missing:
        return _block("malformed_candidate", f"missing fields {missing}")

    entries = ledger["entries"]
    baseline = entries.get(candidate["baseline_id"])
    if not isinstance(baseline, dict):
        return _block("no_baseline", f"no ledger entry for baseline {candidate['baseline_id']!r}")
    missing_base = [k for k in _REQUIRED_BASELINE_FIELDS if baseline.get(k) is None]
    if missing_base:
        return _block("malformed_baseline", f"baseline entry missing fields {missing_base}")

    if candidate["task_set_id"] != baseline["task_set_id"]:
        return _block(
            "task_set_mismatch",
            f"candidate {candidate['task_set_id']!r} vs baseline {baseline['task_set_id']!r}",
        )

    base_out = baseline["output_tokens"]
    base_churn = baseline["diff_files_changed"]
    if not isinstance(base_out, (int, float)) or base_out <= 0:
        return _block("degenerate_baseline", "baseline output_tokens must be > 0")
    if not isinstance(base_churn, (int, float)) or base_churn <= 0:
        return _block("degenerate_baseline", "baseline diff_files_changed must be > 0")

    cand_out = candidate["output_tokens"]
    cand_churn = candidate["diff_files_changed"]
    if not isinstance(cand_out, (int, float)) or cand_out < 0 or not isinstance(cand_churn, (int, float)) or cand_churn < 0:
        return _block("malformed_candidate", "output_tokens/diff_files_changed must be non-negative numbers")

    output_growth = (cand_out - base_out) / base_out
    churn_ratio = cand_churn / base_churn
    metrics = {
        "output_growth": round(output_growth, 6),
        "churn_ratio": round(churn_ratio, 6),
        "output_growth_budget": OUTPUT_TOKEN_GROWTH_MAX,
        "churn_ratio_budget": DIFF_CHURN_RATIO_MAX,
    }

    over_output = output_growth > OUTPUT_TOKEN_GROWTH_MAX
    over_churn = churn_ratio > DIFF_CHURN_RATIO_MAX
    if not (over_output or over_churn):
        return ChurnVerdict(True, ALLOW, str(candidate["model_id"]), baseline_id, ["within budget"], metrics)

    if _quality_case_holds(candidate, baseline):
        return ChurnVerdict(
            True, ALLOW, str(candidate["model_id"]), baseline_id,
            ["over budget but same-task quality comparison shows non-regression"], metrics,
        )

    reasons = []
    if over_output:
        reasons.append(f"output-token growth {output_growth:.1%} exceeds budget {OUTPUT_TOKEN_GROWTH_MAX:.0%} without quality case")
    if over_churn:
        reasons.append(f"diff churn {churn_ratio:.2f}x exceeds budget {DIFF_CHURN_RATIO_MAX:.1f}x without quality case")
    return ChurnVerdict(False, BLOCK, str(candidate["model_id"]), baseline_id, reasons, metrics)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Token-churn regression gate for model bumps (#1662)")
    parser.add_argument("--ledger", required=True, help="path to model_churn_baseline.json")
    parser.add_argument("--candidate", required=True, help="path to candidate evaluation artifact JSON ('-' for stdin)")
    args = parser.parse_args(argv)

    try:
        ledger = load_ledger(args.ledger)
    except (OSError, ValueError) as exc:
        print(f"BLOCK (config error): ledger unreadable/invalid: {exc}", file=sys.stderr)
        return 3

    try:
        if args.candidate == "-":
            candidate = json.load(sys.stdin)
        else:
            with open(args.candidate, "r", encoding="utf-8") as f:
                candidate = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"BLOCK (config error): candidate artifact unreadable/invalid: {exc}", file=sys.stderr)
        return 3

    verdict = evaluate_bump(candidate, ledger)
    print(json.dumps({
        "verdict": verdict.kind,
        "model_id": verdict.model_id,
        "baseline_id": verdict.baseline_id,
        "reasons": verdict.reasons,
        "metrics": verdict.metrics,
    }, sort_keys=True))
    return 0 if verdict.allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
