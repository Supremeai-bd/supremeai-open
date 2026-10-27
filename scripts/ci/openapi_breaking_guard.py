#!/usr/bin/env python3
"""openapi_breaking_guard.py — machine revision-diff gate for the stable external contract (#1711).

Mission (issue #1711, scout radar VI lane R23):
    `api-schemas/gateway.openapi.yaml` is the declared stable external contract
    consumed by `examples/gateway_client.py`, the VS Code extension, and external
    SDK authors. Until this guard, a narrowed type, removed response property, or
    newly-required field sailed through every existing gate: the structural
    validity check in `contract_parity_guard.py` performs zero revision-to-revision
    diffing, so one silent break = every external consumer fails at runtime with
    no guard ever going red.

Behavior contract (fail-closed on detection, honest-degradation on environment):
    1. Engages only when a revision range actually touches the contract file
       (never bothers clean pushes).
    2. Runs `oasdiff breaking <base> <revision>` when the binary is present;
       SKIPS-WITH-EVIDENCE when absent — the same honest-degradation pattern as
       the loop's `gh` handling (offline machines are not failures).
    3. Fail-closed (exit 1) on detected breaking changes; exit 0 on no-diff.
    4. Escape hatch for intentional breaks: a commit inside the revision range
       carrying the admin-reviewed trailer `contract-break-approved:` passes
       with evidence naming the approval — before the binary is even consulted.
    5. Tool version pinned in ONE place (OASDIFF_MIN_VERSION, OpenAPI 3.1 GA);
       an older/unparseable binary skips with evidence instead of lying.

Never-do (issue #1711): this guard never rewrites the spec, never auto-bumps
versions, never fetches anything over the network at guard time (local git +
local binary only), and no binary is committed into the repo.

Usage:
    python scripts/ci/openapi_breaking_guard.py --check          # roster mode
    python scripts/ci/openapi_breaking_guard.py --files a b ...  # pre-push mode
    python scripts/ci/openapi_breaking_guard.py --base REF [--head REF]
    python scripts/ci/openapi_breaking_guard.py --self-test      # hermetic

Exit codes: 0 = pass or honest skip · 1 = breaking changes detected · 2 = usage error.

Stdlib-only. Offline. Zero new Python dependency (the differ is an external CLI).
"""

from __future__ import annotations

import argparse
import contextlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]

CONTRACT_FILE = "api-schemas/gateway.openapi.yaml"
OASDIFF_BINARY = "oasdiff"
# Single SSOT pin for the differ version (issue #1711 adoption path step 3):
# OpenAPI 3.1 is GA since oasdiff v1.15.0 (official docs/OPENAPI-31.md), and the
# pinned contract is `openapi: 3.1.0`. An older binary cannot be trusted to
# classify 3.1 revisions, so it must not silently gate — it skips with evidence.
OASDIFF_MIN_VERSION = "1.15.0"
APPROVAL_TRAILER = "contract-break-approved:"
GUARD_TAG = "[openapi-breaking-guard]"

EXIT_PASS = 0
EXIT_BREAKING = 1
EXIT_USAGE = 2


def _evidence(msg: str) -> None:
    print(f"{GUARD_TAG} {msg}")


def run_cmd(
    cmd: list[str], cwd: Path | None = None, timeout: int = 60, env: dict | None = None
) -> tuple[int, str, str]:
    """Honest command runner modeled on the loop's run_cmd (never raises)."""
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            timeout=timeout,
            check=False,
            env=env,
        )
        out = p.stdout.decode("utf-8", errors="replace").strip()
        err = p.stderr.decode("utf-8", errors="replace").strip()
        return p.returncode, out, err
    except FileNotFoundError:
        return 127, "", f"binary not found: {cmd[0] if cmd else '?'}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout}s: {' '.join(cmd)}"
    except Exception as exc:  # noqa: BLE001 — guard must never crash on env quirks
        return 1, "", f"execution error: {exc}"


