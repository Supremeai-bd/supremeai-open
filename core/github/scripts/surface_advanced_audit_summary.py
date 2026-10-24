#!/usr/bin/env python3
"""Render Advanced Pre-Merge audit artifacts into the final CI job summary.

The Advanced Pre-Merge Checks job already generates rich reports under
``ci-reports/`` and uploads them as ``supremeai-ci-audit-reports``.
The final Smart Pipeline Summary job is a separate runner, so those files are
not automatically present there. The workflow downloads the artifact first,
then this script safely surfaces the most useful information in the same
GITHUB_STEP_SUMMARY page.

Design goals:
  * Do not fail the CI summary job if an audit artifact is missing.
  * Show high-signal counts first.
  * Keep long/raw reports inside collapsible GitHub sections.
  * Redact obvious credential/token/password patterns before rendering.
  * Preserve the exact audit files as downloadable artifacts for deep dives.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Iterable


REPORT_DIR = Path(os.getenv("CI_AUDIT_REPORT_DIR", "ci-reports"))
SUMMARY_FILE = REPORT_DIR / "summary.txt"
ERRORS_FILE = REPORT_DIR / "errors.txt"
WARNINGS_FILE = REPORT_DIR / "warnings.txt"

MAX_FILE_PREVIEW_CHARS = 8000
MAX_INLINE_LINES = 80

SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~-]{12,}"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)['\"]?[^'\"]{8,}"),
    re.compile(r"(?i)(token\s*[=:]\s*)['\"]?[^'\"]{8,}"),
    re.compile(r"(?i)(password\s*[=:]\s*)['\"]?[^'\"]{4,}"),
    re.compile(r"(?i)(secret\s*[=:]\s*)['\"]?[^'\"]{8,}"),
    re.compile(r"(?i)(postgres(?:ql)?://[^/\s:]+:)[^@\s]+(@)"),
    re.compile(r"(?i)(redis://[^/\s:]+:)[^@\s]+(@)"),
]


def redact(text: str) -> str:
    """Redact common credential-shaped values before writing to Step Summary."""
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(lambda m: f"{m.group(1)}[REDACTED]", text)
    return text


def read_lines(path: Path) -> list[str]:
    if not path.exists() or not path.is_file():
        return []
    try:
        return [
            line.strip()
            for line in path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
            if line.strip()
        ]
    except OSError:
        return []


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def bounded_text(lines: list[str]) -> str:
    text = "\n".join(redact(line) for line in lines[:MAX_INLINE_LINES])
    if len(text) > MAX_FILE_PREVIEW_CHARS:
        text = text[:MAX_FILE_PREVIEW_CHARS] + "\n…[truncated]…"
    if len(lines) > MAX_INLINE_LINES:
        text += (
            f"\n…[showing first {MAX_INLINE_LINES} lines; "
            "full report is in the CI artifact]…"
        )
    return text


def parse_counts() -> tuple[int, int, int]:
    return (
        len(read_lines(SUMMARY_FILE)),
        len(read_lines(WARNINGS_FILE)),
        len(read_lines(ERRORS_FILE)),
    )


def classify_files(paths: list[Path]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in paths:
        suffix = path.suffix.lower() or "[no extension]"
        counts[suffix] = counts.get(suffix, 0) + 1
    return dict(sorted(counts.items()))


def render_inventory(paths: list[Path]) -> list[str]:
    lines = [
        "### 📦 Audit Report Inventory",
        "",
        "| Report | Type | Size |",
        "|---|---|---:|",
    ]
    for path in sorted(paths, key=lambda p: str(p).lower()):
        rel = path.relative_to(REPORT_DIR).as_posix()
        suffix = path.suffix.lower() or "text"
        lines.append(f"| `{rel}` | `{suffix}` | {file_size(path):,} B |")

    formats = classify_files(paths)
    if formats:
        compact = ", ".join(
            f"`{kind}` × {count}" for kind, count in formats.items()
        )
        lines.extend(["", f"**Formats:** {compact}"])
    lines.append("")
    return lines


def render_special(
    path: Path,
    title: str,
    icon: str,
) -> list[str]:
    lines = read_lines(path)
    if not lines:
        return []
    return [
        "<details>",
        f"<summary>{icon} {title} ({len(lines)} entries)</summary>",
        "",
        "```text",
        bounded_text(lines),
        "```",
        "",
        "</details>",
        "",
    ]


def render_json(path: Path) -> list[str]:
    try:
        data = json.loads(
            path.read_text(encoding="utf-8", errors="replace")
        )
    except (OSError, json.JSONDecodeError):
        return render_text(path)

    pretty = json.dumps(
        data, indent=2, ensure_ascii=False, sort_keys=True
    )
    pretty = redact(pretty)
    if len(pretty) > MAX_FILE_PREVIEW_CHARS:
        pretty = pretty[:MAX_FILE_PREVIEW_CHARS] + "\n…[truncated]…"

    rel = path.relative_to(REPORT_DIR).as_posix()
    return [
        "<details>",
        f"<summary>📄 `{rel}` (JSON)</summary>",
        "",
        "```json",
        pretty,
        "```",
        "",
        "</details>",
        "",
    ]


def render_text(path: Path) -> list[str]:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    preview = redact(raw)
    if len(preview) > MAX_FILE_PREVIEW_CHARS:
        preview = (
            preview[:MAX_FILE_PREVIEW_CHARS]
            + "\n…[truncated; full report is in the CI artifact]…"
        )

    rel = path.relative_to(REPORT_DIR).as_posix()
    return [
        "<details>",
        f"<summary>📄 `{rel}`</summary>",
        "",
        "```text",
        preview,
        "```",
        "",
        "</details>",
        "",
    ]


def main() -> int:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    report_paths = (
        sorted(
            p for p in REPORT_DIR.rglob("*")
            if p.is_file()
        )
        if REPORT_DIR.exists()
        else []
    )

    passed, warnings, errors = parse_counts()

    if not report_paths:
        output = [
            "",
            "## 🛡️ Advanced Pre-Merge Audit — Detailed Results",
            "",
            "> ⚠️ `supremeai-ci-audit-reports` was not available in the "
            "Smart Summary job.",
            "> The Advanced Pre-Merge job may have been skipped or its "
            "artifact may not have been produced.",
            "",
        ]
    else:
        status = (
            "❌ ERRORS FOUND"
            if errors
            else "⚠️ WARNINGS PRESENT"
            if warnings
            else "✅ CLEAN"
        )
        output = [
            "",
            "## 🛡️ Advanced Pre-Merge Audit — Detailed Results",
            "",
            f"**Audit status:** {status}",
            "",
            "| Quality Signal | Count |",
            "|---|---:|",
            f"| ✅ Passed audit checks | **{passed}** |",
            f"| ⚠️ Warnings | **{warnings}** |",
            f"| ❌ Errors | **{errors}** |",
            f"| 📦 Detailed report files | **{len(report_paths)}** |",
            "",
            "> The compact Smart Summary remains first; this section surfaces "
            "the deeper audit evidence in the same page. Full raw artifacts "
            "remain downloadable.",
            "",
        ]

        output.extend(render_inventory(report_paths))
        output.extend(render_special(ERRORS_FILE, "Detected Errors", "❌"))
        output.extend(render_special(WARNINGS_FILE, "Warnings", "⚠️"))
        output.extend(render_special(SUMMARY_FILE, "Passed Checks", "✅"))

        special = {SUMMARY_FILE, ERRORS_FILE, WARNINGS_FILE}
        for path in report_paths:
            if path in special:
                continue
            if path.suffix.lower() == ".json":
                output.extend(render_json(path))
            else:
                output.extend(render_text(path))

    text = "\n".join(output) + "\n"
    if summary_path:
        Path(summary_path).open("a", encoding="utf-8").write(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
