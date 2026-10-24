#!/usr/bin/env python3
"""
check_react_cleanup.py
======================
Scans React components for useEffect hooks with subscriptions or event listeners
that lack cleanup return statements (Trap #74).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SUBSCRIBER_PATTERNS = [
    r"componentEventBus\.subscribe",
    r"addEventListener",
    r"setInterval",
    r"webSocket",
    r"subscribe\(",
]


def check_file(filepath: Path) -> list[str]:
    issues = []
    content = filepath.read_text(encoding="utf-8", errors="ignore")

    # Fast pattern match for useEffect
    use_effect_matches = list(re.finditer(r"useEffect\s*\(\s*(?:async\s*)?\(\s*\)\s*=>\s*\{", content))
    for m in use_effect_matches:
        start_pos = m.start()
        # Find rough end of the useEffect block
        chunk = content[start_pos : start_pos + 1500]
        has_sub = any(re.search(pat, chunk) for pat in SUBSCRIBER_PATTERNS)
        if has_sub:
            if "return () =>" not in chunk and "return () =>" not in chunk.replace(" ", "") and "return function" not in chunk:
                line_num = content[:start_pos].count("\n") + 1
                issues.append(
                    f"{filepath.name}:{line_num} useEffect contains listener/subscription without return cleanup! (Trap #74)"
                )

    return issues


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    files = [Path(f) for f in sys.argv[1:] if f.endswith((".ts", ".tsx"))]
    if not files:
        # scan frontend/src by default if no args passed
        repo_root = Path(__file__).resolve().parents[2]
        src_dir = repo_root / "frontend" / "src"
        if src_dir.exists():
            files = list(src_dir.rglob("*.tsx")) + list(src_dir.rglob("*.ts"))

    all_issues = []
    for fp in files:
        issues = check_file(fp)
        for iss in issues:
            print(f"[WARN] [react-cleanup-lint] {iss}")
            all_issues.append(iss)

    if all_issues:
        print("[Audit Mode]: Logged React cleanup warnings, returning 0.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
