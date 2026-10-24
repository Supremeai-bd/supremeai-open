#!/usr/bin/env python3
"""
PR Helper — Fixability Scorer (Phase 3 of Intelligent Decision Engine)
=======================================================================
প্রতিটি new failure-এর জন্য fixability score (0-100) গণনা করে।
Score >= 70 → auto-fix attempt eligible
Score < 70 → flag for human review

Combines:
  - Layer 1: failure_type beneficial_probability
  - Layer 2: semantic delta (expected vs actual)
  - Layer 3: PR intention match
  - Layer 4: test file in PR diff

Usage:
  python fixability_scorer.py --delta delta.json --intention intention.json \\
    --changed-files "backend/tests/test_x.py,backend/core/y.py" \\
    --pr-title "fix(core): graceful degradation"

GitHub Actions outputs (GITHUB_OUTPUT):
  all_fixable = true|false
  fixable_count = N
  genuine_regression_count = M
  min_confidence = 0.0-1.0
  recommendations = JSON array of per-failure recommendations
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

AUTO_MERGE_THRESHOLD = 70  # score >= 70 → auto-fix eligible
HUMAN_REVIEW_THRESHOLD = 40  # score 40-69 → human review; < 40 → block


def _extract_expected_actual(snippet: str, message: str) -> tuple[str, str]:
    """Extract what the test expected vs what actually happened from the failure message.

    বাংলা: AssertionError: assert X == Y → expected=X, actual=Y
    """
    combined = f"{message}\n{snippet}"

    # Pattern: assert X == Y
    m = re.search(r"assert\s+(\S+)\s*==\s*(\S+)", combined)
    if m:
        return m.group(1).strip("'\""), m.group(2).strip("'\"")

    # Pattern: expected X, got Y
    m = re.search(r"expected\s+['\"]?(.+?)['\"]?\s*,?\s*(?:but\s+)?got\s+['\"]?(.+?)['\"]", combined, re.IGNORECASE)
    if m:
        return m.group(1), m.group(2)

    # Pattern: KeyError: 'X'
    m = re.search(r"KeyError:\s*['\"](.+?)['\"]", combined)
    if m:
        return f"key '{m.group(1)}'", "key missing"

    return "", ""


def _check_intention_match(failure: dict, intention: dict) -> bool:
    """Check if the PR intention aligns with the failure domain.

    বাংলা: যদি PR intention = "change_secret_handling" এবং failure
    secret_vault বা config_secrets সম্পর্কিত test → intention match।
    """
    intent = intention.get("intention", "unknown")
    test_class = failure.get("class", "").lower()
    test_name = failure.get("test", "").lower()
    failure_snippet = failure.get("snippet", "").lower() + failure.get("message", "").lower()

    if intent == "change_secret_handling":
        return any(kw in test_class + test_name + failure_snippet
                    for kw in ["secret", "vault", "config_secret", "credential", "neo4j", "database_url"])
    elif intent == "change_security_behavior":
        return any(kw in test_class + test_name + failure_snippet
                    for kw in ["middleware", "security", "origin", "rate_limit", "idempotency", "api_key"])
    elif intent == "refactor":
        return True  # refactors often cause import/assertion mismatches
    elif intent == "add_feature":
        return False  # new feature shouldn't break existing tests
    elif intent == "fix_bug":
        return True  # bug fix might intentionally change behavior
    return False


def score_failure(
    failure: dict,
    intention: dict,
    changed_files: list[str],
    pr_title: str = "",
) -> dict:
    """Calculate fixability score for a single failure.

    Returns:
        {
            "test_id": str,
            "failure_type": str,
            "score": int (0-100),
            "confidence": float (0.0-1.0),
            "verdict": "auto_fix" | "human_review" | "block",
            "expected": str,
            "actual": str,
            "intention_match": bool,
            "rationale": str,
        }
    """
    score = 0
    rationales = []

    # Layer 1: failure_type beneficial probability
    ftype = failure.get("failure_type", "unknown")
    beneficial_prob = failure.get("beneficial_probability", 0.40)
    type_score = int(beneficial_prob * 40)  # max 40 points from type
    score += type_score
    rationales.append(f"type={ftype} → +{type_score}")

    # Layer 2: semantic delta (expected vs actual extracted)
    expected, actual = _extract_expected_actual(
        failure.get("snippet", ""), failure.get("message", "")
    )
    if expected and actual:
        score += 20  # clear expected/actual → easier to auto-fix
        rationales.append(f"expected={expected} vs actual={actual} → +20")

    # Layer 3: intention match
    intention_match = _check_intention_match(failure, intention)
    if intention_match:
        score += 25  # PR intended to change this domain
        rationales.append(f"intention_match={intention.get('intention')} → +25")

    # Layer 4: test file in changed files
    test_class = failure.get("class", "")
    test_file_candidates = []
    parts = [p for p in test_class.split(".") if p]
    for size in range(len(parts), 0, -1):
        test_file_candidates.append(f"backend/tests/{'/'.join(parts[:size])}.py")
        test_file_candidates.append(f"tests/{'/'.join(parts[:size])}.py")

    test_in_diff = any(cand in changed_files for cand in test_file_candidates)
    if test_in_diff:
        score += 15  # test file already being modified → easy fix
        rationales.append("test_file_in_diff → +15")

    # Penalty: syntax error is almost never beneficial
    if ftype == "syntax_error":
        score = min(score, 10)
        rationales.append("syntax_error → capped at 10")

    score = max(0, min(100, score))

    # Determine verdict
    if score >= AUTO_MERGE_THRESHOLD:
        verdict = "auto_fix"
        confidence = min(1.0, score / 100 + 0.1)
    elif score >= HUMAN_REVIEW_THRESHOLD:
        verdict = "human_review"
        confidence = score / 100 * 0.7
    else:
        verdict = "block"
        confidence = score / 100 * 0.3

    return {
        "test_id": failure.get("id", ""),
        "failure_type": ftype,
        "score": score,
        "confidence": round(confidence, 2),
        "verdict": verdict,
        "expected": expected,
        "actual": actual,
        "intention_match": intention_match,
        "rationale": "; ".join(rationales),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PR Helper: Fixability Scorer")
    parser.add_argument("--delta", required=True, help="delta.json from Step 3")
    parser.add_argument("--intention", default="", help="intention.json from Phase 2")
    parser.add_argument("--changed-files", default="", help="Comma-separated changed file paths")
    parser.add_argument("--pr-title", default="", help="PR title")
    parser.add_argument("--output-json", default="", help="Output JSON path")
    args = parser.parse_args()

    delta = json.loads(Path(args.delta).read_text(encoding="utf-8"))
    new_failures = delta.get("new_failures", [])

    intention = {}
    if args.intention and Path(args.intention).exists():
        intention = json.loads(Path(args.intention).read_text(encoding="utf-8"))

    changed_files = [f.strip() for f in args.changed_files.split(",") if f.strip()]

    recommendations = []
    for failure in new_failures:
        rec = score_failure(failure, intention, changed_files, args.pr_title)
        recommendations.append(rec)

    all_fixable = all(r["verdict"] == "auto_fix" for r in recommendations) if recommendations else True
    fixable_count = sum(1 for r in recommendations if r["verdict"] == "auto_fix")
    genuine_regression_count = sum(1 for r in recommendations if r["verdict"] == "block")
    human_review_count = sum(1 for r in recommendations if r["verdict"] == "human_review")
    min_confidence = min((r["confidence"] for r in recommendations), default=1.0)

    result = {
        "all_fixable": all_fixable,
        "fixable_count": fixable_count,
        "genuine_regression_count": genuine_regression_count,
        "human_review_count": human_review_count,
        "min_confidence": round(min_confidence, 2),
        "recommendations": recommendations,
    }

    if args.output_json:
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_json).write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    print(f"Fixability: {fixable_count} fixable, {human_review_count} human_review, "
          f"{genuine_regression_count} block | all_fixable={all_fixable} | min_conf={min_confidence}")
    for rec in recommendations:
        print(f"  [{rec['verdict']:12s}] {rec['test_id'][:50]} → score={rec['score']} conf={rec['confidence']}")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"all_fixable={str(all_fixable).lower()}\n")
            f.write(f"fixable_count={fixable_count}\n")
            f.write(f"genuine_regression_count={genuine_regression_count}\n")
            f.write(f"human_review_count={human_review_count}\n")
            f.write(f"min_confidence={round(min_confidence, 2)}\n")
            f.write(f"recommendations={json.dumps(recommendations)}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
