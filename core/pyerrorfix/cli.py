"""Command-line interface for pyerrorfix.

Usage
-----
::

    # scan a path and print human-readable output
    pyerrorfix analyze backend/

    # scan + auto-fix in place (writes back to disk)
    pyerrorfix analyze backend/ --fix

    # analyze code from stdin (used by the dashboard API)
    echo 'x = 1/0' | pyerrorfix analyze --stdin --format json

    # print the full error catalog as JSON
    pyerrorfix catalog --format json

    # emit SARIF for GitHub code scanning
    pyerrorfix analyze backend/ --format sarif > results.sarif

Exit codes: 0 = no errors, 1 = errors found, 2 = invocation error.
"""

from __future__ import annotations

import argparse
import json
import sys

from pyerrorfix.core.catalog import CATALOG, catalog_summary
from pyerrorfix.core.reporter import to_console, to_json, to_markdown, to_sarif
from pyerrorfix.core.scanner import Scanner
from pyerrorfix.pyerrorfix_config import load_config


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pyerrorfix",
        description="Reusable Python error-detection & auto-fix engine for CI pipelines.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="Analyze a path or stdin for Python errors.")
    a.add_argument("path", nargs="?", default=None, help="File or directory to scan.")
    a.add_argument("--stdin", action="store_true", help="Read source from stdin.")
    a.add_argument("--fix", action="store_true", help="Apply auto-fixers.")
    a.add_argument(
        "--format",
        choices=["console", "json", "sarif", "markdown"],
        default="console",
        help="Output format. Default: console.",
    )
    a.add_argument("--config", default=None, help="Path to .pyerrorfix.json/.yaml config.")
    a.add_argument("--quiet", action="store_true", help="Suppress per-issue console output.")

    c = sub.add_parser("catalog", help="Print the full error catalog.")
    c.add_argument("--format", choices=["console", "json"], default="console")

    sub.add_parser("version", help="Print version and exit.")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        from pyerrorfix import __version__

        print(__version__)
        return 0

    if args.command == "catalog":
        return _cmd_catalog(args)

    if args.command == "analyze":
        return _cmd_analyze(args)

    parser.print_help()
    return 2


def _cmd_catalog(args: argparse.Namespace) -> int:
    if args.format == "json":
        print(
            json.dumps(
                {"catalog": CATALOG, "summary": catalog_summary()}, indent=2, ensure_ascii=False
            )
        )
        return 0
    print(f"pyerrorfix error catalog — {catalog_summary()}")
    for cat in CATALOG:
        print(f"\n## {cat['name']}  ({cat['name_bn']})")
        for e in cat["errors"]:
            fix = " [auto-fixable]" if e["fixable"] else ""
            print(f"  - {e['code']:<24} {e['title']}{fix}")
            print(f"      {e['description']}")
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    config = load_config(args.config)

    if args.stdin:
        source = sys.stdin.read()
        scanner = Scanner(config=config, apply_fixers=args.fix)
        result = scanner.scan_source(source, filename="<stdin>")
    elif args.path:
        scanner = Scanner(config=config, apply_fixers=args.fix)
        result = scanner.scan_path(args.path)
    else:
        parser_error("analyze requires either a PATH or --stdin.")
        return 2

    # output
    if args.format == "json":
        sys.stdout.write(to_json(result))
        if not to_json(result).endswith("\n"):
            sys.stdout.write("\n")
    elif args.format == "sarif":
        sys.stdout.write(to_sarif(result))
        sys.stdout.write("\n")
    elif args.format == "markdown":
        sys.stdout.write(to_markdown(result))
        sys.stdout.write("\n")
    else:
        if not args.quiet:
            to_console(result)

    # exit code: 1 if any error/critical issue, else 0
    return 1 if result.summary["errors"] > 0 else 0


def parser_error(msg: str) -> None:
    sys.stderr.write(f"pyerrorfix: error: {msg}\n")


if __name__ == "__main__":
    raise SystemExit(main())