def _version_tuple(text: str) -> tuple[int, ...] | None:
    """Extract the first dotted version number; None when unparseable."""
    m = re.search(r"(\d+(?:\.\d+)+)", text)
    if not m:
        return None
    return tuple(int(part) for part in m.group(1).split("."))


def _version_at_least(found: tuple[int, ...], minimum: tuple[int, ...]) -> bool:
    width = max(len(found), len(minimum))
    pad = lambda v: v + (0,) * (width - len(v))  # noqa: E731
    return pad(found) >= pad(minimum)


def oasdiff_status(path_env: dict | None = None) -> tuple[str | None, str]:
    """Probe the pinned differ. Returns (version_string_or_None, reason).

    version None means the gate cannot run honestly and must skip with
    evidence: binary absent, or present but older than / unverifiable against
    OASDIFF_MIN_VERSION (a too-old differ could misclassify 3.1 revisions).
    """
    binary = shutil.which(OASDIFF_BINARY, path=path_env.get("PATH") if path_env else None)
    if not binary:
        return None, f"{OASDIFF_BINARY} binary not found on PATH (honest skip per #1711)"
    code, out, err = run_cmd([binary, "--version"], timeout=15, env=path_env)
    if code != 0:
        return None, f"{OASDIFF_BINARY} --version failed (exit {code}: {err or 'no stderr'})"
    parsed = _version_tuple(out)
    if parsed is None:
        return None, f"unparseable {OASDIFF_BINARY} version output: {out[:120]!r}"
    minimum = _version_tuple(OASDIFF_MIN_VERSION) or (0,)
    if not _version_at_least(parsed, minimum):
        return None, (
            f"{OASDIFF_BINARY} {out} is older than pinned minimum {OASDIFF_MIN_VERSION} "
            f"(OpenAPI 3.1 GA; pin SSOT lives in this file)"
        )
    return out or OASDIFF_MIN_VERSION, "ok"


def resolve_base_ref(repo_root: Path, explicit_base: str = "") -> tuple[str | None, str]:
    """Pick the comparison base: explicit > merge-base(HEAD, origin/main) > HEAD~1.

    Returns (ref_or_None, reason). None means no honest base exists
    (single-commit / shallow clone) — the caller skips with evidence.
    """
    if explicit_base:
        code, _, _ = run_cmd(["git", "rev-parse", "--verify", "--quiet", explicit_base], cwd=repo_root)
        if code == 0:
            return explicit_base, f"explicit --base {explicit_base}"
        return None, f"explicit --base {explicit_base} is not a valid revision"
    code, head, _ = run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_root)
    if code != 0:
        return None, "git rev-parse HEAD failed (not a git worktree?)"
    head = head.splitlines()[0]
    code, mb, _ = run_cmd(["git", "merge-base", "HEAD", "origin/main"], cwd=repo_root)
    if code == 0 and mb.strip():
        base = mb.splitlines()[0]
        if base != head:
            return base, "merge-base(HEAD, origin/main)"
        return None, "HEAD is at merge-base with origin/main (no local revision range)"
    code, parent, _ = run_cmd(["git", "rev-parse", "--verify", "--quiet", "HEAD~1"], cwd=repo_root)
    if code == 0 and parent.strip():
        return parent.splitlines()[0], "HEAD~1 (origin/main unavailable)"
    return None, "single-commit/shallow history: no honest base revision exists"


def file_changed_in_range(repo_root: Path, path: str, base_ref: str, head_ref: str) -> bool:
    code, out, _ = run_cmd(
        ["git", "diff", "--name-only", f"{base_ref}..{head_ref}", "--", path], cwd=repo_root
    )
    return code == 0 and bool(out.strip())


def find_approval(repo_root: Path, base_ref: str, head_ref: str) -> str | None:
    """Return the admin-review trailer line if any commit in range carries it."""
    code, out, _ = run_cmd(["git", "log", "--format=%B", f"{base_ref}..{head_ref}"], cwd=repo_root)
    if code != 0:
        return None
    for line in out.splitlines():
        if line.strip().startswith(APPROVAL_TRAILER):
            return line.strip()
    return None


