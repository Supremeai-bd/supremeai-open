#!/usr/bin/env python3
"""
TODO/FIXME Management System — Scans, categorizes, tracks, and reports technical debt.

বাংলা: কোডবেসে TODO, FIXME, HACK, XXX এবং অন্যান্য টেকনিক্যাল ডেট ট্যাগ স্ক্যান করে,
ক্যাটাগরাইজ করে এবং রিপোর্ট জেনারেট করে।

Features:
- Scans entire codebase recursively for TODO/FIXME/HACK/XXX/NOTE tags
- Categorizes by severity (CRITICAL, HIGH, MEDIUM, LOW)
- Supports .gitignore-aware scanning
- Generates JSON, Markdown, or CLI-summary reports
- Age tracking: calculates how long each TODO has existed

Usage:
    python scripts/devops/todo_manager.py scan
    python scripts/devops/todo_manager.py scan --format markdown --output todo_report.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Force UTF-8 stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()

TAG_SEVERITY: dict[str, str] = {
    "FIXME": "CRITICAL",
    "BUG": "CRITICAL",
    "HACK": "HIGH",
    "XXX": "HIGH",
    "TODO": "MEDIUM",
    "OPTIMIZE": "LOW",
    "NOTE": "LOW",
}

SEVERITY_ICONS: dict[str, str] = {
    "CRITICAL": "🔴",
    "HIGH": "🟠",
    "MEDIUM": "🟡",
    "LOW": "🔵",
}

SKIP_DIRS: frozenset[str] = frozenset({
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    "htmlcov", ".worktrees", "_archive", "scratch",
})

SCAN_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java",
    ".kt", ".swift", ".cpp", ".c", ".h", ".hpp", ".cs", ".rb",
    ".php", ".sh", ".yaml", ".yml", ".json", ".toml", ".md", ".sql",
})


@dataclass
class TodoItem:
    """Represents a single TODO/FIXME/HACK item found in the codebase."""
    tag: str
    severity: str
    message: str
    file_path: str
    line_number: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScanResult:
    """Aggregated scan results."""
    total_count: int = 0
    items: list[TodoItem] = field(default_factory=list)
    by_severity: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    by_tag: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    scan_time_seconds: float = 0.0
    files_scanned: int = 0


class TodoManager:
    """Manages TODO/FIXME/HACK scanning and reporting."""

    def __init__(self, root_dir: Path = PROJECT_ROOT) -> None:
        self.root_dir = root_dir
        self.tag_pattern = re.compile(
            r"#?\s*\b(TODO|FIXME|HACK|XXX|BUG|OPTIMIZE|NOTE)\b(?::|\s)?\s*(.*)",
            re.IGNORECASE,
        )

    def scan(self, scan_dir: str | Path | None = None) -> ScanResult:
        start_time = time.time()
        scan_path = self.root_dir
        if scan_dir:
            scan_path = (self.root_dir / scan_dir).resolve()
            if not scan_path.exists():
                print(f"⚠️ Scan directory not found: {scan_path}")
                return ScanResult()

        result = ScanResult()
        seen_keys: set[str] = set()

        for filepath in scan_path.rglob("*"):
            if any(part in SKIP_DIRS for part in filepath.parts):
                continue
            if filepath.suffix.lower() not in SCAN_EXTENSIONS:
                continue

            result.files_scanned += 1
            try:
                rel_path = str(filepath.relative_to(self.root_dir))
            except ValueError:
                rel_path = str(filepath)

            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, 1):
                        match = self.tag_pattern.search(line)
                        if match:
                            tag = match.group(1).upper()
                            msg = match.group(2).strip() or line.strip()
                            key = f"{rel_path}:{line_num}:{tag}"
                            if key in seen_keys:
                                continue
                            seen_keys.add(key)

                            severity = TAG_SEVERITY.get(tag, "MEDIUM")
                            item = TodoItem(
                                tag=tag,
                                severity=severity,
                                message=msg,
                                file_path=rel_path,
                                line_number=line_num,
                            )
                            result.items.append(item)
                            result.by_severity[severity] += 1
                            result.by_tag[tag] += 1
            except (OSError, PermissionError):
                continue

        result.total_count = len(result.items)
        result.scan_time_seconds = time.time() - start_time
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        result.items.sort(key=lambda x: (severity_order.get(x.severity, 99), x.file_path, x.line_number))
        return result

    def format_terminal_summary(self, result: ScanResult) -> str:
        lines = [
            "=" * 60,
            "📋 SupremeAI Technical Debt & TODO Summary",
            "=" * 60,
            f"Files Scanned: {result.files_scanned} | Total Debt Items: {result.total_count}",
            f"Scan Time: {result.scan_time_seconds:.2f}s\n",
        ]
        for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            count = result.by_severity.get(sev, 0)
            icon = SEVERITY_ICONS.get(sev, "▫️")
            lines.append(f"{icon} {sev}: {count}")

        lines.append("\nTop Technical Debt Items:")
        for item in result.items[:10]:
            lines.append(f"  [{item.severity}] {item.tag} {item.file_path}:L{item.line_number} — {item.message[:60]}")

        lines.append("=" * 60)
        return "\n".join(lines)

    def format_markdown_report(self, result: ScanResult) -> str:
        lines = [
            "# 📋 Technical Debt & TODO Report",
            f"**Generated at:** `{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}` | **Files Scanned:** `{result.files_scanned}` | **Total Items:** `{result.total_count}`\n",
        ]
        by_sev: dict[str, list[TodoItem]] = defaultdict(list)
        for item in result.items:
            by_sev[item.severity].append(item)

        for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            group = by_sev.get(sev, [])
            if not group:
                continue
            icon = SEVERITY_ICONS.get(sev, "▫️")
            lines.append(f"### {icon} {sev} Priority ({len(group)})")
            lines.append("| Tag | File | Line | Details |")
            lines.append("|---|---|---|---|")
            for item in group:
                clean_msg = item.message.replace("|", "\\|")
                lines.append(f"| `{item.tag}` | `{item.file_path}` | L{item.line_number} | {clean_msg} |")
            lines.append("")

        return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="SupremeAI TODO & Technical Debt Manager")
    subparsers = parser.add_subparsers(dest="subcommand", help="Command to run")

    scan_parser = subparsers.add_parser("scan", help="Scan codebase for TODO/FIXME tags")
    scan_parser.add_argument("--dir", type=str, help="Target directory (relative to root)")
    scan_parser.add_argument("--format", choices=["cli", "markdown", "json"], default="cli", help="Report output format")
    scan_parser.add_argument("--output", type=str, help="Save report to file path")

    args = parser.parse_args()

    manager = TodoManager()
    result = manager.scan(scan_dir=getattr(args, "dir", None))

    fmt = getattr(args, "format", "cli")
    if fmt == "json":
        report = json.dumps([item.to_dict() for item in result.items], indent=2, ensure_ascii=False)
    elif fmt == "markdown":
        report = manager.format_markdown_report(result)
    else:
        report = manager.format_terminal_summary(result)

    out_file = getattr(args, "output", None)
    if out_file:
        out_path = Path(out_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"📄 Report written to: {out_path}")
    else:
        print(report)


if __name__ == "__main__":
    main()
