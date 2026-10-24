#!/usr/bin/env python3
"""Detect definition shadowing: Python silently keeps the LAST definition.

Two silent-defect classes this audit surfaces:

1. Duplicate function/class definitions. A later ``def``/``class`` with the
   same name silently REPLACES the earlier one. If a later maintenance round
   edits the first copy, the stale duplicate still wins at runtime. Real case
   fixed on this repo: ``DistributedConnectionManager.connect`` was defined
   twice and the owner's ``_connection_lock`` race-condition fix lived in the
   copy Python threw away (dead code until shipped).
2. Duplicate keys in dict literals: the earlier entry is silently
   overwritten.

Intentional same-name patterns are excluded so they never pollute the
report:

- ``@x.setter`` / ``@x.deleter`` accessor pairs (property companions),
- ``typing.overload`` stubs,
- ``functools.singledispatch`` ``.register`` handlers.

Rollout is a RATCHET, not a day-one hard gate (mirrors coverage_policy.yaml):

- Default (no ``--baseline``): report-only, exit 0.
- With ``--baseline <file>``: gate mode. Findings not covered by the baseline
  (new file, new (kind, name), or a higher count) FAIL with exit 1. Shrinking
  counts pass and are reported as improvements, with a hint to regenerate the
  baseline via ``--update-baseline``.

The initial baseline documents today's inventory — including duplicates the
owner has explicitly chosen to preserve (see
``backend/api/routes/browser/_tasks.py`` module docstring) — so future
duplicates of this bug class break CI while owner-preserved code stays
untouched (wire-first doctrine).
"""

from __future__ import annotations

import argparse
import ast
import json
import logging
from collections import Counter
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_ROOTS = ("backend", "tools", "scripts")
EXCLUDED_PARTS = {"tests", "examples", "__pycache__", ".venv", "venv", "node_modules"}
BASELINE_SCHEMA_VERSION = 1
FINDING_KINDS = (
    "shadowed_def",
    "shadowed_class",
    "shadowed_method",
    "shadowed_dict_key",
)


