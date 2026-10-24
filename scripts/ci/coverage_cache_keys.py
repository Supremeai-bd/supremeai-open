#!/usr/bin/env python3
"""Per-group coverage cache keys (issue #471 — persistence layer for #470).

বাংলা: #470-এর scoped mode সৎভাবে চালু করতে প্রতিটি ম্যাট্রিক্স গ্রুপের
`.coverage.<group>` ডেটা ফাইল cache করা হয়, এই কী দিয়ে। কী-এর সব
উপাদান byte-identical হলে coverage union-ও identical — তাই cache থেকে
আসা ডেটা দিয়ে coverage gate-এর combined numerator হুবহু একই থাকে
(fail-closed চুক্তি অক্ষত — incident PR #343)।

Cache key contract (all components must capture every input that can
change a group's `.coverage` output):

  key = bcov-v1-<group>-sha256(
      measured_source_hash    # backend/{core,api,services,tools,runs,memory}/**
      + pyproject_hash        # backend/pyproject.toml (pytest/addopts/cov config)
      + lock_hash             # backend/poetry.lock (dependency versions)
      + root_conftest_hash    # backend/tests/conftest.py (global fixtures)
      + group_scope_hash      # the group's resolved test-file set (incl.
  )                           #   any conftest.py inside those dirs)

Honesty properties (DO NOT weaken):
- Same inputs → byte-identical `.coverage.<group>` → the aggregate's
  `coverage combine` sees exactly the numerator a fresh run would produce.
  This is ccache-style reuse over identical inputs, NOT sampling.
- Any change under measured packages / pyproject / lock / root conftest
  changes EVERY group's key (invalidate-all) — matching the planner's
  CORE_TRIGGER contract, so such diffs always run fresh (full mode).
- The hash covers file CONTENTS, not mtimes → stable across checkouts.

Non-goals: this module never reads or writes the cache itself; it only
computes keys. ci.yml's actions/cache steps own persistence.

Usage (planner job):
  python scripts/ci/coverage_cache_keys.py --all --json-out keys.json
Usage (debug one group):
  python scripts/ci/coverage_cache_keys.py --group fast --explain
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

# MUST mirror the pytest --cov list in ci.yml (coverage gate tiers match
# coverage_policy.yaml globs against these packages). Adding a package to
# --cov without adding it here = stale cached numerators. A unit test locks
# the equivalence.
MEASURED_PACKAGES = ("core", "api", "services", "tools", "runs", "memory")

# Files whose content participates in every group's key (test-behavior
# configuration shared by all groups).
GLOBAL_INPUT_FILES = (
    Path("pyproject.toml"),
    Path("poetry.lock"),
    Path("tests") / "conftest.py",
)

KEY_PREFIX = "bcov-v1"

_SKIP_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
_SKIP_SUFFIXES = (".pyc", ".pyo", ".orig", ".rej")


def _file_sha256(path: Path) -> str:
    """sha256 of file bytes; unreadable files hash their path (never crash)."""
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 16), b""):
                digest.update(chunk)
    except OSError:
        digest.update(str(path).encode("utf-8", errors="replace"))
    return digest.hexdigest()


def _iter_repo_files(root: Path) -> list[Path]:
    """All files under root (any type), skipping caches/scratch artifacts."""
    files: list[Path] = []
    if root.is_file():
        return [root]
    if not root.is_dir():
        return []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        for name in sorted(filenames):
            if name.endswith(_SKIP_SUFFIXES):
                continue
            files.append(Path(dirpath) / name)
    return files


def _hash_file_set(backend_root: Path, files: list[Path]) -> str:
    """Content+path hash over a file set (order-independent, mtime-blind)."""
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda p: str(p)):
        rel = str(path.relative_to(backend_root)).replace(os.sep, "/")
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_file_sha256(path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def global_component_hashes(backend_root: Path = BACKEND_ROOT) -> dict[str, str]:
    """Hashes shared by every group: measured source + config files."""
    measured_files: list[Path] = []
    for package in MEASURED_PACKAGES:
        measured_files.extend(_iter_repo_files(backend_root / package))
    components: dict[str, str] = {
        "measured_source": _hash_file_set(backend_root, measured_files),
    }
    for rel in GLOBAL_INPUT_FILES:
        path = backend_root / rel
        if path.is_file():
            components[rel.as_posix()] = _file_sha256(path)
        else:
            components[rel.as_posix()] = "absent"
    return components


def parse_group_tokens(paths_str: str) -> tuple[list[str], list[str]]:
    """Split a group's pytest paths string into (includes, ignores).

    Includes are the verbatim tokens (`tests/core`, `tests/test_*.py`,
    `tests/core/test_x.py`); ignores are the `--ignore=` values. Glob
    detection is left to the resolver (any token containing `*`).
    """
    includes: list[str] = []
    ignores: list[str] = []
    for token in paths_str.split():
        if token.startswith("--ignore="):
            ignores.append(token.removeprefix("--ignore=").replace("\\", "/"))
        elif token:
            includes.append(token.replace("\\", "/"))
    return includes, ignores


def resolve_group_scope(backend_root: Path, paths_str: str) -> list[Path]:
    """Resolve a group's pytest paths string to its concrete file set.

    Mirrors what pytest would collect as INPUT FILES for the group:
    plain dirs are walked (all files, cache artifacts skipped), plain
    files are taken directly, and glob tokens are expanded relative to
    backend/. `--ignore=` values prune matching paths everywhere.

    pytest semantics: a `conftest.py` applies to its own directory AND
    everything below it — so every ancestor conftest between backend/tests
    and each scope path is part of the group's behavioral input and is
    included (tests/conftest.py is already a global component; including
    it again is harmless). Missing this would let a fixture change slip
    through a cache hit and silently shift the gate numerator.
    """
    includes, ignores = parse_group_tokens(paths_str)

    def ignored(rel: str) -> bool:
        return any(
            rel == ign or rel.startswith(ign.rstrip("/") + "/") for ign in ignores
        )

    tests_root = (backend_root / "tests").resolve()
    files: set[Path] = set()

    def add_with_ancestor_conftests(path: Path) -> None:
        files.add(path)
        parent = path.parent
        while True:
            conftest = parent / "conftest.py"
            if conftest.is_file():
                files.add(conftest)
            if parent == tests_root or tests_root not in parent.parents:
                break
            parent = parent.parent

    for token in includes:
        path = (backend_root / token).resolve()
        if any(ch in token for ch in "*?["):
            parent = path.parent
            for hit in sorted(parent.glob(path.name)) if parent.is_dir() else []:
                if hit.is_file():
                    rel = hit.relative_to(backend_root).as_posix()
                    if not ignored(rel):
                        add_with_ancestor_conftests(hit)
            continue
        if path.is_file():
            rel = path.relative_to(backend_root).as_posix()
            if not ignored(rel):
                add_with_ancestor_conftests(path)
        elif path.is_dir():
            for file_path in _iter_repo_files(path):
                rel = file_path.relative_to(backend_root).as_posix()
                if not ignored(rel):
                    files.add(file_path)
            # Directory walk: still capture ancestor conftests above the
            # walked dir (tests/core/conftest.py governs tests/core/**).
            add_with_ancestor_conftests(path)
    return sorted(files, key=lambda p: str(p))


def group_cache_key(
    group_key: str,
    paths_str: str,
    backend_root: Path = BACKEND_ROOT,
    component_hashes: dict[str, str] | None = None,
) -> str:
    """Stable cache key for one group's `.coverage.<group>` artifact."""
    if component_hashes is None:
        component_hashes = global_component_hashes(backend_root)
    scope_files = resolve_group_scope(backend_root, paths_str)
    scope_hash = _hash_file_set(backend_root, scope_files)
    digest = hashlib.sha256()
    digest.update(KEY_PREFIX.encode("ascii"))
    digest.update(b"\0")
    for name in sorted(component_hashes):
        digest.update(name.encode("utf-8"))
        digest.update(b"=")
        digest.update(component_hashes[name].encode("ascii"))
        digest.update(b"\0")
    digest.update(b"group_scope=")
    digest.update(scope_hash.encode("ascii"))
    return f"{KEY_PREFIX}-{group_key}-{digest.hexdigest()[:32]}"


