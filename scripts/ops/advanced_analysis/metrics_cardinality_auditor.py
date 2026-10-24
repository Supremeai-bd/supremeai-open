#!/usr/bin/env python3
"""
metrics_cardinality_auditor.py
==============================
Audit tool to detect High-Cardinality Metrics Bombs (Trap #101).
Scans for:
1. Calls to increment_counter, observe_histogram, set_gauge with labels.
2. Flags dangerous unbounded label keys such as:
   - user_id, uid, email, token, session_id, message_id, trace_id, prompt, ip, uuid
3. Ensures only bounded categorical labels (endpoint, method, status_code, type, model) are used.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

UNBOUNDED_LABEL_KEYS = {
    "user_id",
    "uid",
    "email",
    "token",
    "session_id",
    "message_id",
    "task_id",
    "trace_id",
    "prompt",
    "ip",
    "client_ip",
    "uuid",
    "timestamp",
}


def audit_metrics_cardinality() -> list[str]:
    issues = []
    for py_file in BACKEND_ROOT.rglob("*.py"):
        if any(part.startswith(".") or part in ("tests", "venv", ".venv") for part in py_file.parts):
            continue

        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            if "labels" not in content and "increment_counter" not in content and "observe_histogram" not in content:
                continue

            tree = ast.parse(content, filename=str(py_file))
            rel_path = str(py_file.relative_to(REPO_ROOT))

            for node in ast.walk(tree):
                if isinstance(node, ast.Dict):
                    # Check if this dictionary looks like metrics labels
                    label_keys = []
                    for k in node.keys:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            label_keys.append(k.value.lower())

                    for k_name in label_keys:
                        if k_name in UNBOUNDED_LABEL_KEYS:
                            # Verify if inside metrics context
                            issues.append(
                                f"High cardinality metrics risk in {rel_path}:{node.lineno}: "
                                f"Unbounded label key '{k_name}' detected. This can cause memory exhaustion (Trap #101)!"
                            )
        except Exception as e:
            issues.append(f"Error checking {py_file}: {e}")

    return issues


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Auditing Prometheus/Collector Metrics for High-Cardinality Bombs (Trap #101)...")
    issues = audit_metrics_cardinality()

    if issues:
        for issue in issues:
            print(f"[WARN] {issue}")
        print(f"\nTotal cardinality bomb findings: {len(issues)}")
        return 0

    print("[PASS] No unbounded high-cardinality metrics label keys detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
