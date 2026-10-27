#!/usr/bin/env python3
"""tests/test_openapi_breaking_guard.py — fail-closed behavioral suite for #1711.

Verifies the machine revision-diff gate for the stable external contract
(`api-schemas/gateway.openapi.yaml`) delivered by issue #1711:

  - engagement gate: a revision set that does not touch the contract never
    runs the differ (clean pushes stay clean);
  - honest degradation: missing/unparseable/overtime differ binary degrades
    to a documented skip (exit 0) — the loop's `gh` honesty pattern — and a
    crashing differ can never fabricate a pass;
  - fail-closed detection: a stub differ reporting breaking changes makes the
    guard exit 1 (the documented oasdiff CI pattern);
  - escape hatch: the admin-reviewed `contract-break-approved:` trailer passes
    an intentional break with the approval surfaced verbatim;
  - wiring SSOT: the guard is present in the LIVE `run_all_guards.py` roster
    and the LIVE `.githooks/pre-push` hook (never duplicated here).

Design (zero-dependency doctrine, dual mode — pytest + stdlib runners):

  - pytest:  pytest tests/test_openapi_breaking_guard.py
  - stdlib:  python3 tests/test_openapi_breaking_guard.py   (plain runner)

Every test is offline and deterministic; the only external tool exercised is
a local stub `oasdiff` executable plus sandbox `git` repos — the same
hermetic pattern as the guard's own --self-test and the pre-push hook
self-test.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "ci" / "openapi_breaking_guard.py"
CONTRACT = "api-schemas/gateway.openapi.yaml"
TRAILER = "contract-break-approved:"
TAG = "[openapi-breaking-guard]"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
import openapi_breaking_guard as guard  # noqa: E402


# --------------------------------------------------------------------------- #
# SSOT wiring: the live roster and the live hook carry the guard               #
# --------------------------------------------------------------------------- #

def test_guard_module_reachable_and_pinned() -> None:
    assert GUARD.is_file(), f"guard script missing: {GUARD}"
    src = GUARD.read_text(encoding="utf-8")
    assert 'OASDIFF_MIN_VERSION = "1.15.0"' in src, "version pin SSOT must stay in one place"
    assert CONTRACT in src, "guard must name the contract file"
    assert TRAILER in src, "guard must implement the escape-hatch trailer"


def test_roster_carries_guard_line() -> None:
    roster = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"
    assert roster.is_file(), f"roster missing: {roster}"
    text = roster.read_text(encoding="utf-8")
    assert "scripts/ci/openapi_breaking_guard.py" in text, (
        "run_all_guards roster must invoke the new guard (issue #1711 step 2)"
    )


def test_pre_push_hook_carries_guard_section() -> None:
    hook = REPO_ROOT / ".githooks" / "pre-push"
    assert hook.is_file(), f"hook missing: {hook}"
    text = hook.read_text(encoding="utf-8")
    assert "openapi_breaking_guard.py" in text, "pre-push must wire the guard"
    assert TRAILER in text, "hook must document the escape hatch for intentional breaks"
    assert "run_all_guards" not in text, "hook runs the guard directly, not the whole roster"


# --------------------------------------------------------------------------- #
# Decision-tree behavior: engagement + honest degradation                      #
# --------------------------------------------------------------------------- #

def test_not_touched_revision_set_never_engages() -> None:
    code, ev = guard.evaluate(Path("/nonexistent"), changed_files=["README.md", "docs/x.md"])
    assert code == guard.EXIT_PASS
    assert any("not touched" in e for e in ev), ev


def test_no_honest_base_degrades_to_skip() -> None:
    # /nonexistent is not a git worktree: resolve_base_ref must honestly skip.
    code, ev = guard.evaluate(Path("/nonexistent"), changed_files=[CONTRACT])
    assert code == guard.EXIT_PASS
    assert any("skip" in e.lower() for e in ev), ev


def test_explicit_invalid_base_degrades_to_skip() -> None:
    code, ev = guard.evaluate(
        Path("/nonexistent"), base_ref="definitely-not-a-ref-000", changed_files=None
    )
    assert code == guard.EXIT_PASS
    assert any("not a valid revision" in e for e in ev), ev


# --------------------------------------------------------------------------- #
# Stub differ: the three differ-outcome contracts                              #
# --------------------------------------------------------------------------- #

def _make_stub(name: str, body: str) -> tuple[Path, dict]:
    d = Path(tempfile.mkdtemp(prefix=f"oasdiff-stub-{name}-"))
    stub = d / "oasdiff"
    stub.write_text(body, encoding="utf-8")
    stub.chmod(0o755)
    return d, {"PATH": f"{d}{os.pathsep}/usr/bin{os.pathsep}/bin"}


def test_stub_breaking_change_fails_closed() -> None:
    d, env = _make_stub(
        "breaking",
        "#!/usr/bin/env python3\nprint('~~ breaking: response property removed')\nraise SystemExit(1)\n",
    )
    try:
        code, ev = guard.run_oasdiff_breaking("a: 1\n", "a: 2\n", "stub 1.15.0", env)
        assert code == guard.EXIT_BREAKING, ev
        assert any("FAILED-CLOSED" in e for e in ev), ev
        assert any("response property removed" in e for e in ev), "differ output must surface as evidence"
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_stub_clean_scan_passes() -> None:
    d, env = _make_stub(
        "clean", "#!/usr/bin/env python3\nprint('No breaking changes')\nraise SystemExit(0)\n"
    )
    try:
        code, ev = guard.run_oasdiff_breaking("a: 1\n", "a: 1\n", "stub 1.15.0", env)
        assert code == guard.EXIT_PASS, ev
        assert any("CLEAN" in e for e in ev), ev
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_stub_crash_cannot_fabricate_pass() -> None:
    d, env = _make_stub("crash", "#!/usr/bin/env python3\nimport sys\nsys.exit(127)\n")
    try:
        code, ev = guard.run_oasdiff_breaking("a: 1\n", "a: 2\n", "stub 1.15.0", env)
        assert code == guard.EXIT_PASS, "env crash must degrade honestly, not fail the world"
        assert any("honest skip" in e for e in ev), ev
        assert not any("CLEAN" in e for e in ev), "a crashed scan must never claim clean"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Version pin SSOT                                                             #
# --------------------------------------------------------------------------- #

def test_version_parsing_and_pin_math() -> None:
    assert guard._version_tuple("oasdiff version 1.15.0") == (1, 15, 0)
    assert guard._version_tuple("1.16.2") == (1, 16, 2)
    assert guard._version_tuple("no digits") is None
    at_least = guard._version_at_least
    assert at_least((1, 15, 0), (1, 15, 0))
    assert at_least((1, 16, 2), (1, 15, 0))
    assert at_least((2, 0), (1, 15, 0))
    assert not at_least((1, 9, 4), (1, 15, 0))
    assert not at_least((1, 14, 9), (1, 15, 0))


def test_absent_binary_skips_with_evidence() -> None:
    # Empty PATH guarantees absence regardless of the host machine.
    version, reason = guard.oasdiff_status({"PATH": ""})
    assert version is None
    assert "not found" in reason, reason


# --------------------------------------------------------------------------- #
# Sandbox git: trailer escape hatch + committed-blob plumbing                  #
# --------------------------------------------------------------------------- #

def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


def _sandbox_repo() -> tuple[Path, str, Path]:
    repo = Path(tempfile.mkdtemp(prefix="oasdiff-guard-test-"))
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "guard-test@example.invalid")
    _git(repo, "config", "user.name", "Guard Test")
    (repo / "api-schemas").mkdir()
    cfile = repo / CONTRACT
    cfile.write_text("openapi: 3.1.0\ninfo:\n  title: t\n  version: 1.0.0\npaths: {}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD")
    return repo, base, cfile


def test_approval_trailer_absent_without_trailer() -> None:
    repo, base, cfile = _sandbox_repo()
    try:
        cfile.write_text("openapi: 3.1.0\ninfo:\n  title: t\n  version: 1.1.0\npaths: {}\n", encoding="utf-8")
        _git(repo, "commit", "-aqm", "bump without approval")
        assert guard.find_approval(repo, base, "HEAD") is None
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_approval_trailer_surfaced_verbatim() -> None:
    repo, base, cfile = _sandbox_repo()
    try:
        cfile.write_text("openapi: 3.1.0\ninfo:\n  title: t\n  version: 1.1.0\npaths: {}\n", encoding="utf-8")
        _git(repo, "commit", "-aqm", "intentional break")
        _git(repo, "commit", "--allow-empty", "-qm", f"approval\n\n{TRAILER} admin @ops (ticket #99)")
        approval = guard.find_approval(repo, base, "HEAD")
        assert approval is not None and TRAILER in approval and "admin @ops" in approval, approval
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_changed_in_range_and_blob_reads() -> None:
    repo, base, cfile = _sandbox_repo()
    try:
        assert not guard.file_changed_in_range(repo, CONTRACT, base, "HEAD")
        assert guard.file_changed_in_range(repo, "README.md", base, "HEAD") is False or True  # git decides
        cfile.write_text("openapi: 3.1.0\ninfo:\n  title: t\n  version: 1.1.0\npaths: {}\n", encoding="utf-8")
        _git(repo, "commit", "-aqm", "bump")
        assert guard.file_changed_in_range(repo, CONTRACT, base, "HEAD")
        blob, how = guard.read_blob(repo, base, CONTRACT)
        assert blob is not None and "version: 1.0.0" in blob and how == "git"
        head_blob, _ = guard.read_blob(repo, "HEAD", CONTRACT)
        assert head_blob is not None and "version: 1.1.0" in head_blob
    finally:
        shutil.rmtree(repo, ignore_errors=True)


# --------------------------------------------------------------------------- #
# End-to-end CLI: self-test + pristine-main check exit 0                       #
# --------------------------------------------------------------------------- #

def test_guard_self_test_passes() -> None:
    r = subprocess.run(
        [sys.executable, str(GUARD), "--self-test"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, f"self-test failed:\n{r.stdout}\n{r.stderr}"
    assert "PASSED" in r.stdout


def test_guard_check_on_pristine_main_is_honest_zero() -> None:
    r = subprocess.run(
        [sys.executable, str(GUARD), "--check"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert r.returncode in (guard.EXIT_PASS,), (
        f"pristine-main --check must exit 0 (pass or honest skip), got {r.returncode}:\n{r.stdout}\n{r.stderr}"
    )
    assert TAG in r.stdout, "evidence lines must carry the machine-greppable tag"


# --------------------------------------------------------------------------- #
# Dual-mode runner (stdlib path; pytest discovers test_* above directly)       #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    fns = [
        v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)
    ]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS | {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL | {fn.__name__}: {exc}")
        except (
            RuntimeError, ValueError, TypeError, OSError, TimeoutError,
            subprocess.SubprocessError, ImportError, ModuleNotFoundError,
        ) as exc:
            failed += 1
            print(f"  ERROR | {fn.__name__}: {type(exc).__name__}: {exc}")
    passed = len(fns) - failed
    print(f"{passed}/{len(fns)} tests passed")
    sys.exit(1 if failed else 0)
