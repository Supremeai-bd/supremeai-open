#!/usr/bin/env python3
"""
PR Helper — Step 3: Test Failure & Delta Analysis
=================================================
BASE ও HEAD দুই রেফারেন্সের JUnit XML তুলনা করে তিনটি বাকেটে ভাগ করে:

  - new_failures  → এই PR-এ নতুনভাবে ভাঙা টেস্ট (regression) → Branch B (Step 4)
  - pre_existing  → BASE-এও ভাঙা ছিল (PR-এর দোষ নয়) → সহনীয় (tolerated)
  - fixed         → BASE-এ ভাঙা ছিল, এই PR ঠিক করেছে → pure improvement signal

State-based Locking Lifecycle-এর সিদ্ধান্ত ইঞ্জিন এই classification-এর উপর চলে:
  new_failures == 0  → Branch A: Pure Improvement → approve / auto-merge (Step 5)
  new_failures > 0   → Branch B: Hunk-Level Isolation → cherry-pick বা issue (Step 4)

Stdlib-only (xml.etree, argparse, json) — কোনো extra dependency নেই।

Usage:
  python delta_analysis.py \
    --base-junit junit-base.xml \
    --head-junit junit-head.xml \
    --output-json delta.json \
    --summary-out summary.md

GitHub Actions outputs (GITHUB_OUTPUT):
  classification = pure-improvement | regression
  new_count, pre_existing_count, fixed_count, head_total, base_total
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _parse_junit(path: str | None) -> dict:
    """Parse a JUnit XML file → {failures: {id: detail}, totals: {...}}.

    বাংলা মন্তব্য: junit-এ <failure> এবং <error> দুটোই fail গণ্য হবে —
    error মানে collection/import error বা crash, যা regression-এর সবচেয়ে
    বড় সংকেত। ফাইল না থাকলে empty result (incomplete=True) দেয়।
    """
    result: dict = {
        "file": path,
        "present": False,
        "incomplete": True,
        "failures": {},
        "tests": 0,
        "errors": 0,
        "skipped": 0,
    }
    if not path or not Path(path).exists():
        return result
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        print(f"::warning::JUnit XML parse failed for {path}: {exc}", file=sys.stderr)
        return result

    result["present"] = True
    result["incomplete"] = False
    for suite in root.iter("testsuite"):
        result["tests"] += int(suite.get("tests", 0) or 0)
        result["errors"] += int(suite.get("errors", 0) or 0)
        result["skipped"] += int(suite.get("skipped", 0) or 0)
        for case in suite.iter("testcase"):
            failure_node = case.find("failure")
            error_node = case.find("error")
            node = None
            kind = None
            if failure_node is not None:
                node, kind = failure_node, "failure"
            elif error_node is not None:
                node, kind = error_node, "error"
            if node is None:
                continue
            classname = (case.get("classname") or "").strip()
            name = (case.get("name") or "").strip()
            fid = f"{classname}::{name}" if classname else name
            text = (node.text or "")[-1800:]
            result["failures"][fid] = {
                "id": fid,
                "class": classname,
                "test": name,
                "kind": kind,
                "message": (node.get("message") or "")[:300],
                "snippet": text,
            }
    return result

FAILURE_TYPE_PATTERNS = {
    "import_error": [
        r"ModuleNotFoundError:\s*No module named",
        r"ImportError:\s*cannot import name",
        r"ImportError:\s*No module named",
        r"AttributeError:\s*module '.*' has no attribute",
    ],
    "assertion_mismatch": [
        r"AssertionError:\s*assert .* ==",
        r"AssertionError:\s*assert .* !=",
        r"AssertionError:",
    ],
    "type_error": [
        r"TypeError:\s*",
        r"TypeError.*got an unexpected keyword argument",
        r"TypeError.*missing.*required.*argument",
    ],
    "key_error": [
        r"KeyError:\s*['\"]",
        r"IndexError:\s*list index out of range",
    ],
    "timeout": [
        r"TimeoutError",
        r"timed out",
        r"TimeoutExpired",
    ],
    "connection_error": [
        r"ConnectionRefusedError",
        r"ConnectionError",
        r"Connection refused",
        r"ECONNREFUSED",
        r"Failed to establish a connection",
    ],
    "syntax_error": [
        r"SyntaxError:",
        r"IndentationError:",
        r"TabError:",
    ],
}

FAILURE_TYPE_BENEFICIAL_PROBABILITY = {
    "import_error": 0.85,
    "assertion_mismatch": 0.50,
    "type_error": 0.80,
    "key_error": 0.75,
    "timeout": 0.30,
    "connection_error": 0.90,
    "syntax_error": 0.05,
    "unknown": 0.40,
}

FAILURE_TYPE_AUTO_FIX_STRATEGY = {
    "import_error": "update_test_import_path",
    "assertion_mismatch": "compare_expected_vs_actual_semantically",
    "type_error": "update_test_call_signature",
    "key_error": "update_test_data_access",
    "timeout": "retry_with_longer_timeout",
    "connection_error": "skip_as_env_issue",
    "syntax_error": None,
    "unknown": None,
}


def _classify_failure_type(snippet: str, message: str) -> str:
    """Classify a test failure into a taxonomy type based on the error snippet + message.

    বাংলা মন্তব্য: JUnit <failure> বা <error> এর text/message থেকে pattern match
    করে failure type নির্ধারণ করে। এটা পরবর্তী fixability scoring-এর ভিত্তি।
    """
    import re
    combined = f"{message}\n{snippet}"
    for ftype, patterns in FAILURE_TYPE_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, combined, re.IGNORECASE):
                return ftype
    return "unknown"


def _enrich_failure(failure: dict) -> dict:
    """Add failure_type, beneficial_probability, auto_fix_strategy to a failure dict."""
    ftype = _classify_failure_type(failure.get("snippet", ""), failure.get("message", ""))
    failure["failure_type"] = ftype
    failure["beneficial_probability"] = FAILURE_TYPE_BENEFICIAL_PROBABILITY.get(ftype, 0.40)
    failure["auto_fix_strategy"] = FAILURE_TYPE_AUTO_FIX_STRATEGY.get(ftype)
    return failure




def _md_escape(text: str) -> str:
    return text.replace("|", "\\|")


def build_summary(base: dict, head: dict, new: list, pre_existing: list, fixed: list) -> str:
    """Human-readable markdown summary (GitHub Step Summary + PR comment উভয়ে ব্যবহৃত)।"""
    classification = "pure-improvement" if not new else "regression"
    icon = "✅" if not new else "🛑"
    lines = [
        f"## {icon} PR Helper — Step 3: Failure Delta Analysis",
        "",
        f"**Classification:** `{classification}`",
        "",
        "| Metric | BASE | HEAD |",
        "|---|---|---|",
        f"| Tests executed | {base.get('tests', 0)} | {head.get('tests', 0)} |",
        f"| Failures | {len(base.get('failures', {}))} | {len(head.get('failures', {}))} |",
        "",
        "| Delta bucket | Count |",
        "|---|---|",
        f"| 🛑 New failures (regression) | {len(new)} |",
        f"| 🟡 Pre-existing (tolerated) | {len(pre_existing)} |",
        f"| 🟢 Fixed by this PR | {len(fixed)} |",
        "",
    ]
    if base.get("incomplete") or head.get("incomplete"):
        lines += [
            "> ⚠️ **Incomplete diagnostic data** — এক বা একাধিক JUnit artifact পাওয়া যায়নি।",
            "> Fail-closed: missing BASE data থাকলে HEAD failure গুলো new হিসেবেই গণ্য হয়েছে।",
            "",
        ]
    if new:
        lines += ["### 🛑 New failures (this PR breaks these)", ""]
        for item in new[:20]:
            lines.append(f"- `{_md_escape(item['id'])}` — {_md_escape(item['message'][:160])}")
        if len(new) > 20:
            lines.append(f"- …and {len(new) - 20} more")
        lines.append("")
    if fixed:
        lines += ["### 🟢 Fixed by this PR", ""]
        for item in fixed[:10]:
            lines.append(f"- `{_md_escape(item['id'])}`")
        if len(fixed) > 10:
            lines.append(f"- …and {len(fixed) - 10} more")
        lines.append("")
    if pre_existing:
        lines += ["### 🟡 Pre-existing failures (tolerated — not this PR's fault)", ""]
        for item in pre_existing[:10]:
            lines.append(f"- `{_md_escape(item['id'])}`")
        if len(pre_existing) > 10:
            lines.append(f"- …and {len(pre_existing) - 10} more")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="PR Helper Step 3: failure delta analysis")
    parser.add_argument("--base-junit", default="", help="JUnit XML from BASE diagnostic run")
    parser.add_argument("--head-junit", default="", help="JUnit XML from HEAD diagnostic run")
    parser.add_argument("--output-json", default="delta.json", help="delta JSON output path")
    parser.add_argument("--summary-out", default="", help="optional markdown summary output path")
    args = parser.parse_args()

    base = _parse_junit(args.base_junit)
    head = _parse_junit(args.head_junit)

    base_ids = set(base["failures"])
    head_ids = set(head["failures"])

    # বাংলা মন্তব্য: fail-closed — BASE data না থাকলে HEAD-এর সব failure-ই
    # new (regression) গণ্য হবে; অন্যথায় ভাঙা PR চুপচাপ পাস করে যেতে পারত।
    if base["incomplete"] and not head["incomplete"]:
        new_ids = head_ids
    else:
        new_ids = head_ids - base_ids
    pre_ids = head_ids & base_ids
    fixed_ids = base_ids - head_ids

    new = [_enrich_failure(head["failures"][i]) for i in sorted(new_ids)]
    pre_existing = [head["failures"][i] for i in sorted(pre_ids)]
    fixed = [base["failures"][i] for i in sorted(fixed_ids)]

    classification = "pure-improvement" if not new else "regression"

    delta = {
        "classification": classification,
        "new_failures": new,
        "pre_existing": pre_existing,
        "fixed": fixed,
        "head_tests": head.get("tests", 0),
        "base_tests": base.get("tests", 0),
        "head_incomplete": head["incomplete"],
        "base_incomplete": base["incomplete"],
    }
    out_path = Path(args.output_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(delta, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = build_summary(base, head, new, pre_existing, fixed)
    if args.summary_out:
        Path(args.summary_out).write_text(summary, encoding="utf-8")
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(summary + "\n")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"classification={classification}\n")
            f.write(f"new_count={len(new)}\n")
            f.write(f"pre_existing_count={len(pre_existing)}\n")
            f.write(f"fixed_count={len(fixed)}\n")
            f.write(f"head_total={head.get('tests', 0)}\n")
            f.write(f"base_total={base.get('tests', 0)}\n")
            # FIX: head_incomplete/base_incomplete MUST be written to GITHUB_OUTPUT
            # (not just to delta.json) — otherwise Step 5's condition
            # `needs.step3-delta.outputs.head_incomplete == 'false'` is never true,
            # and Step 5 (auto-merge) is always skipped for backend-touching PRs.
            # Python bool True/False → lowercase string 'true'/'false' for GHA comparison.
            f.write(f"head_incomplete={str(head['incomplete']).lower()}\n")
            f.write(f"base_incomplete={str(base['incomplete']).lower()}\n")

    print(f"PR Helper delta classification: {classification} "
          f"(new={len(new)}, pre_existing={len(pre_existing)}, fixed={len(fixed)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