def iter_python_files(roots: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for root_name in roots:
        root = Path(root_name)
        if not root.exists():
            continue
        files.extend(
            path
            for path in root.rglob("*.py")
            if not EXCLUDED_PARTS.intersection(path.parts)
        )
    return sorted(set(files))


def _decorator_is(node: ast.AST, attr_names: set[str], plain_names: set[str]) -> bool:
    """True when decorator is ``name`` / ``mod.name`` / ``x.attr`` style match."""
    target = node.func if isinstance(node, ast.Call) else node
    name_match = isinstance(target, ast.Name) and target.id in plain_names
    attr_match = isinstance(target, ast.Attribute) and target.attr in attr_names
    return name_match or attr_match


def _is_intentional_redefinition(node: ast.AST) -> bool:
    """Accessor pairs, overloads and dispatch registrations share names on purpose."""
    for decorator in getattr(node, "decorator_list", []):
        if _decorator_is(decorator, {"setter", "deleter"}, set()):
            return True
        if _decorator_is(decorator, {"overload", "register"}, {"overload"}):
            return True
    return False


def _is_overload_stub(node: ast.AST) -> bool:
    """``@overload`` stubs are followed by one undecorated implementation def."""
    for decorator in getattr(node, "decorator_list", []):
        if _decorator_is(decorator, {"overload"}, {"overload"}):
            return True
    return False


def _scan_scope(
    body: list[ast.stmt], kind: str, path: Path, findings: list[dict[str, object]]
) -> None:
    seen: dict[str, ast.AST] = {}
    for node in body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        node_kind = "shadowed_class" if isinstance(node, ast.ClassDef) else kind
        if (
            node.name in seen
            and not _is_intentional_redefinition(node)
            and not _is_overload_stub(seen[node.name])
        ):
            findings.append(
                {
                    "file": str(path),
                    "line": node.lineno,
                    "kind": node_kind,
                    "name": node.name,
                    "first_line": seen[node.name].lineno,
                }
            )
        else:
            seen.setdefault(node.name, node)


def audit_file(path: Path) -> list[dict[str, object]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        return [
            {
                "file": str(path),
                "line": 1,
                "kind": "parse_error",
                "name": "",
                "first_line": 1,
                "detail": str(exc),
            }
        ]

    findings: list[dict[str, object]] = []
    _scan_scope(tree.body, "shadowed_def", path, findings)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            _scan_scope(node.body, "shadowed_method", path, findings)
        elif isinstance(node, ast.Dict):
            seen: dict[object, int] = {}
            for key_node in node.keys:
                if not isinstance(key_node, ast.Constant):
                    continue  # non-literal / **unpacking keys: not statically comparable
                try:
                    hash(key_node.value)
                except TypeError:
                    # REL-002 (error observability): never swallow silently — the
                    # skip is deliberate, but it must leave a trace when it fires.
                    logger.debug(
                        "Skipping unhashable dict-literal key %r in %s "
                        "(not statically comparable)",
                        key_node.value,
                        path,
                    )
                    continue
                if key_node.value in seen:
                    findings.append(
                        {
                            "file": str(path),
                            "line": key_node.lineno,
                            "kind": "shadowed_dict_key",
                            "name": repr(key_node.value)[:80],
                            "first_line": seen[key_node.value],
                        }
                    )
                else:
                    seen[key_node.value] = key_node.lineno
    return findings


def aggregate(
    findings: list[dict[str, object]],
) -> dict[str, dict[tuple[str, str], int]]:
    """file -> (kind, name) -> occurrence count."""
    per_file: dict[str, Counter] = {}
    for finding in findings:
        key = (str(finding["kind"]), str(finding["name"]))
        per_file.setdefault(str(finding["file"]), Counter())[key] += 1
    return {path: dict(counter) for path, counter in per_file.items()}


def load_baseline(path: Path) -> dict[str, dict[tuple[str, str], int]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries: dict[str, dict[tuple[str, str], int]] = {}
    for file_name, items in data.get("entries", {}).items():
        entries[file_name] = {
            (item["kind"], item["name"]): int(item["count"]) for item in items
        }
    return entries


def compare_against_baseline(
    current: dict[str, dict[tuple[str, str], int]],
    baseline: dict[str, dict[tuple[str, str], int]],
) -> tuple[list[dict[str, object]], list[str]]:
    new_violations: list[dict[str, object]] = []
    improvements: list[str] = []
    for file_name, keys in sorted(current.items()):
        allowed = baseline.get(file_name, {})
        for (kind, name), count in sorted(keys.items()):
            baseline_count = allowed.get((kind, name), 0)
            if count > baseline_count:
                new_violations.append(
                    {
                        "file": file_name,
                        "kind": kind,
                        "name": name,
                        "count": count,
                        "baseline_count": baseline_count,
                        "note": "NEW" if baseline_count == 0 else "COUNT_INCREASED",
                    }
                )
            elif count < baseline_count:
                improvements.append(
                    f"{file_name}: {kind} {name} {baseline_count} -> {count}"
                )
    for file_name, keys in sorted(baseline.items()):
        if file_name not in current:
            improvements.append(
                f"{file_name}: all baseline findings resolved — remove the entry"
            )
        else:
            for (kind, name), count in sorted(keys.items()):
                if (kind, name) not in current[file_name]:
                    improvements.append(
                        f"{file_name}: {kind} {name} resolved — remove from baseline"
                    )
    return new_violations, improvements


def write_baseline(findings: list[dict[str, object]], path: Path) -> None:
    current = aggregate(findings)
    entries: dict[str, list[dict[str, object]]] = {}
    for file_name, keys in sorted(current.items()):
        entries[file_name] = [
            {"kind": kind, "name": name, "count": count}
            for (kind, name), count in sorted(keys.items())
        ]
    payload = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "description": (
            "Known definition-shadowing findings (duplicate defs/classes/methods/dict keys). "
            "Ratchet baseline: CI fails only on findings NOT covered here. Shrink by fixing "
            "findings, then regenerate with --update-baseline. Wire-first: entries include "
            "owner-preserved duplicates (see _tasks.py docstring) — never delete without approval."
        ),
        "entries": entries,
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="ci-reports/definition-shadowing.json")
    parser.add_argument(
        "--baseline",
        default=None,
        help="Gate mode: fail on findings not covered by this ratchet baseline JSON.",
    )
    parser.add_argument(
        "--update-baseline",
        default=None,
        help="Regenerate the baseline file from the current findings and exit.",
    )
    parser.add_argument("roots", nargs="*", default=list(DEFAULT_ROOTS))
    args = parser.parse_args()

    findings = [
        finding
        for path in iter_python_files(tuple(args.roots))
        for finding in audit_file(path)
    ]

    if args.update_baseline:
        write_baseline(findings, Path(args.update_baseline))
        print(
            f"Definition-shadowing baseline updated: {len(findings)} findings -> {args.update_baseline}"
        )
        return 0

    report: dict[str, object] = {
        "roots": args.roots,
        "finding_count": len(findings),
        "findings": findings,
    }
    exit_code = 0

    if args.baseline:
        baseline = load_baseline(Path(args.baseline))
        current = aggregate(findings)
        new_violations, improvements = compare_against_baseline(current, baseline)
        report["status"] = "fail" if new_violations else "pass"
        report["new_violations"] = new_violations
        report["improvements"] = improvements
        exit_code = 1 if new_violations else 0
        print(
            f"Definition-shadowing gate: {len(findings)} findings, {len(new_violations)} NEW (baseline ratchet)"
        )
        for violation in new_violations:
            print(
                f"  NEW: {violation['file']} {violation['kind']} '{violation['name']}' "
                f"x{violation['count']} (baseline allows {violation['baseline_count']})"
            )
        for improvement in improvements:
            print(f"  IMPROVED: {improvement} — consider --update-baseline")
    else:
        report["status"] = "report-only"
        print(f"Definition-shadowing audit: {len(findings)} findings (report-only)")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