def compute_all_group_keys(backend_root: Path = BACKEND_ROOT) -> dict[str, str]:
    """Keys for every planner group; caller maps group key → matrix name."""
    # Imported lazily to keep this module dependency-free from the planner
    # (the planner imports THIS module; a top-level cycle would break both).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import plan_backend_test_groups as planner  # noqa: PLC0415

    components = global_component_hashes(backend_root)
    return {
        key: group_cache_key(key, paths, backend_root, components)
        for key, (_, paths) in planner.GROUPS.items()
    }


def _explain(backend_root: Path, group_key: str, paths_str: str) -> str:
    components = global_component_hashes(backend_root)
    scope_files = resolve_group_scope(backend_root, paths_str)
    lines = [
        f"group: {group_key}",
        *(f"  {name}: {value[:16]}…" for name, value in sorted(components.items())),
        f"  group_scope: {len(scope_files)} files",
        group_cache_key(group_key, paths_str, backend_root, components),
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Per-group coverage cache keys (issue #471)."
    )
    parser.add_argument("--backend-root", type=Path, default=BACKEND_ROOT)
    parser.add_argument("--group", help="Explain a single group's key")
    parser.add_argument(
        "--all", action="store_true", help="Print cache_key_<group>=… lines"
    )
    parser.add_argument("--json-out", type=Path, help="Also write JSON {group: key}")
    args = parser.parse_args()

    backend_root: Path = args.backend_root
    if args.group:
        sys_path = sys.path[:]
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import plan_backend_test_groups as planner  # noqa: PLC0415

        sys.path = sys_path
        if args.group not in planner.GROUPS:
            print(f"unknown group: {args.group}", file=sys.stderr)
            return 1
        _, paths = planner.GROUPS[args.group]
        print(_explain(backend_root, args.group, paths))
        return 0

    keys = compute_all_group_keys(backend_root)
    for key, value in keys.items():
        print(f"cache_key_{key}={value}")
    if args.json_out:
        args.json_out.write_text(
            json.dumps(keys, indent=2, sort_keys=True), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
