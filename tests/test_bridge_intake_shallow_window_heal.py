#!/usr/bin/env python3
"""Offline reproduction of the #3723 intake shallow-window stall + self-heal proof.

Live evidence being pinned (issue #3723): one 15:59Z intake batch failed four
work orders with the identical deterministic error
`git diff origin/main...origin/bridge/<tid>… rc=128: fatal: … no merge base`
(#3382 15:59:10Z, #3380 15:59:24Z, #3335 15:59:40Z, #3292 15:59:55Z), leaving
them parked in `bridge:in-gates` for hours because every re-run fails the same
way while main drifts further away (121+ commits by filing time).

Mechanism: `clone(--depth=50)` windows main to {T..T-49}; a WO branch whose
base sits >50 commits behind (C60 base was 54 behind, rev-list-verified) is
fetched as {tip, base..deeper} — the commits between the two windows
(T-50..T-53) belong to NEITHER set, so the three-dot diff cannot compute a
merge base. A base ≤49 behind intersects the window at the base itself, which
is why fresh WOs pass: the failure line is exactly the clone depth.

These tests rebuild that exact shape against a local `file://` origin (the
only transport that honors --depth locally) with zero network:

  A. stale-base repro: base 55 behind tip on a 60-commit main → the raw
     three-dot diff fails rc=128 "no merge base" (the live verdict shape);
     `ensure_diffable_base` heals it (one bounded unshallow — the open repo's
     full .git is ~20MB) and the diff then lists exactly the WO's file;
     the shallow marker is gone afterwards.
  B. fresh-base no-op: base 45 behind (inside the window) → the diff already
     works and the heal pays nothing (`.git/shallow` still present — the
     fast path must never unshallow).
  C. orphan branch: no shared history even at full depth → fail-closed
     `BRANCH_BASE_UNREACHABLE` BridgeError, never a silent wrong-base diff.
  D. contract pins: the heal is wired into `fetch_patch` BEFORE the first
     three-dot diff, and the teachable token exists in the source.

Dual-mode (pytest + stdlib runner), mirroring test_bridge_intake_gate_watchdog.py.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INTAKE = REPO_ROOT / "scripts" / "bridge" / "bridge_intake.py"

PASS = 0
FAIL = 1


def _load_intake_module():
    spec = importlib.util.spec_from_file_location("bridge_intake_under_test", INTAKE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(*args, cwd, check=True):
    env_args = ["-c", "user.email=wo-test@example.invalid", "-c", "user.name=WO Test"]
    proc = subprocess.run(["git", *env_args, *args], cwd=str(cwd), capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} rc={proc.returncode}: {(proc.stderr or proc.stdout)[-400:]}"
        )
    return proc


def _make_origin(root: Path, n_commits: int = 60) -> Path:
    """n-commit linear main, each commit appending one numbered line to log.txt."""
    origin = root / "origin"
    origin.mkdir()
    _git("init", "-q", "-b", "main", cwd=origin)
    log = origin / "log.txt"
    for i in range(1, n_commits + 1):
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(f"line-{i}\n")
        _git("add", "log.txt", cwd=origin)
        _git("commit", "-q", "-m", f"c{i}", cwd=origin)
    return origin


def _add_wo_branch(origin: Path, name: str, base_behind: int, filename: str) -> None:
    """One-commit WO branch cut `base_behind` commits behind the main tip."""
    _git("checkout", "-q", "-b", name, f"main~{base_behind}", cwd=origin)
    (origin / filename).write_text(f"{filename} content\n", encoding="utf-8")
    _git("add", filename, cwd=origin)
    _git("commit", "-q", "-m", f"{name}: add {filename}", cwd=origin)
    _git("checkout", "-q", "main", cwd=origin)


def _bot_clone_and_fetch(origin: Path, dest: Path, branch: str) -> None:
    """Mirror the bot's exact plumbing: --depth=50 clone + explicit refspec fetch."""
    _git("clone", "--quiet", "--depth=50", f"file://{origin}", str(dest), cwd=dest.parent)
    _git("fetch", "--quiet", "origin", f"refs/heads/{branch}:refs/remotes/origin/{branch}", cwd=dest)


def _three_dot_rc(work: Path, branch: str) -> tuple[int, str]:
    proc = _git("diff", f"origin/main...origin/{branch}", cwd=work, check=False)
    return proc.returncode, (proc.stderr or "")


