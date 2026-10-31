#!/usr/bin/env python3
"""Guard: every command the loop advisory advertises must be runnable end-to-end.

Invariant 6 close-out for the #4070/#3997 failure class (R63/#2343 chain).

বাংলা: গত দুই পর্বে একই ত্রুটি-শ্রেণি দুইবার বাস্তবে ধরা দিয়েছে —
(১) লুপ-advisory একটি পাথ শেখাল যা রিপো-গভর্নেন্সে অনুমোদিতই ছিল না
(#3942, Boundary Guard #107 লাল), (২) লুপ-advisory একটি ফ্ল্যাগ শেখাল
যা স্ক্রিপ্টের argparse চেনেই না (#4070, 'unrecognized arguments')।
মানে: advisory-স্ট্রিং আর বিজ্ঞাপিত-পৃষ্ঠের মধ্যে বিচ্ছুটি হলে তা কোনো
মেশিন-স্তরে ধরা পড়ত না — শুধু agent-রান ব্যর্থ হয়ে আবিষ্কৃত হত।

এই গার্ড সেই স্তরটি বসায় — `hooks_path_advisory()`-এর রিটার্ন-লিটারাল
(ast-ভিত্তিক সিনট্যাক্স-নির্ভর আহরণ; রেজেক্স-হীন, ফরম্যাট-পরিবর্তনে
ফেইল-ক্লোজড) থেকে বিজ্ঞাপিত কমান্ড বের করে যাচাই করে:

1. বিজ্ঞাপিত স্ক্রিপ্ট-পাথ এই ক্লোনে বিদ্যমান কি না।
2. স্ক্রিপ্টের প্রকৃত `--help` (subprocess) exit 0 দেয় কি না — মানে
   argparse সত্যিই ফ্ল্যাগটি গ্রহণ করে (স্ট্যাটিক-গ্রেপের চেয়ে শক্ত)।
3. প্রতিটি বিজ্ঞাপিত ফ্ল্যাগ `--help` আউটপুটে দৃশ্যমান কি না।

Exit codes: 0 = পূর্ণ পৃষ্ঠ চালনযোগ্য; 2 = বিচ্ছুটি ধরা পড়েছে (রিপোর্ট);
1 = অপ্রত্যাশিত ত্রুটি (যেমন advisory-ফাংশন/লিটারাল সোর্সেই পাওয়া যায়নি)।
"""

from __future__ import annotations

import argparse
import ast
import os
import subprocess
import sys
from typing import Optional

DEFAULT_LOOP = "scripts/agents/continuous_agent_loop.py"
ADVISORY_FUNC = "hooks_path_advisory"
ADVISORY_HELP = "python3"


def extract_advisory_literals(loop_path: str) -> tuple[list[str], Optional[str]]:
    """ast দিয়ে advisory-ফাংশনের সব return-লিটারাল আহরণ করে (msgs, problem) দেয়।

    বাংলা: implicit string concatenation CPython-এ এক Constant-এ ফোল্ড হয়,
    তাই প্রতিটি শাখার স্ট্রিং-জোড়া এক মান হিসেবেই পড়া যায়। ফাংশনে একাধিক
    বিজ্ঞাপন-শাখা থাকতে পারে (যেমন পুরোনো-ক্লোন শাখা) — প্রতিটিই যাচাই-
    যোগ্য হতে হবে, তাই তালিকা দেয়। f-string/গণনাশীল শাখা সৎভাবে skip
    (static-extraction অসম্ভব) — বাকি শাখাগুলো দিয়ে সিদ্ধান্ত হয়; একটিও
    স্ট্যাটিক শাখা না পেলে সমস্যা-রিপোর্ট — নিঃশব্দ-পাস নয়।
    """
    try:
        src = open(loop_path, encoding="utf-8").read()
    except OSError as exc:
        return [], f"loop file unreadable: {loop_path} ({exc})"
    try:
        tree = ast.parse(src, filename=loop_path)
    except SyntaxError as exc:
        return [], f"loop file does not parse: {exc}"
    static: list[str] = []
    dynamic = 0
    saw_func = False
    for node in ast.walk(tree):
        if not (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == ADVISORY_FUNC):
            continue
        saw_func = True
        for sub in ast.walk(node):
            if isinstance(sub, ast.Return):
                val = sub.value
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    static.append(val.value)
                elif isinstance(val, ast.BinOp):
                    dynamic += 1
    if not saw_func:
        return [], f"no '{ADVISORY_FUNC}' function found in {loop_path}"
    if not static:
        if dynamic:
            return [], (
                f"'{ADVISORY_FUNC}' has only dynamic returns ({dynamic}); "
                "static extraction unsupported — extend this guard"
            )
        return [], f"no string return literals in '{ADVISORY_FUNC}'"
    return static, None