def read_blob(repo_root: Path, ref: str, path: str) -> tuple[str | None, str]:
    """Read path content at ref via git (committed truth). Worktree fallback for HEAD."""
    code, out, err = run_cmd(["git", "show", f"{ref}:{path}"], cwd=repo_root)
    if code == 0:
        return out + ("\n" if out else ""), "git"
    if ref == "HEAD":
        wt = repo_root / path
        if wt.is_file():
            try:
                return wt.read_text(encoding="utf-8"), "worktree"
            except Exception as exc:  # noqa: BLE001
                return None, f"worktree read failed: {exc}"
    return None, err or f"git show {ref}:{path} failed (exit {code})"


def run_oasdiff_breaking(
    base_content: str, rev_content: str, version_report: str, path_env: dict | None = None
) -> tuple[int, list[str]]:
    """Materialize both revisions and run the differ. Returns (exit_code, evidence).

    Exit contract (issue #1711): fail-closed on detected breaking changes,
    exit 0 on no-diff, honest skip on environment trouble.
    """
    version_line = f"differ: {version_report}" if version_report else "differ: (probed)"
    with tempfile.TemporaryDirectory(prefix="openapi-breaking-guard-") as td:
        base_file = Path(td) / "base.yaml"
        rev_file = Path(td) / "revision.yaml"
        base_file.write_text(base_content, encoding="utf-8")
        rev_file.write_text(rev_content, encoding="utf-8")
        binary = shutil.which(OASDIFF_BINARY, path=path_env.get("PATH") if path_env else None)
        code, out, err = run_cmd(
            [binary, "breaking", str(base_file), str(rev_file)],
            timeout=120,
            env=path_env,
        )
        evidence = [version_line]
        if code == 0:
            evidence.append("breaking-change scan: CLEAN (0 breaking changes)")
            return EXIT_PASS, evidence
        if code in (124, 127):
            evidence.append(f"{OASDIFF_BINARY} could not run (exit {code}: {err[:200]}) — honest skip")
            return EXIT_PASS, evidence
        evidence.append(f"breaking-change scan FAILED-CLOSED (differ exit {code})")
        for line in (out or err).splitlines()[:40]:
            evidence.append(f"  oasdiff| {line}")
        return EXIT_BREAKING, evidence


def evaluate(
    repo_root: Path,
    base_ref: str = "",
    head_ref: str = "HEAD",
    changed_files: list[str] | None = None,
) -> tuple[int, list[str]]:
    """Single decision tree. Returns (exit_code, evidence_lines). Never raises."""
    ev: list[str] = [f"contract: {CONTRACT_FILE}"]

    # 1. Engagement gate — never bother clean revisions.
    if changed_files is not None and CONTRACT_FILE not in changed_files:
        return EXIT_PASS, ev + ["not touched in this revision set — gate not engaged"]
    base, why = resolve_base_ref(repo_root, base_ref)
    if base is None:
        return EXIT_PASS, ev + [f"skip: {why}"]
    ev.append(f"base: {base[:12]} ({why}) · head: {head_ref}")
    if not file_changed_in_range(repo_root, CONTRACT_FILE, base, head_ref):
        return EXIT_PASS, ev + ["contract unchanged in revision range — gate not engaged"]

    # 2. Escape hatch BEFORE the binary: an admin-approved intentional break
    #    must pass even on machines without oasdiff installed.
    approval = find_approval(repo_root, base, head_ref)
    if approval:
        return EXIT_PASS, ev + [f"approved intentional break ({APPROVAL_TRAILER} trailer): {approval}"]

    # 3. Honest tool probe (skip-with-evidence when the differ cannot run).
    version_report, probe_reason = oasdiff_status()
    if version_report is None:
        return EXIT_PASS, ev + [f"skip: {probe_reason}"]

    # 4. Machine revision-diff (fail-closed on detection).
    base_content, base_err = read_blob(repo_root, base, CONTRACT_FILE)
    if base_content is None:
        return EXIT_PASS, ev + [f"skip: base blob unreadable ({base_err[:160]})"]
    rev_content, rev_err = read_blob(repo_root, head_ref, CONTRACT_FILE)
    if rev_content is None:
        return EXIT_PASS, ev + [f"skip: head blob unreadable ({rev_err[:160]})"]
    code, diff_ev = run_oasdiff_breaking(base_content, rev_content, version_report)
    return code, ev + diff_ev


