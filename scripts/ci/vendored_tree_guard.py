#!/usr/bin/env python3
"""S11 — Vendored-Tree Sanitization Guard (issue #498, criterion 1).

Machine-enforces the Zero-Bloat & Lightweight Satellite Doctrine: PRs that
add large 3rd-party vendored trees are FLAGGED by CI before landing.

Deterministic, fail-closed rules over the structured PR file list
(``{path, bytes}`` records — produced by the pipeline from ``git diff
--numstat``; no free-text analysis):

  R1  vendored directory paths  — vendor/, third_party/, node_modules/,
      bowel_components-free bower_components/, .venv bundles
  R2  oversize single additions — one added file above
      VENDORED_FILE_MAX_BYTES
  R3  mass-file new directory   — more than VENDORED_TREE_FILE_COUNT new
      files under one first-level directory
  R4  lockfile additions        — package-lock.json / yarn.lock /
      poetry.lock / Cargo.lock / Pipfile.lock added as NEW files
  R5  total mass addition       — sum of added bytes above
      VENDORED_TREE_MAX_TOTAL_BYTES

Exit codes: 0 = clean, 2 = vendored-tree violation (fail-closed on
malformed input as well). Any single violation lists every offending
record; the guard never passes partially.

Pure stdlib. Run: python3 scripts/ci/vendored_tree_guard.py --self-test
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

VENDORED_DIR_MARKERS: Final = (
    "/vendor/",
    "/third_party/",
    "/node_modules/",
    "/bower_components/",
    "/vendors/",
)
VENDORED_DIR_ROOTS: Final = (
    "vendor/",
    "third_party/",
    "node_modules/",
    "bower_components/",
    "vendors/",
)
VENDORED_FILE_MAX_BYTES: Final = 512 * 1024  # 512 KiB single file
VENDORED_TREE_FILE_COUNT: Final = 50  # files per new top dir
VENDORED_TREE_MAX_TOTAL_BYTES: Final = 2 * 1024 * 1024  # 2 MiB total
LOCKFILE_NAMES: Final = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "Cargo.lock",
        "Pipfile.lock",
        "composer.lock",
    }
)
OVERSIZE_LIBRARY_SUFFIXES: Final = (
    ".jar",
    ".war",
    ".wasm",
    ".node",
    ".so",
    ".dll",
    ".dylib",
    ".a",
    ".lib",
)

EXIT_CLEAN: Final = 0
EXIT_VIOLATION: Final = 2


@dataclass(frozen=True)
class AddedFile:
    path: str
    bytes: int


@dataclass(frozen=True)
class GuardVerdict:
    exit_code: int
    violations: tuple[str, ...]
    offending_paths: tuple[str, ...]


def _is_vendored_path(path: str) -> bool:
    normalized = "/" + path.replace("\\", "/").lstrip("/")
    return any(marker in normalized for marker in VENDORED_DIR_MARKERS) or any(
        normalized.startswith("/" + root) for root in VENDORED_DIR_ROOTS
    )


def _top_dir(path: str) -> str:
    parts = path.replace("\\", "/").split("/")
    return parts[0] if len(parts) > 1 else "(root)"


def guard_added_files(files: Sequence[AddedFile]) -> GuardVerdict:
    """Run R1-R5 over the added-file list. Deterministic, fail-closed."""
    violations: list[str] = []
    offenders: set[str] = set()

    vendored = [f for f in files if _is_vendored_path(f.path)]
    if vendored:
        violations.append(f"R1 vendored directory paths: {len(vendored)} file(s)")
        offenders.update(f.path for f in vendored)

    oversize = [
        f
        for f in files
        if f.bytes > VENDORED_FILE_MAX_BYTES
        or f.path.lower().endswith(OVERSIZE_LIBRARY_SUFFIXES)
    ]
    if oversize:
        violations.append(
            f"R2 oversize/binary library additions: {[f.path for f in oversize]}"
        )
        offenders.update(f.path for f in oversize)

    by_top: Mapping[str, list[AddedFile]] = {}
    for f in files:
        by_top.setdefault(_top_dir(f.path), []).append(f)
    for top, group in sorted(by_top.items()):
        if len(group) > VENDORED_TREE_FILE_COUNT:
            violations.append(
                f"R3 mass addition under {top!r}: {len(group)} new files "
                f"(limit {VENDORED_TREE_FILE_COUNT})"
            )
            offenders.update(f.path for f in group)

    lockfiles = [
        f for f in files if f.path.replace("\\", "/").split("/")[-1] in LOCKFILE_NAMES
    ]
    if lockfiles:
        violations.append(
            f"R4 dependency lockfile additions: "
            f"{[f.path for f in lockfiles]} — vendoring manifests are "
            "prohibited; surgical extraction needs no dependency tree"
        )
        offenders.update(f.path for f in lockfiles)

    total = sum(f.bytes for f in files)
    if total > VENDORED_TREE_MAX_TOTAL_BYTES:
        violations.append(
            f"R5 total added mass {total} bytes exceeds "
            f"{VENDORED_TREE_MAX_TOTAL_BYTES} — extract the Gold Pearl, "
            "not the repository"
        )
        offenders.update(f.path for f in files)

    return GuardVerdict(
        exit_code=EXIT_VIOLATION if violations else EXIT_CLEAN,
        violations=tuple(violations),
        offending_paths=tuple(sorted(offenders)),
    )


def _parse_records(raw: str) -> list[AddedFile]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"EXIT_VIOLATION: malformed files payload: {exc}")
        raise SystemExit(EXIT_VIOLATION)
    if not isinstance(payload, list):
        print("EXIT_VIOLATION: files payload must be a JSON list")
        raise SystemExit(EXIT_VIOLATION)
    parsed: list[AddedFile] = []
    for item in payload:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or not isinstance(item.get("bytes"), int)
            or item["bytes"] < 0
        ):
            print("EXIT_VIOLATION: each record needs {path: str, bytes: int}")
            raise SystemExit(EXIT_VIOLATION)
        parsed.append(AddedFile(path=item["path"], bytes=item["bytes"]))
    return parsed


def self_test() -> bool:
    clean = guard_added_files(
        [
            AddedFile("scripts/agents/scout_extractor.py", 9000),
            AddedFile("tests/test_s11_surgical_adoption.py", 7000),
            AddedFile("docs/S11_SURGICAL_ADOPTION_SPEC.md", 8000),
        ]
    )
    assert clean.exit_code == EXIT_CLEAN and not clean.violations

    cases: tuple[tuple[list[AddedFile], str], ...] = (
        ([AddedFile("vendor/lib/foo.py", 100)], "R1"),
        ([AddedFile("src/node_modules/left-pad/index.js", 10)], "R1"),
        ([AddedFile("third_party/engine/core.py", 10)], "R1"),
        ([AddedFile("src/blob.jar", 100)], "R2"),
        ([AddedFile("src/huge.bin", VENDORED_FILE_MAX_BYTES + 1)], "R2"),
        (
            [
                AddedFile(f"newpkg/mod{i}.py", 10)
                for i in range(VENDORED_TREE_FILE_COUNT + 1)
            ],
            "R3",
        ),
        ([AddedFile("package-lock.json", 400)], "R4"),
        ([AddedFile("web/yarn.lock", 400)], "R4"),
        ([AddedFile(f"f{i}.py", 300 * 1024) for i in range(8)], "R5"),
    )
    for files, rule in cases:
        verdict = guard_added_files(files)
        assert verdict.exit_code == EXIT_VIOLATION, (rule, verdict)
        assert any(v.startswith(rule) for v in verdict.violations), (rule, verdict)
        assert verdict.offending_paths

    # Boundary: exactly at the limits is clean.
    edge_files = [AddedFile("ok.bin", VENDORED_FILE_MAX_BYTES)]
    edge_files += [
        AddedFile(f"pkg/mod{i}.py", 10) for i in range(VENDORED_TREE_FILE_COUNT)
    ]
    edge_files.append(AddedFile("tail.py", 400 * 1024))  # ≤ per-file cap
    edge = guard_added_files(edge_files)
    assert edge.exit_code == EXIT_CLEAN, edge

    # Empty PR is clean.
    assert guard_added_files([]).exit_code == EXIT_CLEAN
    return True


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--files-json",
        help="inline JSON list of {path, bytes} records; omit to read stdin",
    )
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("SELF-TEST OK: vendored_tree_guard")
        return EXIT_CLEAN
    raw = args.files_json if args.files_json else sys.stdin.read()
    verdict = guard_added_files(_parse_records(raw))
    for violation in verdict.violations:
        print(f"VIOLATION {violation}")
    if verdict.violations:
        print("VENDORED-TREE GUARD: BLOCKED (fail-closed)")
        return EXIT_VIOLATION
    print("VENDORED-TREE GUARD: clean")
    return EXIT_CLEAN


if __name__ == "__main__":
    raise SystemExit(_cli())
