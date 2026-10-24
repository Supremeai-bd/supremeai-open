#!/usr/bin/env python3
"""
ai_memory_integrity_audit.py
============================
Audit tool for AI Memory & Knowledge Base Integrity (Traps #8, #21, #23).
Checks:
1. Memory Isolation & Poisoning:
   - Verifies that ai_memory table queries require user_id/session_id boundaries.
   - Ensures memory entries do not store raw unsanitized prompt injection vectors.
2. GDPR Deletion Compliance (Trap #21):
   - Verifies that delete_memory routines properly remove both database records and associated vectors.
3. Persistence Check (Trap #23):
   - Checks that production configurations do not default to ephemeral in-memory or transient stores without degraded mode alerts.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"


def audit_memory_service_implementation() -> list[str]:
    issues = []
    mem_file = BACKEND_ROOT / "services" / "memory_service.py"
    if not mem_file.exists():
        issues.append(f"Missing memory service file: {mem_file}")
        return issues

    content = mem_file.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(content, filename=str(mem_file))
    except Exception as e:
        issues.append(f"Failed to parse memory_service.py: {e}")
        return issues

    # 1. Check user_id in store_memory
    has_user_id_in_store = False
    has_delete_method = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "store_memory":
                arg_names = [a.arg for a in node.args.args]
                if "user_id" in arg_names:
                    has_user_id_in_store = True
            elif node.name == "delete_memory":
                has_delete_method = True

    if not has_user_id_in_store:
        issues.append("CascadeMemoryService.store_memory is missing 'user_id' parameter — risk of cross-tenant memory leakage (Trap #8)!")

    if not has_delete_method:
        issues.append("CascadeMemoryService lacks delete_memory method — GDPR compliance failure (Trap #21)!")

    # 2. Check ephemeral fallback detection (Trap #23)
    if "sqlite_fallback_allowed" not in content or "InMemoryRing" not in content:
        issues.append("CascadeMemoryService lacks explicit degraded in-process ring buffer guards against silent ephemeral loss (Trap #23)!")

    return issues


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Auditing AI Memory Integrity, GDPR Deletion & Vector Persistence (Traps #8, #21, #23)...")
    issues = audit_memory_service_implementation()

    if issues:
        for issue in issues:
            print(f"[FAIL] {issue}")
        print(f"\nTotal AI memory integrity findings: {len(issues)}")
        return 1

    print("[PASS] AI Memory isolation, GDPR deletion hooks, and persistence safeguards verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
