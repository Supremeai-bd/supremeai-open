#!/usr/bin/env python3
"""wiring_integrity_guard.py — wired-but-absent class prevention (#3316).

Root cause it prevents: a wiring commit (a ``run_all_guards.py`` roster entry)
can merge while the implementation script it references still waits in the
gate queue. Live instance 2026-10-30: wiring #3268 merged onto main while the
carrying PR #3257 was still open, so ``run_all_guards.py`` exited 1 on every
run with an obscure ``can't open file`` errno-2 instead of a legible signal.

This guard makes every "roster references a script that does not exist in the
tree" state legible at CI time and actionable: land the carrying PR or remove
the wiring. It never masks a failure (fail-closed): a structural roster
problem or a missing script is a hard non-zero exit.

Modes
-----
``--check``      Validate the LIVE tree's ``scripts/ci/run_all_guards.py`` roster.
``--self-test``  Validate the validator on a synthetic tree inside a temp dir
                 (complete roster must pass; roster with an absent script must
                 fail and name it; malformed roster must be a structural error).

Exit codes: 0 = roster complete (or self-test assertions all held);
1 = at least one wired-but-absent script or a structural error.
Zero third-party dependencies; stdlib only.
"""

from __future__ import annotations

import argparse
import ast
import sys
import tempfile
from pathlib import Path

ROSTER_RELPATH = Path("scripts/ci/run_all_guards.py")
SCRIPT_SUFFIXES = (".py", ".sh")


def _extract_scripts_from_source(source: str) -> tuple[list[str], list[str]]:
    """AST-parse a roster source and return (wired script relpaths, structural errors).

    বাংলা: roster-এ GUARDS নামে module-level list থাকতে হবে; প্রতিটি ভুক্তি
    ["python", "scripts/.../*.py", ...args] আকারে literal হতে হবে। যেকোনো
    গঠনগত সমস্যা structural error — fail-closed, কখনো চুপচাপ পাস নয়।
    """
    errors: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [], [f"roster source is not parseable Python: {exc}"]

    guards_node: ast.expr | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "GUARDS":
                    guards_node = node.value
                    break
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "GUARDS":
                guards_node = node.value
    if guards_node is None:
        return [], ["no module-level GUARDS assignment found in roster"]

    if not isinstance(guards_node, (ast.List, ast.Tuple)):
        return [], ["GUARDS is not a list/tuple literal"]

    scripts: list[str] = []
    for entry in guards_node.elts:
        if not isinstance(entry, (ast.List, ast.Tuple)):
            errors.append("GUARDS contains a non-list entry (expected [interp, script, ...])")
            continue
        for elt in entry.elts:
            if not isinstance(elt, ast.Constant) or not isinstance(elt.value, str):
                continue
            token = elt.value
            if token.startswith("-") or "/" not in token:
                continue  # interpreter, flags, bare names
            if token.endswith(SCRIPT_SUFFIXES):
                scripts.append(token)
    return scripts, errors


def check_tree(repo_root: Path, source: str | None = None) -> tuple[list[str], list[str]]:
    """Return (missing script relpaths, structural errors) for a repo root."""
    roster = repo_root / ROSTER_RELPATH
    if source is None:
        if not roster.is_file():
            return [], [f"roster not found: {ROSTER_RELPATH.as_posix()}"]
        source = roster.read_text(encoding="utf-8")
    scripts, errors = _extract_scripts_from_source(source)
    missing = [s for s in scripts if not (repo_root / s).is_file()]
    return missing, errors


def _self_test() -> int:
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        root_ok = Path(tmp) / "ok"
        (root_ok / "scripts" / "ci").mkdir(parents=True)
        (root_ok / "scripts" / "ci" / "real_guard.py").write_text("# real\n", encoding="utf-8")
        roster_ok = (
            "GUARDS = [\n"
            "    [\"python\", \"scripts/ci/real_guard.py\", \"--self-test\"],\n"
            "]\n"
        )
        (root_ok / ROSTER_RELPATH).write_text(roster_ok, encoding="utf-8")
        missing, errors = check_tree(root_ok)
        if missing or errors:
            failures.append(f"complete roster must pass, got missing={missing} errors={errors}")

    with tempfile.TemporaryDirectory() as tmp:
        root_bad = Path(tmp) / "bad"
        (root_bad / "scripts" / "ci").mkdir(parents=True)
        roster_bad = (
            "GUARDS = [\n"
            "    [\"python\", \"scripts/ci/real_guard.py\", \"--self-test\"],\n"
            "    [\"python\", \"scripts/ci/ghost_guard.py\", \"--self-test\"],\n"
            "]\n"
        )
        (root_bad / ROSTER_RELPATH).write_text(roster_bad, encoding="utf-8")
        (root_bad / "scripts" / "ci" / "real_guard.py").write_text("# real\n", encoding="utf-8")
        missing, errors = check_tree(root_bad)
        if not missing:
            failures.append("roster with an absent script must be caught")
        elif "ghost_guard.py" not in " ".join(missing):
            failures.append(f"failure must name the absent script, got {missing}")
        if errors:
            failures.append(f"well-formed roster must have no structural errors, got {errors}")

    missing, errors = check_tree(Path("/nonexistent-repo-root-for-selftest"))
    if errors != ["roster not found: scripts/ci/run_all_guards.py"]:
        failures.append(f"missing roster file must be a structural error, got {errors}")

    _, errors = _extract_scripts_from_source("NOT_A_LIST = 1\n")
    if not any("GUARDS" in e for e in errors):
        failures.append(f"roster without GUARDS must be a structural error, got {errors}")

    _, errors = _extract_scripts_from_source("GUARDS = 'oops'\n")
    if not any("list/tuple" in e for e in errors):
        failures.append(f"non-list GUARDS must be a structural error, got {errors}")

    if failures:
        for f in failures:
            print(f"SELF-TEST FAIL: {f}")
        return 1
    print("wiring_integrity_guard self-test: 5/5 assertions held")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Wired-but-absent roster integrity guard (#3316)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="validate the live tree roster")
    mode.add_argument("--self-test", action="store_true", help="validate the validator (synthetic tree)")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    repo_root = Path(__file__).resolve().parents[2]
    missing, errors = check_tree(repo_root)
    scripts, _ = _extract_scripts_from_source(
        (repo_root / ROSTER_RELPATH).read_text(encoding="utf-8")
    )
    print(f"wiring_integrity_guard: roster {ROSTER_RELPATH.as_posix()} wires {len(scripts)} script(s)")
    for error in errors:
        print(f"STRUCTURAL ERROR: {error}")
    for script in scripts:
        state = "ok" if script not in missing else "WIRED-BUT-ABSENT"
        print(f"  [{state}] {script}")
    if missing:
        print(
            "wired-but-absent scripts found: land the carrying PR or remove the wiring "
            "(root cause #3316: wiring must not outrun implementation)"
        )
        return 1
    if errors:
        return 1
    print("wiring_integrity_guard --check: PASS (roster complete)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
