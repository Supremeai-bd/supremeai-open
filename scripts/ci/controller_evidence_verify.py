#!/usr/bin/env python3
"""Controller-side evidence verifier (plan §10.2 item 8).

Does NOT trust a coder's self-report. Verifies:
  - git diff scope (changed files subset of declared scope, no protected paths)
  - SHA-256 digests of changed files (optional, fail-closed on mismatch)
  - controller-run test commands all exit 0

Stdlib-only. Fail-closed: any git/subprocess failure or scope violation -> fail.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROTECTED_PREFIXES = (
    ".env",
    "secrets/",
    "credentials/",
    "vault/",
    ".github/",
    "prisma/",
)
PROTECTED_PATTERNS = (".pem", "credential", "key.p12")


def _run(
    cmd, cwd: Path, timeout: int = 300, shell: bool = False
) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd, cwd=cwd, capture_output=True, timeout=timeout, check=False, shell=shell
        )
        return (
            p.returncode,
            p.stdout.decode("utf-8", errors="replace"),
            p.stderr.decode("utf-8", errors="replace"),
        )
    except Exception as exc:
        return 127, "", str(exc)


def changed_files(base_sha: str, head_sha: str, repo_root: Path) -> list[str] | None:
    """Return list of changed file paths, or None on git failure (fail-closed)."""
    if not base_sha or not head_sha:
        return None
    rc, out, _ = _run(["git", "diff", "--name-only", base_sha, head_sha], repo_root)
    if rc != 0:
        return None
    return [line.strip() for line in out.splitlines() if line.strip()]


def is_protected(path: str) -> bool:
    p = path.replace("\\", "/")
    if any(p.startswith(pref) for pref in PROTECTED_PREFIXES):
        return True
    low = p.lower()
    return any(tok in low for tok in PROTECTED_PATTERNS)


def scope_violations(changed: list[str], scope_paths: list[str]) -> list[str]:
    """Files that are (a) protected, or (b) not in the declared scope (when scope given)."""
    violations: list[str] = []
    scope_set = {s.strip() for s in (scope_paths or []) if s.strip()}
    for f in changed:
        if is_protected(f):
            violations.append(f"protected:{f}")
            continue
        if scope_set and f not in scope_set:
            violations.append(f"out-of-scope:{f}")
    return violations


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def verify_digests(
    repo_root: Path, changed: list[str], expected: dict[str, str]
) -> list[str]:
    """Return list of digest mismatch descriptions (empty == ok)."""
    mismatches: list[str] = []
    for f in changed:
        full = repo_root / f
        if not full.is_file():
            mismatches.append(f"missing:{f}")
            continue
        actual = sha256_file(full)
        if f in expected and expected[f] and expected[f] != actual:
            mismatches.append(f"digest-mismatch:{f}")
    # Also check expected files that were not changed but digests provided.
    for f, exp in (expected or {}).items():
        if exp and f not in changed:
            mismatches.append(f"expected-not-changed:{f}")
    return mismatches


def run_test_commands(commands: list[str], cwd: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for cmd in commands or []:
        rc, _out, err = _run(cmd, cwd, shell=True)
        results.append({"cmd": cmd, "rc": rc, "passed": rc == 0, "stderr": err[:200]})
    return results


def verify(
    base_sha: str,
    head_sha: str,
    scope_paths: list[str] | None,
    expected_digests: dict[str, str] | None,
    test_commands: list[str] | None,
    repo_root: Path,
) -> dict[str, Any]:
    """Full controller-side evidence verification. Fail-closed."""
    result: dict[str, Any] = {
        "passed": False,
        "changed_files": [],
        "scope_violations": [],
        "digest_mismatches": [],
        "test_results": [],
        "errors": [],
    }
    changed = changed_files(base_sha, head_sha, repo_root)
    if changed is None:
        result["errors"].append("git-diff-failed")
        return result
    result["changed_files"] = changed
    if not changed:
        result["errors"].append("no-changed-files")
        return result

    v = scope_violations(changed, scope_paths or [])
    result["scope_violations"] = v
    if v:
        result["errors"].append("scope-violation")

    dm = verify_digests(repo_root, changed, expected_digests or {})
    result["digest_mismatches"] = dm
    if dm:
        result["errors"].append("digest-mismatch")

    tr = run_test_commands(test_commands or [], repo_root)
    result["test_results"] = tr
    if any(not t["passed"] for t in tr):
        result["errors"].append("test-failure")

    result["passed"] = len(result["errors"]) == 0
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Controller-side evidence verifier")
    parser.add_argument("--base", required=True, help="base commit SHA")
    parser.add_argument("--head", required=True, help="head commit SHA")
    parser.add_argument(
        "--scope", default="", help="comma-separated declared scope paths"
    )
    parser.add_argument(
        "--digests", default="", help="path to JSON file of {path: sha256:...}"
    )
    parser.add_argument(
        "--test", action="append", default=[], help="test command (repeatable)"
    )
    parser.add_argument("--repo-root", default=".", help="repository root")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    scope = [s.strip() for s in args.scope.split(",") if s.strip()]
    digests = {}
    if args.digests:
        try:
            digests = json.loads(Path(args.digests).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(
                json.dumps({"passed": False, "errors": [f"digests-load-failed:{exc}"]})
            )
            return 1
    res = verify(args.base, args.head, scope, digests, args.test, root)
    print(json.dumps(res, indent=2, sort_keys=True))
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
