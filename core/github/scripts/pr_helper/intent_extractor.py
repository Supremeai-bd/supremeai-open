#!/usr/bin/env python3
"""
PR Helper — Intent Extractor (Phase 2 of Intelligent Decision Engine)
=====================================================================
PR-এর title, body, commit messages, এবং changed file paths থেকে
intention extract করে। এটা নির্ধারণ করে PR কী change করতে চাইলো।

Output: pr_intention field (e.g., "change_secret_handling", "add_feature")

Usage:
  python intent_extractor.py --pr-title "fix(core): DATABASE_URL graceful degradation" \\
    --pr-body "..." --changed-files "backend/core/security/secret_vault.py,backend/api/..."

GitHub Actions outputs (GITHUB_OUTPUT):
  pr_intention = change_secret_handling | add_feature | refactor | fix_bug | ...
  intention_confidence = 0.0-1.0
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


INTENT_PATTERNS = {
    "change_secret_handling": [
        r"secret_vault\.py",
        r"config_secrets\.py",
        r"secret.*rotat",
        r"credential",
        r"fail.closed|fail.open|graceful.degrad",
        r"NEO4J|DATABASE_URL|SUPABASE",
    ],
    "change_security_behavior": [
        r"middleware\.py|security_pipeline\.py",
        r"origin.*valid|rate.*limit|api.*key.*limiter",
        r"idempotency|replay.*protect",
        r"auth.*middleware|session.*manage",
    ],
    "add_feature": [
        r"^feat\(",
        r"add.*endpoint|add.*route|add.*api",
        r"new.*module|new.*service",
        r"MESH-|mesh.*task",
    ],
    "fix_bug": [
        r"^fix\(",
        r"bug.*fix|broken|crash|error.*fix",
        r"regression|revert",
    ],
    "refactor": [
        r"^refactor\(",
        r"cleanup|reorganize|restructure",
        r"move.*module|rename.*class|update.*import",
    ],
    "change_test_contract": [
        r"test.*contract|test.*update|test.*fix",
        r"assertion.*update|test.*expect",
    ],
    "docs_only": [
        r"^docs\(",
        r"README|CHANGELOG|\.md$",
    ],
    "ci_improvement": [
        r"^ci\(|^chore\(ci",
        r"workflow|github.*action",
        r"lint.*gate|ruff|mypy",
    ],
}

INTENT_LABELS = {
    "change_secret_handling": "Changing how secrets/vault behaves",
    "change_security_behavior": "Changing security middleware behavior",
    "add_feature": "Adding new feature/endpoint",
    "fix_bug": "Fixing a bug",
    "refactor": "Refactoring/restructuring code",
    "change_test_contract": "Changing test expectations",
    "docs_only": "Documentation only",
    "ci_improvement": "CI/CD improvement",
    "unknown": "Cannot determine intention",
}


def extract_intention(
    pr_title: str = "",
    pr_body: str = "",
    changed_files: str = "",
    commit_messages: str = "",
) -> dict:
    """Extract PR intention from title, body, changed files, and commit messages.

    Returns:
        {
            "intention": str (e.g., "change_secret_handling"),
            "confidence": float (0.0-1.0),
            "matched_patterns": list[str],
            "label": str (human-readable),
        }
    """
    combined_text = f"{pr_title}\n{pr_body}\n{commit_messages}\n{changed_files}"
    changed_paths = [f.strip() for f in changed_files.split(",") if f.strip()]

    scores: dict[str, int] = {}
    matched: dict[str, list[str]] = {}

    for intent, patterns in INTENT_PATTERNS.items():
        count = 0
        for pat in patterns:
            if re.search(pat, combined_text, re.IGNORECASE):
                count += 1
        if count > 0:
            scores[intent] = count
            matched[intent] = [
                p for p in patterns if re.search(p, combined_text, re.IGNORECASE)
            ]

    if not scores:
        # Check if files are docs-only
        if changed_paths and all(f.endswith(".md") for f in changed_paths):
            return {
                "intention": "docs_only",
                "confidence": 0.90,
                "matched_patterns": ["all files are .md"],
                "label": INTENT_LABELS["docs_only"],
            }
        return {
            "intention": "unknown",
            "confidence": 0.0,
            "matched_patterns": [],
            "label": INTENT_LABELS["unknown"],
        }

    # Pick the intent with highest match count
    best_intent = max(scores, key=scores.get)
    best_count = scores[best_intent]
    total_matches = sum(scores.values())
    confidence = min(1.0, best_count / max(1, total_matches))

    # Boost confidence if PR title prefix matches (feat/, fix/, refactor/)
    title_prefix_match = False
    if best_intent == "add_feature" and re.match(r"^feat\(", pr_title):
        confidence = min(1.0, confidence + 0.2)
        title_prefix_match = True
    elif best_intent == "fix_bug" and re.match(r"^fix\(", pr_title):
        confidence = min(1.0, confidence + 0.2)
        title_prefix_match = True
    elif best_intent == "refactor" and re.match(r"^refactor\(", pr_title):
        confidence = min(1.0, confidence + 0.2)
        title_prefix_match = True

    return {
        "intention": best_intent,
        "confidence": round(confidence, 2),
        "matched_patterns": matched[best_intent],
        "label": INTENT_LABELS.get(best_intent, "Unknown"),
        "title_prefix_match": title_prefix_match,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PR Helper: Intent Extractor")
    parser.add_argument("--pr-title", default="", help="PR title")
    parser.add_argument("--pr-body", default="", help="PR body text")
    parser.add_argument("--changed-files", default="", help="Comma-separated changed file paths")
    parser.add_argument("--commit-messages", default="", help="Commit messages from the PR")
    parser.add_argument("--output-json", default="", help="Output JSON path")
    args = parser.parse_args()

    result = extract_intention(
        pr_title=args.pr_title,
        pr_body=args.pr_body,
        changed_files=args.changed_files,
        commit_messages=args.commit_messages,
    )

    if args.output_json:
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_json).write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    print(f"PR intention: {result['intention']} (confidence={result['confidence']})")
    print(f"  Label: {result['label']}")
    if result["matched_patterns"]:
        print(f"  Matched: {', '.join(result['matched_patterns'][:3])}")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"pr_intention={result['intention']}\n")
            f.write(f"intention_confidence={result['confidence']}\n")
            f.write(f"intention_label={result['label']}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