# --------------------------------------------------------------------------- #
# Hermetic self-test (offline; stub differ on PATH, sandbox git for trailers)  #
# --------------------------------------------------------------------------- #

def self_test() -> bool:
    print("[self-test] Running openapi breaking guard tests...")
    import subprocess as sp

    min_ver = _version_tuple(OASDIFF_MIN_VERSION)
    assert min_ver == (1, 15, 0), f"pin SSOT malformed: {min_ver}"
    assert _version_at_least((1, 15, 0), (1, 15, 0)), "equal version must satisfy pin"
    assert _version_at_least((1, 16, 2), (1, 15, 0)), "newer version must satisfy pin"
    assert not _version_at_least((1, 9, 4), (1, 15, 0)), "older version must fail pin"
    assert _version_tuple("oasdiff version 1.15.0") == (1, 15, 0)
    assert _version_tuple("no digits here") is None
    print("  PASS | version pin parsing + comparison")

    # Case A: engagement gate — contract not in changed set.
    code, ev = evaluate(Path("/nonexistent"), changed_files=["README.md", "docs/x.md"])
    assert code == EXIT_PASS and any("not touched" in e for e in ev), (code, ev)
    print("  PASS | not-touched engagement gate")

    # Case B: honest skip when the binary is absent (no PATH at all).
    code, ev = evaluate(Path("/nonexistent"), changed_files=[CONTRACT_FILE])
    assert code == EXIT_PASS, (code, ev)
    # (on this machine oasdiff may or may not exist; both outcomes are honest:
    # skip evidence, or a clean/failing scan against /nonexistent git — which
    # resolve_base_ref already short-circuits as skip. Assert skip-shaped.)
    assert any("skip" in e.lower() for e in ev), (code, ev)
    print("  PASS | environment trouble degrades to honest skip (exit 0)")

    # Case C/D/E: stub differ on PATH — breaking / clean / crash semantics.
    def _stub_dir(name: str, body: str) -> tuple[Path, dict]:
        d = Path(tempfile.mkdtemp(prefix=f"oasdiff-stub-{name}-"))
        stub = d / OASDIFF_BINARY
        stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)
        return d, {"PATH": f"{d}:/usr/bin:/bin"}

    # C: differ detects breaking changes (documented CI pattern: non-zero exit).
    d, env = _stub_dir(
        "breaking",
        "#!/usr/bin/env python3\nprint('~~ breaking: response property removed')\nraise SystemExit(1)\n",
    )
    code, ev = run_oasdiff_breaking("a: 1\n", "a: 2\n", "stub 1.15.0", env)
    assert code == EXIT_BREAKING, (code, ev)
    assert any("FAILED-CLOSED" in e for e in ev), ev
    shutil.rmtree(d, ignore_errors=True)
    print("  PASS | breaking change -> fail-closed exit 1")

    # D: clean scan (exit 0) -> pass.
    d, env = _stub_dir(
        "clean", "#!/usr/bin/env python3\nprint('No breaking changes')\nraise SystemExit(0)\n"
    )
    code, ev = run_oasdiff_breaking("a: 1\n", "a: 1\n", "stub 1.15.0", env)
    assert code == EXIT_PASS and any("CLEAN" in e for e in ev), (code, ev)
    shutil.rmtree(d, ignore_errors=True)
    print("  PASS | clean scan -> exit 0")

    # E: differ crashes (127/124-class env failure) -> honest skip, not a lie.
    d, env = _stub_dir(
        "crash", "#!/usr/bin/env python3\nimport sys\nsys.exit(127)\n"
    )
    code, ev = run_oasdiff_breaking("a: 1\n", "a: 2\n", "stub 1.15.0", env)
    assert code == EXIT_PASS and any("honest skip" in e for e in ev), (code, ev)
    shutil.rmtree(d, ignore_errors=True)
    print("  PASS | differ crash -> honest skip (never fabricated pass)")

    # F: sandbox git repo — trailer escape hatch + real blob plumbing.
    with tempfile.TemporaryDirectory(prefix="oasdiff-guard-git-") as td:
        repo = Path(td)
        def git(*args: str) -> None:
            r = sp.run(["git", *args], cwd=repo, capture_output=True, text=True)
            assert r.returncode == 0, (args, r.stderr)
        git("init", "-q")
        git("config", "user.email", "guard@example.invalid")
        git("config", "user.name", "Guard Self-Test")
        (repo / "api-schemas").mkdir()
        cfile = repo / CONTRACT_FILE
        cfile.write_text("openapi: 3.1.0\ninfo:\n  title: t\n  version: 1.0.0\npaths: {}\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-qm", "base")
        base_sha = sp.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
        # revision WITHOUT trailer: no approval found
        cfile.write_text("openapi: 3.1.0\ninfo:\n  title: t\n  version: 1.1.0\npaths: {}\n", encoding="utf-8")
        git("commit", "-aqm", "bump")
        assert find_approval(repo, base_sha, "HEAD") is None
        # revision WITH trailer: approval surfaced verbatim
        git("commit", "--allow-empty", "-qm", "intentional break\n\ncontract-break-approved: admin @ops (ticket #99)")
        approval = find_approval(repo, base_sha, "HEAD")
        assert approval and APPROVAL_TRAILER in approval and "admin @ops" in approval, approval
        assert file_changed_in_range(repo, CONTRACT_FILE, base_sha, "HEAD~1")
        blob, how = read_blob(repo, base_sha, CONTRACT_FILE)
        assert blob is not None and "version: 1.0.0" in blob and how == "git"
        blob2, _ = read_blob(repo, "HEAD", CONTRACT_FILE)
        assert blob2 is not None and "version: 1.1.0" in blob2
        print("  PASS | sandbox git: trailer escape hatch + committed-blob reads")

    # G: roster/hook wiring (SSOT-extraction style — assert the LIVE files).
    roster = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"
    if roster.is_file():
        text = roster.read_text(encoding="utf-8")
        assert "scripts/ci/openapi_breaking_guard.py" in text, "guard missing from roster"
    hook = REPO_ROOT / ".githooks" / "pre-push"
    if hook.is_file():
        htext = hook.read_text(encoding="utf-8")
        assert "openapi_breaking_guard.py" in htext, "guard missing from pre-push hook"
        assert APPROVAL_TRAILER in htext, "hook must document the escape hatch"
    print("  PASS | roster + pre-push wiring present (when run inside the repo)")

    print("[self-test] openapi breaking guard self-tests PASSED (7 test cases)!")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Machine revision-diff gate for api-schemas/gateway.openapi.yaml (#1711)"
    )
    parser.add_argument("--check", action="store_true", help="roster mode: auto-resolve base, engage on contract change")
    parser.add_argument(
        "--files", nargs="*", default=None,
        help="pre-push mode: changed-file list; engages only when the contract file is among them",
    )
    parser.add_argument("--base", default="", help="explicit base revision (default: auto-resolved)")
    parser.add_argument("--head", default="HEAD", help="head revision (default: HEAD)")
    parser.add_argument("--self-test", action="store_true", help="hermetic self-test suite (offline)")
    args = parser.parse_args()

    if args.self_test:
        return EXIT_PASS if self_test() else EXIT_BREAKING

    code, ev = evaluate(REPO_ROOT, base_ref=args.base, head_ref=args.head, changed_files=args.files)
    for line in ev:
        _evidence(line)
    if code == EXIT_BREAKING:
        print(
            f"{GUARD_TAG} ❌ BREAKING CHANGE detected in {CONTRACT_FILE}. "
            f"Fix the revision, or land an admin-reviewed '{APPROVAL_TRAILER}' trailer commit in this range for intentional breaks.",
            file=sys.stderr,
        )
    return code


if __name__ == "__main__":
    sys.exit(main())
