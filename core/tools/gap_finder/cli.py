from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .scanner import GapScanner, load_baseline, print_summary, report_to_markdown
from .config import DEFAULT_IGNORES

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Universal project gap discovery engine for SupremeAI and reusable AI-assisted audits."
    )
    parser.add_argument("root", nargs="?", default=".", help="Project root directory")
    parser.add_argument("--format", choices=("terminal", "markdown", "json"), default="terminal")
    parser.add_argument("--output", help="Write the selected report format to this file")
    parser.add_argument("--baseline", help="Existing JSON report to compare fingerprints against")
    parser.add_argument("--write-baseline", help="Write current JSON report as baseline")
    parser.add_argument("--max-files", type=int, default=20_000)
    parser.add_argument(
        "--focus",
        help="Comma-separated categories: security,architecture,testing,ci,docs,maintainability,dependencies,operations",
    )
    parser.add_argument(
        "--ignore",
        default="",
        help="Comma-separated directory/file names to ignore in addition to defaults",
    )
    parser.add_argument(
        "--profile",
        default="universal",
        choices=("universal", "supremeai", "backend", "frontend", "mobile", "security"),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when CRITICAL/HIGH findings exist",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()

    if not root.exists() or not root.is_dir():
        print(f"ERROR: project root does not exist or is not a directory: {root}", file=sys.stderr)
        return 2

    ignores = set(DEFAULT_IGNORES)
    if args.ignore:
        ignores.update(item.strip() for item in args.ignore.split(",") if item.strip())

    focus = {item.strip().lower() for item in args.focus.split(",")} if args.focus else set()

    scanner = GapScanner(
        root,
        ignores=ignores,
        max_files=args.max_files,
        profile=args.profile,
        focus=focus,
    )
    report = scanner.scan()

    baseline = load_baseline(Path(args.baseline)) if args.baseline else set()

    if args.write_baseline:
        Path(args.write_baseline).write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    if args.format == "terminal":
        print_summary(report, baseline)
    elif args.format == "markdown":
        content = report_to_markdown(report, baseline)
        if args.output:
            Path(args.output).write_text(content, encoding="utf-8")
        else:
            print(content)
    else:
        content = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
        if args.output:
            Path(args.output).write_text(content, encoding="utf-8")
        else:
            print(content)

    if args.output and args.format == "terminal":
        Path(args.output).write_text(report_to_markdown(report, baseline), encoding="utf-8")

    if args.strict and (report.stats.critical > 0 or report.stats.high > 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
