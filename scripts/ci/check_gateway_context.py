# scripts/ci/check_gateway_context.py
"""M03 P0-পূর্ণাংশ — ১৩ serving route-এ বাধ্যতামূলক InferenceContext গেট।

বাংলা মন্তব্য: নীতি — backend/api/routes/-এ LLMGateway-এর inference-কল
(``acompletion``/``complete``/``async_generate``) প্রতিটিতে ``context=``
(InferenceContext) বাধ্যতামূলক। ফলে টেন্যান্ট/টাস্ক অ্যাট্রিবিউশন ছাড়া
অদৃশ্য-খরচ (CostGuard-বাইপাসড) serving-পথ কাঠামোগতভাবে অসম্ভব।

Ratchet নীতি (any-ratchet-প্রেসিডেন্ট): লঙ্ঘন-সংখ্যা বেসলাইনের বেশি হলে
exit 2 — নতুন context-হীন কল নিষিদ্ধ; কমলে বেসলাইন নিজেই কমিয়ে নেওয়ার
প্রত্যাশা (downward ratchet)। ফেল-ওপেন (`|| true`) বা বেসলাইন-বৃদ্ধি নিষিদ্ধ।
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTES_DIR = REPO_ROOT / "backend" / "api" / "routes"

#: গেটওয়ে-ইনস্ট্যান্স মনে রাখা নাম — `from core.llm.llm_gateway import <n>`।
GATEWAY_IMPORT_NAMES = {"llm_gateway", "get_llm_gateway", "GatewayManager"}

#: inference-কল মানে এই মেথডগুলো (gateway instance-এ)।
INFERENCE_METHODS = {"acompletion", "complete", "async_generate"}

#: বর্তমান স্বীকৃত লঙ্ঘন-সংখ্যা — কেবল নিচের দিকে সংশোধনযোগ্য।
BASELINE = 0


def _collect_gateway_names(tree: ast.AST) -> set[str]:
    """ফাইলের ভেতরে gateway-instance ধারণকারী নামগুলো খুঁজে বের করে।"""
    names: set[str] = set()
    for node in ast.walk(tree):
        # from core.llm.llm_gateway import llm_gateway → instance alias
        if isinstance(node, ast.ImportFrom) and node.module == "core.llm.llm_gateway":
            for alias in node.names:
                if alias.name in GATEWAY_IMPORT_NAMES and alias.name != "get_llm_gateway":
                    names.add(alias.asname or alias.name)
        # x = get_llm_gateway() → factory result
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fn = node.value.func
            if isinstance(fn, ast.Name) and fn.id == "get_llm_gateway":
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
    return names


def scan() -> tuple[list[str], int]:
    """api/routes-এ context-হীন inference-কল খুঁজে ফেরত দেয় (violations, total)।"""
    violations: list[str] = []
    total_sites = 0
    for py_file in sorted(ROUTES_DIR.glob("*.py")):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError) as exc:
            violations.append(f"{py_file.name}: unparseable ({exc})")
            continue
        gateway_names = _collect_gateway_names(tree)
        if not gateway_names:
            continue
        try:
            rel = py_file.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            # টেস্ট-সিনথেটিক ট্রি (REPO_ROOT-বহির্ভূত tmp ডিরেক্টরি)।
            rel = py_file.name
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr not in INFERENCE_METHODS:
                continue
            if not (isinstance(node.func.value, ast.Name) and node.func.value.id in gateway_names):
                continue
            total_sites += 1
            has_context = any(kw.arg == "context" for kw in node.keywords)
            if not has_context:
                violations.append(f"{rel}:{node.lineno}: gateway call without context=")
    return violations, total_sites


def main() -> int:
    violations, total_sites = scan()
    print(f"[gateway-context] scanned inference call-sites: {total_sites}")
    print(f"[gateway-context] context-less violations: {len(violations)} (baseline {BASELINE})")
    for v in violations:
        print(f"  VIOLATION {v}")
    if len(violations) > BASELINE:
        print("[gateway-context] FAIL — ratchet exceeded; নতুন কলে context= যোগ করুন")
        return 2
    print("[gateway-context] PASS — ১৩-route context-coverage অটুট")
    return 0


if __name__ == "__main__":
    sys.exit(main())
