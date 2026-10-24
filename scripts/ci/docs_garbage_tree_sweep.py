#!/usr/bin/env python3
"""docs_garbage_tree_sweep — tree-level Zero-Garbage Docs check (#4176).

# বাংলা মন্তব্য: PR-path gate (`constitution.gates all` → docs_garbage) শুধু
# PR-এর changed-files দেখে — main-এ সরাসরি push হলে কোনো gate-ই চলে না
# (প্রমাণ: 2026-10-06-এ docs/FRONTEND_DASHBOARD_MASTER_PLAN{,_V2}.md দুটি
# সরাসরি main-push ছিল — 9e4d9df/889da16, কোনো PR নেই; gate সুযোগই পায়নি)।
# এই sweep পুরো docs/ tree দেখে: allowlist-বাইরের ফাইল যারা baseline-এ নেই —
# তাদের BLOCK করে। Baseline-এ থাকা পরিচিত ফাইল grandfathered (তাদের অবস্থান
# নিয়ে সিদ্ধান্ত liability-audit issue-তে); baseline regen কেবল অনুমোদিত
# PR-প্রবাহে (review-সহ) হবে — যাতে guard নিজেই বাইপাস-পথ না হয়।

Usage:
  python3 scripts/ci/docs_garbage_tree_sweep.py            # check (exit 2 on new offenders)
  python3 scripts/ci/docs_garbage_tree_sweep.py --list     # offenders দেখাও, exit 0
  python3 scripts/ci/docs_garbage_tree_sweep.py --regen    # baseline হালনাগাদ (approved PR-এই)
"""
from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = REPO_ROOT / ".github" / "constitution" / "rules.yml"
BASELINE_PATH = REPO_ROOT / "docs" / "generated" / "docs_garbage_baseline.txt"


def load_patterns() -> list[str]:
    """rules.yml → docs_garbage_policy.allowed_patterns (PR-gate-এর সঙ্গে একই SSOT)।"""
    import yaml  # lazy import — CI step-এ PyYAML আছে

    data = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8")) or {}
    return list((data.get("docs_garbage_policy") or {}).get("allowed_patterns") or [])


def matches_any(path: str, patterns: list[str]) -> bool:
    """fnmatch + trailing '/**' directory-prefix semantics (gates.py-র সঙ্গে সামঞ্জস্যপূর্ণ)।"""
    for pat in patterns:
        if pat.endswith("/**"):
            if path.startswith(pat[:-2]):  # 'docs/archive/**' → 'docs/archive/'
                return True
        elif fnmatch.fnmatch(path, pat):
            return True
    return False


def tracked_docs_md() -> list[str]:
    """docs/-এর সব tracked .md (untracked garbage এখানে আসবে না — commit-এর পরেই ধরা পড়বে)।"""
    tracked = subprocess.run(
        ["git", "ls-files", "--", "docs/"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return sorted(p for p in tracked if p.endswith(".md"))


def read_baseline() -> set[str]:
    if not BASELINE_PATH.exists():
        print(f"::error::baseline missing: {BASELINE_PATH.relative_to(REPO_ROOT)} — approved PR-এ `--regen` চালাও")
        sys.exit(2)
    return {l.strip() for l in BASELINE_PATH.read_text(encoding="utf-8").splitlines() if l.strip()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="offenders দেখাও, exit 0")
    ap.add_argument("--regen", action="store_true", help="baseline হালনাগাদ (approved PR-এই)")
    args = ap.parse_args()

    patterns = load_patterns()
    if not patterns:
        print("::error::docs_garbage_policy.allowed_patterns খালি — rules.yml যাচাই করো")
        return 2

    offenders_now = [p for p in tracked_docs_md() if not matches_any(p, patterns)]

    if args.regen:
        baseline = read_baseline() if BASELINE_PATH.exists() else set()
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text("\n".join(offenders_now) + ("\n" if offenders_now else ""), encoding="utf-8")
        removed, added = baseline - set(offenders_now), set(offenders_now) - baseline
        print(f"[REGEN] baseline হালনাগাদ: {len(offenders_now)} entry | removed={sorted(removed)} added={sorted(added)}")
        print("# বাংলা মন্তব্য: regen commit-টি অবশ্যই approved PR-এ যাবে — diff review ছাড়া baseline বদলানো বাইপাস-পথ।")
        return 0

    baseline = read_baseline()

    new_offenders = sorted(set(offenders_now) - baseline)
    stale = sorted(baseline - set(offenders_now))

    if args.list:
        print(f"non-allowlisted docs/*.md (tree): {len(offenders_now)}")
        for p in offenders_now:
            print(" -", p)
        return 0

    for p in stale:
        print(f"::notice::stale baseline entry (ফাইল আর নেই — regen-এ বাদ যাবে): {p}")

    if new_offenders:
        print(f"::error::Docs Garbage Tree Sweep: {len(new_offenders)}টি নতুন non-allowlisted docs/*.md (main-এ সরাসরি push-এর সন্দেহ) —")
        for p in new_offenders:
            print(f"   - {p}")
        print("# বাংলা: ফাইলটি docs/archive/ সরাও, অথবা rules.yml allowlist-এ (approved PR-এ) যোগ করো, অথবা liability-audit-এ সিদ্ধান্ত নাও।")
        return 2

    print(f"[PASSED] Docs Garbage Tree Sweep: {len(offenders_now)} grandfathered, 0 new non-allowlisted docs/*.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
