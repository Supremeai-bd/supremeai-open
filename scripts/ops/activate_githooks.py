#!/usr/bin/env python3
"""Bootstrap `core.hooksPath` for the shipped `.githooks/` enforcement suite.

R63/#2343 root-cause close-out — the bootstrap-gap fix.

বাংলা: রিপো যে `.githooks/` স্যুট শিপ করে (pre-commit, Board-Freshness
pre-push গেট #4177, post-commit) সেটি git-এর নিরাপত্তা-নীতির কারণে
`$GIT_DIR/hooks`-এ স্বয়ংক্রিয়ভাবে কখনো সক্রিয় হয় না — প্রতিটি ক্লোনে
`git config core.hooksPath .githooks` দরকার। রিপোর কোনো পৃষ্ঠই সেই
কনফিগ-লাইন বুটস্ট্র্যাপ করে না (R63 স্ক্যান: hooksPath/githooks শূন্য হিট),
ফলে Universal Invariant 1-এর স্থানীয়-স্তর প্রয়োগ প্রতিটি স্ট্যান্ডার্ড
ক্লোনে অন্ধকার। এই স্ক্রিপ্ট সেই ফাঁক বন্ধ করে:

- **ডিফল্ট / `--verify`** — report-only: কিছুই মিউটেট করে না, শুধু বর্তমান
  অবস্থা যাচাই করে (সক্রিয় হলে exit 0, না হলে exit 2)।
- **`--activate`** — explicit opt-in: `core.hooksPath` = `.githooks`
  (local scope) সেট করে, তারপর সেইম যাচাই চালায়। Idempotent — বারবার
  চালানো নিরাপদ।

যাচাই-ধাপ (উভয় মোডে):
1. ভেতরে আসল git worktree কি না।
2. `.githooks/` স্যুট উপস্থিত কি না।
3. প্রতিটি হুকে exec-bit (#3689-শ্রেণির mode-ড্রিফট রিগ্রেশন-গার্ড —
   Invariant 6: একবার ঠেকানো ত্রুটি আর ফিরবে না)।
4. `core.hooksPath` কনফিগ মান ঠিক আছে কি না।

সম্মতি-মডেল: লুপের hooks-path probe (option B, প্রত্যাখ্যাত option D) যে
নীতি মেনেছে — এই স্ক্রিপ্টও নিজে থেকে কিছু মিউটেট করে না; অপারেটর/এজেন্ট
স্পষ্টভাবে `--activate` চালালে তবেই কনফিগ সেট হয়।

পাথ-নোট: আবির্ভাবে `scripts/setup/` ছিল (PR #3942); Boundary Sanitization
Guard (#107, fail-closed) সেটিকে আনরেজিস্টার্ড সাবট্রি হিসেবে প্রত্যাখ্যান
করেছে — এখন রেজিস্টার্ড সাবট্রি `scripts/ops/`-এ (সংশোধন PR: রিলোকেট-lane)।

Exit codes: 0 = সক্রিয় ও অক্ষত; 2 = সক্রিয় নয় / অসম্পূর্ণ (report-only);
1 = অপ্রত্যাশিত ত্রুটি।
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import Optional

EXPECTED_HOOKS_PATH = ".githooks"
HOOK_NAMES = ("pre-commit", "pre-push", "post-commit")
EXPECTED_MODE_BITS = "755"


def run(cmd: list[str], cwd: Optional[str] = None) -> tuple[int, str, str]:
    """একটি কমান্ড চালিয়ে (rc, stdout, stderr) দেয়; ব্যতিক্রম rc তে রূপান্তর।"""
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=15)
        return (
            p.returncode,
            p.stdout.decode("utf-8", errors="replace").strip(),
            p.stderr.decode("utf-8", errors="replace").strip(),
        )
    except FileNotFoundError:
        return 127, "", f"binary not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout: {' '.join(cmd)}"
    except Exception as exc:  # pragma: no cover - defensive
        return 1, "", f"execution error: {exc}"


def inside_worktree(repo: str) -> bool:
    rc, _, _ = run(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo)
    return rc == 0


def check_suite(repo: str) -> tuple[list[str], list[str]]:
    """`.githooks/` স্যুটের উপস্থিতি ও exec-bit যাচাই করে (ok, problems) দেয়।"""
    ok: list[str] = []
    problems: list[str] = []
    suite = os.path.join(repo, EXPECTED_HOOKS_PATH)
    if not os.path.isdir(suite):
        problems.append(f"{EXPECTED_HOOKS_PATH}/ directory missing")
        return ok, problems
    for name in HOOK_NAMES:
        path = os.path.join(suite, name)
        if not os.path.isfile(path):
            problems.append(f"{EXPECTED_HOOKS_PATH}/{name}: missing")
            continue
        mode = os.stat(path).st_mode
        if not (mode & 0o111):
            problems.append(
                f"{EXPECTED_HOOKS_PATH}/{name}: not executable "
                f"(#3689 class mode-drift; fix: git update-index --chmod=+x)"
            )
        else:
            ok.append(f"{EXPECTED_HOOKS_PATH}/{name}: present, executable")
    return ok, problems


def check_config(repo: str) -> tuple[Optional[str], Optional[str]]:
    """`core.hooksPath` পড়ে (value, problem) দেয়।"""
    rc, out, _ = run(["git", "config", "--get", "core.hooksPath"], cwd=repo)
    if rc == 0 and out.strip():
        val = out.strip()
        if val == EXPECTED_HOOKS_PATH:
            return val, None
        # বাংলা: ভিন্ন hooksPath-ও সচেতন-রিপোর্ট হবে — নীরব override নয়।
        return val, f"core.hooksPath={val!r} (expected {EXPECTED_HOOKS_PATH!r})"
    return None, "core.hooksPath unset (enforcement suite dark by git default)"


def verify(repo: str) -> tuple[bool, list[str]]:
    """report-only যাচাই; (all_ok, report_lines) দেয়।"""
    lines: list[str] = []
    if not inside_worktree(repo):
        return False, [f"not a git worktree: {repo}"]
    ok, problems = check_suite(repo)
    lines.extend(ok)
    lines.extend(problems)
    value, cfg_problem = check_config(repo)
    if value and not cfg_problem:
        lines.append(f"core.hooksPath={value}: armed")
    elif cfg_problem:
        problems.append(cfg_problem)
        lines.append(cfg_problem)
    return (not problems), lines


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap/verify core.hooksPath for the shipped .githooks/ suite."
    )
    parser.add_argument(
        "--activate",
        action="store_true",
        help="set core.hooksPath=.githooks (local scope) before verifying",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="report-only verify (default mode; explicit alias kept because the "
        "loop advisory and this docstring both advertise --verify)",
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="repo/worktree root (default: current directory)",
    )
    args = parser.parse_args()

    repo = os.path.abspath(args.repo)
    if args.activate:
        if not inside_worktree(repo):
            print(f"activate_githooks: not a git worktree: {repo}", file=sys.stderr)
            return 1
        rc, _, err = run(
            ["git", "config", "--local", "core.hooksPath", EXPECTED_HOOKS_PATH],
            cwd=repo,
        )
        if rc != 0:
            print(f"activate_githooks: git config failed: {err}", file=sys.stderr)
            return 1
        print(f"activate_githooks: core.hooksPath set to {EXPECTED_HOOKS_PATH!r} (local)")

    all_ok, lines = verify(repo)
    tag = "OK" if all_ok else "NOT-ACTIVE"
    for line in lines:
        print(f"activate_githooks: {line}")
    print(f"activate_githooks: summary={tag}")
    return 0 if all_ok else 2


if __name__ == "__main__":
    sys.exit(main())