def parse_advertised_command(msg: str) -> tuple[Optional[str], list[str], Optional[str]]:
    """বার্তা থেকে (script_path, flags, problem) বের করে।"""
    tokens = [t for raw in msg.splitlines() for t in raw.split()]
    if ADVISORY_HELP not in tokens:
        return None, [], "no 'python3' command advertised in advisory literal"
    i = tokens.index(ADVISORY_HELP)
    candidates = tokens[i + 1 :]
    if not candidates:
        return None, [], "'python3' advertised with no script argument"
    script = candidates[0]
    flags: list[str] = []
    for tok in candidates[1:]:
        clean = tok.strip(",;()")
        if clean.startswith("--"):
            flags.append(clean)
    return script, flags, None


def check_surface(script: str, flags: list[str]) -> tuple[bool, list[str]]:
    """পাথ-অস্তিত্ব + প্রকৃত --help রান করে (ok, lines) দেয়।"""
    ok = True
    lines: list[str] = []
    if not os.path.isfile(script):
        return False, [f"advertised script missing: {script}"]
    lines.append(f"script present: {script}")
    try:
        p = subprocess.run(
            [sys.executable, script, "--help"], capture_output=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, [f"script --help failed to run: {exc}"]
    if p.returncode != 0:
        ok = False
        lines.append(f"script --help exit={p.returncode} (argparse or runtime error)")
        return ok, lines
    help_text = p.stdout.decode("utf-8", errors="replace") + p.stderr.decode(
        "utf-8", errors="replace"
    )
    for flag in flags:
        if flag in help_text:
            lines.append(f"flag {flag}: advertised and accepted by --help")
        else:
            ok = False
            lines.append(f"flag {flag}: advertised in advisory but ABSENT from --help")
    return ok, lines


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify every command advertised by the loop hooks-path advisory is runnable."
    )
    parser.add_argument(
        "--loop",
        default=DEFAULT_LOOP,
        help="path to continuous_agent_loop.py (default: repo-relative standard path)",
    )
    args = parser.parse_args()

    msgs, problem = extract_advisory_literals(args.loop)
    if problem:
        print(f"check_advisory_surface: {problem}", file=sys.stderr)
        return 1
    all_ok = True
    saw_any_command = False
    for idx, msg in enumerate(msgs, start=1):
        script, flags, pproblem = parse_advertised_command(msg)
        if pproblem or not script:
            # বাংলা: python3-বিজ্ঞাপনহীন শাখা (যেমন সতর্কবার্তা-শাখা) — যাচাইযোগ্য
            # কমান্ড নেই, সৎ-নোট; শুধু অন্য কোনো শাখা কমান্ড বিজ্ঞাপন করলে সেটি শক্ত-যাচাই হবে।
            print(f"check_advisory_surface: branch {idx}: no runnable command advertised (noted)")
            continue
        saw_any_command = True
        ok, lines = check_surface(script, flags)
        all_ok = all_ok and ok
        for line in lines:
            print(f"check_advisory_surface: branch {idx}: {line}")
    if not saw_any_command:
        print(
            "check_advisory_surface: no runnable command found in any advisory branch",
            file=sys.stderr,
        )
        return 1
    print(f"check_advisory_surface: summary={'OK' if all_ok else 'DIVERGENT'}")
    return 0 if all_ok else 2


if __name__ == "__main__":
    sys.exit(main())
