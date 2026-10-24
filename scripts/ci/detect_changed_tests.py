#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
TESTS_DIR = BACKEND_DIR / "tests"


def get_git_diff_files(base: str | None = None) -> list[str]:
    try:
        if base and base.strip():
            verify = subprocess.run(
                ["git", "rev-parse", "--verify", base],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            if verify.returncode != 0:
                base = None
        if not base:
            for candidate in ["origin/main", "origin/develop", "HEAD~1"]:
                res = subprocess.run(
                    ["git", "rev-parse", "--verify", candidate],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                )
                if res.returncode == 0:
                    base = candidate
                    break

        if not base:
            return []

        cmd = ["git", "diff", "--name-only", f"{base}...HEAD"]
        res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
        if res.returncode != 0:
            cmd = ["git", "diff", "--name-only", base]
            res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)

        if res.returncode == 0:
            return [line.strip() for line in res.stdout.splitlines() if line.strip()]
    except Exception as e:
        print(f"Error getting git diff: {e}", file=sys.stderr)
    return []


def map_file_to_tests(file_path: str) -> list[str]:
    rel = file_path.replace(chr(92), "/")
    if rel.startswith("backend/tests/"):
        test_subpath = rel[len("backend/") :]
        if (BACKEND_DIR / test_subpath).exists():
            return [test_subpath]
        return []

    if not rel.startswith("backend/"):
        return []

    backend_rel = rel[len("backend/") :]
    stem = Path(backend_rel).stem

    matched_tests: list[str] = []
    for test_file in TESTS_DIR.rglob(f"test_{stem}.py"):
        matched_tests.append(
            str(test_file.relative_to(BACKEND_DIR)).replace(chr(92), "/")
        )

    parts = Path(backend_rel).parts
    if len(parts) >= 2:
        folder = parts[0]
        subfolder = parts[1]
        target_dir = TESTS_DIR / folder / subfolder
        if target_dir.exists() and target_dir.is_dir():
            matched_tests.append(
                str(target_dir.relative_to(BACKEND_DIR)).replace(chr(92), "/")
            )
        else:
            folder_dir = TESTS_DIR / folder
            if folder_dir.exists() and folder_dir.is_dir():
                matched_tests.append(
                    str(folder_dir.relative_to(BACKEND_DIR)).replace(chr(92), "/")
                )

    return matched_tests


def should_run_full_suite(changed_files: list[str]) -> bool:
    core_triggers = {
        "backend/pyproject.toml",
        "backend/poetry.lock",
        "backend/tests/conftest.py",
        "backend/core/config.py",
        "backend/core/app.py",
        "backend/main.py",
        "backend/database/session.py",
        ".github/workflows/ci.yml",
    }
    for f in changed_files:
        norm = f.replace(chr(92), "/")
        if norm in core_triggers:
            return True
        if norm.startswith("backend/migrations/"):
            return True
        # FIX (coverage-gate collapse, 2026-09-14): targeted mode used to accept
        # ANY backend source change via the test_<stem>.py name heuristic. Groups
        # with no name-matched tests then ran ZERO tests and uploaded EMPTY
        # coverage artifacts, so the Backend Aggregate Gate combined a collapsed
        # numerator (critical 64.72% -> 21.68%) and failed the PR. The tiered
        # gate requires honest per-group coverage on every backend-affecting
        # PR, so any backend change (source OR tests) escalates to the full
        # critical/important tier. Targeted mode stays available for
        # frontend/docs/infra-only PRs, which never enter the backend matrix.
        if norm.startswith("backend/"):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect changed and previously failed tests."
    )
    parser.add_argument(
        "--base", default=None, help="Base git reference or commit SHA to diff against"
    )
    parser.add_argument(
        "--is-main", action="store_true", help="Whether running on main branch"
    )
    parser.add_argument(
        "--previous-failed",
        default="",
        help="Flag or list from detect-previous-failures",
    )
    args = parser.parse_args()

    if args.is_main:
        print("Running on main branch: standard full test suite applied.")
        targets = "tests/"
        markers = "not requires_network and not e2e and not chaos"
        is_targeted = "false"
    elif args.previous_failed and args.previous_failed.lower() == "true":
        print(
            "Previous run failed for backend: running standard critical/important suite."
        )
        targets = "tests/"
        markers = (
            "(critical or important) and not requires_network and not e2e and not chaos"
        )
        is_targeted = "false"
    else:
        changed_files = get_git_diff_files(args.base)
        print(f"Changed files count: {len(changed_files)}")
        for f in changed_files[:10]:
            print(f"  - {f}")
        if len(changed_files) > 10:
            print(f"  ... and {len(changed_files) - 10} more")

        if not changed_files or should_run_full_suite(changed_files):
            print(
                "Changes include core files or empty diff: running standard critical/important suite."
            )
            targets = "tests/"
            markers = "(critical or important) and not requires_network and not e2e and not chaos"
            is_targeted = "false"
        else:
            selected_tests = set()
            for f in changed_files:
                for t in map_file_to_tests(f):
                    selected_tests.add(t)

            if selected_tests:
                targets = " ".join(sorted(selected_tests))
                markers = "not requires_network and not e2e and not chaos"
                is_targeted = "true"
                print(f"Intelligent target test paths: {targets}")
            else:
                # FIX (aggregate-gate collapse, 2026-09-15): this fallback used
                # `critical` alone while still running the FULL group paths.
                # The Backend Aggregate Gate's coverage thresholds (critical 60,
                # important 38) are calibrated on the honest full-suite run of
                # BOTH tiers (measured 63.11% / 45.27%), so a critical-only run
                # collapses the combined numerator (real incident: PR #343 —
                # 213/2257 core + 15/1799 services selected, critical tier
                # 47.59% < 60) and fails every PR whose merge-base diff carries
                # no backend/ files (e.g. scripts/docs PRs that still trigger
                # the backend matrix via path filters). Use the same tier
                # expression as the full-suite branch: the resulting run is the
                # calibrated tier suite, which the gate can evaluate honestly.
                print(
                    "No direct backend module tests mapped: falling back to "
                    "the (critical or important) tier suite."
                )
                targets = "tests/"
                markers = (
                    "(critical or important) "
                    "and not requires_network and not e2e and not chaos"
                )
                is_targeted = "false"

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"test_targets={targets}\n")
            f.write(f"test_markers={markers}\n")
            f.write(f"test_targeted={is_targeted}\n")
    else:
        print(f"OUTPUT: test_targets={targets}")
        print(f"OUTPUT: test_markers={markers}")
        print(f"OUTPUT: test_targeted={is_targeted}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