def test_a_stale_base_repro_and_heal():
    mod = _load_intake_module()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        origin = _make_origin(root)
        # 60-commit main; base 55 behind the tip → outside the depth=50 window
        # (mirrors the live C60 shape: base 54 behind, window 50).
        _add_wo_branch(origin, "bridge/wo-stale", base_behind=55, filename="wo.txt")
        work = root / "work-stale"
        _bot_clone_and_fetch(origin, work, "bridge/wo-stale")

        rc, err = _three_dot_rc(work, "bridge/wo-stale")
        assert rc == 128, f"expected the live rc=128 shape, got rc={rc}"
        assert "no merge base" in err, f"expected 'no merge base' in stderr: {err[-200:]}"

        # The heal must reconnect the object graph — no exception.
        mod.ensure_diffable_base(str(work), "bridge/wo-stale")

        rc2, err2 = _three_dot_rc(work, "bridge/wo-stale")
        assert rc2 == 0, f"heal left the diff broken: rc={rc2} {err2[-200:]}"
        names = _git(
            "diff", "--name-only", "origin/main...origin/bridge/wo-stale", cwd=work
        ).stdout.split()
        assert names == ["wo.txt"], f"healed diff must be exactly the WO file, got {names}"
        # Full-depth heal: the shallow marker is gone.
        assert not (work / ".git" / "shallow").exists(), "unshallow must remove .git/shallow"


def test_b_fresh_base_pays_nothing():
    mod = _load_intake_module()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        origin = _make_origin(root)
        # Base 45 behind → inside the depth=50 window (fresh WO fast path).
        _add_wo_branch(origin, "bridge/wo-fresh", base_behind=45, filename="wf.txt")
        work = root / "work-fresh"
        _bot_clone_and_fetch(origin, work, "bridge/wo-fresh")

        rc, err = _three_dot_rc(work, "bridge/wo-fresh")
        assert rc == 0, f"fresh WO must diff cleanly without any heal: rc={rc} {err[-200:]}"

        mod.ensure_diffable_base(str(work), "bridge/wo-fresh")  # silent no-op path
        assert (work / ".git" / "shallow").exists(), (
            "fast path must NOT unshallow — the heal is only for the window-miss case"
        )


def test_c_orphan_branch_fails_closed():
    mod = _load_intake_module()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        origin = _make_origin(root, n_commits=8)
        # Orphan line: genuinely no shared history, even at full depth.
        _git("checkout", "-q", "--orphan", "bridge/wo-orphan", cwd=origin)
        _git("rm", "-q", "-f", "--ignore-unmatch", "log.txt", cwd=origin)
        (origin / "orphan.txt").write_text("orphan\n", encoding="utf-8")
        _git("add", "orphan.txt", cwd=origin)
        _git("commit", "-q", "-m", "orphan root", cwd=origin)
        _git("checkout", "-q", "main", cwd=origin)

        work = root / "work-orphan"
        _bot_clone_and_fetch(origin, work, "bridge/wo-orphan")

        try:
            mod.ensure_diffable_base(str(work), "bridge/wo-orphan")
            raised = None
        except mod.BridgeError as exc:
            raised = str(exc)
        assert raised is not None, "orphan branch must fail closed, not pass"
        assert "BRANCH_BASE_UNREACHABLE" in raised, f"teachable token missing: {raised[:200]}"


def test_d_contract_pins():
    src = INTAKE.read_text(encoding="utf-8")
    assert "def ensure_diffable_base(" in src, "heal helper missing"
    assert "BRANCH_BASE_UNREACHABLE" in src, "teachable fail-closed token missing"
    assert "--unshallow" in src, "bounded self-heal fetch missing"
    # The heal must run BEFORE the first three-dot diff inside fetch_patch.
    fp_start = src.index("def fetch_patch(")
    heal_call = src.index("ensure_diffable_base(public_dir, branch)", fp_start)
    first_diff = src.index('["git", "diff"', fp_start)
    assert heal_call < first_diff, "ensure_diffable_base must precede the three-dot diff"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"[ RUN ] {name}")
            try:
                fn()
                print(f"[  OK ] {name}")
            except AssertionError as e:
                failures += 1
                print(f"[ FAIL] {name}: {e}")
    total = sum(1 for n in globals() if n.startswith("test_") and callable(globals()[n]))
    print(f"\n==== {total - failures}/{total} PASS ====")
    sys.exit(FAIL if failures else PASS)
