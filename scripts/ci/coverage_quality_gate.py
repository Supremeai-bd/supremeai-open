#!/usr/bin/env python3
"""Coverage quality gate — evaluates coverage.json against tiered policy.

INTEGRITY FIX (final-test hardening-2, 2026-09-14):
The previous matcher compared policy globs like ``backend/core/llm/**``
against paths as they appear in coverage.json (``core/llm/...`` — relative
to the backend root, because pytest runs with ``--cov=core --cov=api ...``
inside ./backend). No path ever matched, both tiers accumulated ZERO files,
and the divide-by-zero guard reported a vacuous 100.00% "pass". The gate has
never enforced anything.

This version:
1. Normalises paths — every file is matched both bare and with the
   ``backend/`` prefix, and ``dir/**`` patterns match any depth below ``dir``.
2. Fails closed — a tier that matches ZERO files is a policy/coverage-scope
   drift (or a broken combine), not a perfect score.
3. Emits evidence — matched file/statement counts per tier plus the worst
   offenders (most missed lines), so CI logs show real numbers.
"""

import argparse
import fnmatch
import json
import sys
from pathlib import Path

import yaml
from loguru import logger

BACKEND_PREFIX = "backend/"


def _path_forms(file_path: str) -> list[str]:
    """Return the candidate spellings of a coverage.json path.

    coverage.json paths are relative to the backend root (e.g. ``core/llm/x.py``);
    policy globs may be written either bare or with a ``backend/`` prefix. Both
    spellings are tried so the gate is insensitive to the authoring choice.
    """
    forms = [file_path]
    if file_path.startswith(BACKEND_PREFIX):
        forms.append(file_path[len(BACKEND_PREFIX) :])
    else:
        forms.append(BACKEND_PREFIX + file_path)
    return forms


def matches_pattern(file_path: str, patterns: list) -> bool:
    """Check if file_path matches any policy glob.

    Supported pattern shapes:
    - ``dir/**``   → anything at or below ``dir`` (any depth)
    - ``dir/*``    → direct children of ``dir`` (fnmatch)
    - ``prefix*``  → fnmatch glob (e.g. ``services/memory*``)
    - exact path   → equality
    Both bare and ``backend/``-prefixed spellings of file_path are tried.
    """
    for base in _path_forms(file_path):
        for p in patterns:
            if p.endswith("/**"):
                d = p[:-3]
                if base == d or base.startswith(d + "/"):
                    return True
            elif fnmatch.fnmatch(base, p) or p in base:
                return True
    return False


def _tier_stats(files: dict, patterns: list) -> dict:
    """Aggregate statements/coverage for a tier and list matched files."""
    stmts = covered = 0
    matched = []
    for file_path, info in files.items():
        summary = info.get("summary", {})
        s = summary.get("num_statements", 0)
        c = summary.get("covered_lines", 0)
        if matches_pattern(file_path, patterns):
            stmts += s
            covered += c
            matched.append((file_path, s, c))
    return {"stmts": stmts, "covered": covered, "matched": matched}


def _evaluate_tier(name: str, stats: dict, threshold: float, failed: bool) -> bool:
    """Log evidence for one tier and return the updated failed flag."""
    matched = stats["matched"]
    if not matched:
        # Fail closed: zero files matched means the policy globs no longer
        # align with the coverage scope, or the combine produced garbage.
        logger.error(
            f"❌ {name} tier matched 0 files in coverage.json — policy/coverage "
            "scope drift (globs never match = vacuous pass is forbidden). "
            "Fix coverage_policy.yaml paths or the pytest --cov scope."
        )
        return True

    if stats["stmts"] == 0:
        logger.error(f"❌ {name} tier matched {len(matched)} files but 0 statements.")
        return True

    pct = stats["covered"] / stats["stmts"] * 100
    status_icon = "✅" if pct >= threshold else "❌"
    logger.info(
        f"{status_icon} {name} Modules Coverage: {pct:.2f}% "
        f"(Threshold: {threshold}%) — {len(matched)} files, "
        f"{stats['covered']}/{stats['stmts']} statements"
    )

    # Evidence: the 5 files with the most missed lines, so every CI run
    # shows where the next tests should go.
    worst = sorted(matched, key=lambda t: t[1] - t[2], reverse=True)[:5]
    for fp, s, c in worst:
        missed = s - c
        if missed > 0:
            logger.info(f"   · {fp}: {c}/{s} covered ({missed} missed)")

    if pct < threshold:
        logger.error(
            f"❌ {name} coverage {pct:.2f}% is below {threshold}% — "
            "add tests for the worst offenders listed above."
        )
        return True
    return failed


def main():
    parser = argparse.ArgumentParser(description="Evaluate coverage against policy thresholds.")
    parser.add_argument("cov_file", help="Path to coverage.json")
    parser.add_argument("policy_file", help="Path to coverage_policy.yaml")
    parser.add_argument(
        "--tiers",
        default="overall,critical,important",
        help="Comma-separated list of tiers to evaluate (e.g., 'critical,important')",
    )
    args = parser.parse_args()

    active_tiers = [t.strip().lower() for t in args.tiers.split(",") if t.strip()]

    try:
        with open(args.policy_file) as f:
            policy = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load policy.yaml: {e}")
        sys.exit(1)

    try:
        with open(args.cov_file) as f:
            coverage_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load coverage JSON: {e}")
        sys.exit(1)

    thresholds = policy.get("thresholds", {})
    critical_patterns = policy.get("critical", [])
    important_patterns = policy.get("important", [])

    files = coverage_data.get("files", {})
    if not files:
        logger.error("❌ coverage.json contains no file entries — combine failed or wrong file.")
        sys.exit(1)

    overall_coverage = coverage_data.get("totals", {}).get("percent_covered", 0.0)

    failed = False

    logger.info("=========================================")
    logger.info("   SUPREMEAI MULTI-LAYER COVERAGE GATE   ")
    logger.info(f"   Active Tiers: {', '.join(active_tiers)}")
    logger.info("=========================================")

    # 1. Overall
    if "overall" in active_tiers:
        overall_pr_thresh = thresholds.get("overall", {}).get("pr", 30)
        logger.info(f"Overall Coverage: {overall_coverage:.2f}% (Threshold: {overall_pr_thresh}%)")
        if overall_coverage < overall_pr_thresh:
            logger.error(
                f"❌ Overall coverage {overall_coverage:.2f}% is below {overall_pr_thresh}%"
            )
            failed = True
        else:
            logger.info("✅ Overall coverage passed.")

    # 2. Critical
    if "critical" in active_tiers:
        critical_pr_thresh = thresholds.get("critical", {}).get("pr", 80)
        critical_stats = _tier_stats(files, critical_patterns)
        failed = _evaluate_tier("Critical", critical_stats, critical_pr_thresh, failed)

    # 3. Important
    if "important" in active_tiers:
        important_pr_thresh = thresholds.get("important", {}).get("pr", 60)
        important_stats = _tier_stats(files, important_patterns)
        failed = _evaluate_tier("Important", important_stats, important_pr_thresh, failed)

    logger.info("=========================================")

    if failed:
        logger.error("Quality Gate FAILED. Please add tests for your changes.")
        sys.exit(1)
    else:
        logger.info("Quality Gate PASSED. Great job!")
        sys.exit(0)


if __name__ == "__main__":
    main()
