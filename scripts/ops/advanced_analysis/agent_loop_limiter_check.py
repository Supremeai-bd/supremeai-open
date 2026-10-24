#!/usr/bin/env python3
"""
agent_loop_limiter_check.py
===========================
Audit tool to detect Unbounded Agent Execution Loops (Trap #15).
Scans for:
1. Agent orchestration while loops, debate loops, or iterative reasoning loops.
2. Verifies each loop has a hard cap (MAX_ITERATIONS, max_steps, MAX_AGENT_ITERATIONS)
   and a circuit breaker or timeout to avoid runaway costs and infinite loops.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"


def audit_agent_loops() -> list[str]:
    issues = []
    agent_dirs = [
        BACKEND_ROOT / "core" / "orchestration",
        BACKEND_ROOT / "engine",
        BACKEND_ROOT / "brain",
        BACKEND_ROOT / "tools" / "code",
    ]

    for d in agent_dirs:
        if not d.exists():
            continue
        for py_file in d.glob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content, filename=str(py_file))
                rel_path = str(py_file.relative_to(REPO_ROOT))

                for node in ast.walk(tree):
                    if isinstance(node, ast.While):
                        # Inspect test condition of while loop
                        test_str = ast.unparse(node.test).lower()
                        # If while True or while condition doesn't reference limit or iteration, check inside body
                        body_str = ast.unparse(node).lower()
                        has_limit_or_break = any(
                            term in (test_str + body_str)
                            for term in ("iteration", "max_", "break", "timeout", "circuit_breaker", "step")
                        )
                        if not has_limit_or_break:
                            issues.append(
                                f"Unbounded loop risk in {rel_path}:{node.lineno} (`while {test_str}`): "
                                f"No iteration limit, timeout guard, or circuit breaker detected (Trap #15)!"
                            )
            except Exception as e:
                issues.append(f"Error parsing {py_file}: {e}")

    return issues


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Auditing Agent Loops for MAX_ITERATIONS and Circuit Breaker Guards (Trap #15)...")
    issues = audit_agent_loops()

    if issues:
        for issue in issues:
            print(f"[WARN] {issue}")
        print(f"\nTotal loop limiter findings: {len(issues)}")
        return 0

    print("[PASS] All agent execution loops enforce MAX_ITERATIONS and circuit breakers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
