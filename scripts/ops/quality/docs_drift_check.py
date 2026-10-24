#!/usr/bin/env python3
"""বাংলা মন্তব্য: SupremeAI Docs-Drift Checker (docs_drift_check.py)

উদ্দেশ্য: STATUS.md / task_progress.md / REMAINING_TASKS.md / FAILING_TESTS.md-এর
মতো tracking markdown ফাইলগুলো বারবার stale হয়ে যায় (একাধিক audit সেশনে এই সমস্যা
পাওয়া গেছে — যেমন task_progress.md ৩৮% লিখে রেখেছিল যখন actual coverage গেট ছিল
৪৫%, বা REMAINING_TASKS.md "ALL PHASES COMPLETED" বলছিল যখন কাজ চলমান ছিল)।

এই স্ক্রিপ্ট কয়েকটা সহজ, যাচাইযোগ্য claim স্বয়ংক্রিয়ভাবে actual repo state-এর সাথে
মিলিয়ে দেখে:
  - docs-এ উল্লেখিত coverage %  vs  CI workflow-এর প্রকৃত cov-fail-under মান
  - "ALL PHASES/TASKS COMPLETED"-জাতীয় claim vs repo-তে এখনো TODO/FIXME থাকা কিনা
  - docs-এ referenced ফাইল-পাথ আসলেই এখনো বিদ্যমান কিনা (moved/renamed ফাইলের কারণে
    stale path reference একাধিকবার পাওয়া গেছে)

শুধু stdlib, network/dependency ছাড়া (Zero Cost)। এটা কোনোকিছু auto-fix করে না —
শুধু মানুষকে জানায় কোন doc কে refresh করা দরকার।

ব্যবহার: python3 scripts/quality/docs_drift_check.py [--path .]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TRACKING_DOCS = [
    "STATUS.md", "TODO.md", "CHECKPOINT.md", "task_progress.md",
    "REMAINING_TASKS.md", "FAILING_TESTS.md", "implementation_plan.md",
]

COMPLETION_CLAIM_RE = re.compile(r"ALL (PHASES|TASKS) COMPLETED", re.IGNORECASE)
COVERAGE_CLAIM_RE = re.compile(r"coverage[^0-9]{0,20}(\d{1,3})\s*%", re.IGNORECASE)
FILE_PATH_RE = re.compile(r'`([\w./\\-]+\.(?:py|ts|tsx|js|yml|yaml))`')


def get_real_coverage_gate(root: Path) -> int | None:
    wf_dir = root / ".github" / "workflows"
    if not wf_dir.exists():
        return None
    for wf in wf_dir.glob("*.yml"):
        text = wf.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"MIN_BACKEND_COVERAGE:\s*(\d+)", text)
        if m:
            return int(m.group(1))
    return None


def count_todos(root: Path) -> int:
    count = 0
    for p in (root / "backend").rglob("*.py") if (root / "backend").exists() else []:
        if any(part in {"node_modules", ".git", "__pycache__", "venv"} for part in p.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except UnicodeDecodeError:
            continue
        count += len(re.findall(r"\b(TODO|FIXME|XXX)\b", text))
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="SupremeAI docs-drift checker")
    parser.add_argument("--path", default=".", help="Repo root")
    args = parser.parse_args()
    root = Path(args.path).resolve()

    issues: list[str] = []
    real_gate = get_real_coverage_gate(root)
    real_todos = count_todos(root)

    for name in TRACKING_DOCS:
        doc = root / name
        if not doc.exists():
            continue
        text = doc.read_text(encoding="utf-8", errors="replace")

        if COMPLETION_CLAIM_RE.search(text) and real_todos > 0:
            issues.append(
                f"{name}: claims 'ALL PHASES/TASKS COMPLETED' but {real_todos} TODO/FIXME/XXX "
                f"markers still exist under backend/ — likely stale."
            )

        cov_matches = COVERAGE_CLAIM_RE.findall(text)
        if cov_matches and real_gate is not None:
            for claimed in cov_matches:
                if abs(int(claimed) - real_gate) > 3:
                    issues.append(
                        f"{name}: claims coverage ~{claimed}% but CI's actual "
                        f"MIN_BACKEND_COVERAGE is {real_gate}% — likely stale."
                    )

        for ref in FILE_PATH_RE.findall(text):
            ref_path = root / ref
            if not ref_path.exists():
                issues.append(f"{name}: references '{ref}' which no longer exists in the repo — stale path.")

    print("=" * 70)
    print("SupremeAI Docs-Drift Check")
    print("=" * 70)
    if not issues:
        print("✅ No obvious drift detected in tracked markdown docs.")
        return 0
    for i in issues:
        print(f"  ⚠️  {i}")
    print(f"\n{len(issues)} potential drift issue(s) found. This check is informational — "
          f"review and refresh docs manually (exit 0, never blocks CI).")
    return 0  # informational only, never fails the build


if __name__ == "__main__":
    sys.exit(main())
