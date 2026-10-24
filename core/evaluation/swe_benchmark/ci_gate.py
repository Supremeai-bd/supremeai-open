"""core/evaluation/swe_benchmark/ci_gate.py — Regression gate (Way 15, fail-closed).

বাংলা: বেসলাইন metrics-এর সাথে তুলনা করে CI-তে গেট হিসেবে কাজ করে। যেকোনো
মেট্রিক রিগ্রেশন (নিচে পিন করা floor-এর নিচে) হলে exit 1 — কখনো exit 0 দিয়ে
রিগ্রেশন ঢাকা যাবে না।

Usage:
    # Baseline (human-reviewed, pinned in baseline.json):
    python -m core.evaluation.swe_benchmark.ci_gate --detector gateway.prompt_injection \
        --baseline core/evaluation/swe_benchmark/baseline.json

    # Print current metrics only (no gate):
    python -m core.evaluation.swe_benchmark.ci_gate --print-only

Baseline format (baseline.json):
    {
      "corpus_fingerprint": "3d9755...",   # must match the loaded corpus
      "min_accuracy": 0.85,
      "min_precision": 0.8,
      "min_recall": 0.8,
      "min_specificity": 0.8,
      "min_f1": 0.8
    }

Exit codes: 0 = pass, 1 = regression/mismatch, 2 = harness error.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

from .runner import corpus_fingerprint, load_corpus, run_benchmark

BASELINE_PATH = Path(__file__).resolve().parent / "baseline.json"

# Seed floors — deliberately conservative for the 14-case seed corpus.
# Tighten as the corpus grows toward the 216-case target (plan Way 15).
DEFAULT_FLOORS = {
    "min_accuracy": 0.85,
    "min_precision": 0.80,
    "min_recall": 0.80,
    "min_specificity": 0.80,
    "min_f1": 0.80,
}


def _resolve_detector(dotted: str):
    """Import 'module.attr' and return the callable (e.g. gateway.prompt_injection.detect_injection)."""
    mod_name, _, attr = dotted.rpartition(".")
    if not mod_name:
        raise ValueError(f"--detector expects 'module.attr', got {dotted!r}")
    module = importlib.import_module(mod_name)
    fn = getattr(module, attr)
    if not callable(fn):
        raise TypeError(f"{dotted} is not callable")
    return fn


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SWE benchmark regression gate")
    parser.add_argument(
        "--detector",
        default="gateway.prompt_injection.detect_injection",
        help="dotted callable: module.attr(text) -> detection result",
    )
    parser.add_argument("--baseline", default=str(BASELINE_PATH))
    parser.add_argument("--print-only", action="store_true", help="report metrics, exit 0")
    args = parser.parse_args(argv)

    try:
        cases, _ = load_corpus()
    except ValueError as exc:
        print(f"GATE ERROR (corpus): {exc}", file=sys.stderr)
        return 2

    try:
        detector = _resolve_detector(args.detector)
        report = run_benchmark(detector, cases)
    except Exception as exc:  # detector import/run failure = harness error
        print(f"GATE ERROR (detector): {exc}", file=sys.stderr)
        return 2

    metrics = report.to_dict()
    print(json.dumps(metrics, indent=2, sort_keys=True))
    if args.print_only:
        return 0

    baseline_path = Path(args.baseline)
    floors = dict(DEFAULT_FLOORS)
    if baseline_path.exists():
        try:
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            for k in floors:
                if k in baseline:
                    floors[k] = float(baseline[k])
        except Exception as exc:
            print(f"GATE ERROR (baseline unreadable, using defaults): {exc}", file=sys.stderr)
            return 2

    # Frozen-corpus discipline: fingerprint drift = corpus changed = fail-closed.
    pinned_fp = None
    if baseline_path.exists():
        try:
            pinned_fp = json.loads(baseline_path.read_text(encoding="utf-8")).get(
                "corpus_fingerprint"
            )
        except Exception:
            pinned_fp = None
    if pinned_fp and pinned_fp != metrics["corpus_fingerprint"]:
        print(
            "GATE FAIL: corpus fingerprint changed "
            f"({pinned_fp[:12]}… → {metrics['corpus_fingerprint'][:12]}…). "
            "Frozen cases must not be edited; append a NEW versioned manifest instead.",
            file=sys.stderr,
        )
        return 1

    failures = []
    metric_map = {
        "min_accuracy": metrics["accuracy"],
        "min_precision": metrics["precision"],
        "min_recall": metrics["recall"],
        "min_specificity": metrics["specificity"],
        "min_f1": metrics["f1"],
    }
    for floor_name, value in metric_map.items():
        floor = floors[floor_name]
        if value < floor:
            failures.append(f"{floor_name.replace('min_', '')}={value:.4f} < {floor:.4f}")
    if report.match_violations:
        failures.extend(f"rule-mismatch: {v}" for v in report.match_violations)

    if failures:
        print("GATE FAIL: " + "; ".join(failures), file=sys.stderr)
        return 1
    print("GATE PASS: all floors met, corpus fingerprint verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
