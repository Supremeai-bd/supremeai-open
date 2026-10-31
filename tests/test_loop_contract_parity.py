"""Regression tests for the Loop-Contract Parity Guard (#118) — guard 7 ghost-label class.

Root cause fixed 2026-10-31: the guard-7 label extraction scanned the raw
``EXCLUDED_LABELS`` frozenset block for quoted strings, so a *comment* inside the
block that quotes a live WO-body sentence verbatim ("report-only, no closure
request; Recovery: N/A" — the #2756/#2766 family) was minted into a ghost label.
Every guard-7 waste warning then named a label that has never existed, and the
parity-OK summary inflated its label count by one (15 vs 14). The fix strips
``#`` comments from the captured block before the quoted-string scan; labels in
the SSOT never contain '#', so the strip cannot corrupt a real label, and a
future label that did contain '#' would fail the guard loudly (fail-closed).

These tests run the checker as a subprocess against the live repo tree — the
same way pipeline.yml's Loop-Contract Parity Guard job invokes it — so they pin
the exact CI behavior, including the exit-code contract (0 = parity held,
2 = guard environment error).
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "scripts" / "agents" / "check_loop_contract_parity.py"

# The verbatim sentence quoted inside a comment of the EXCLUDED_LABELS block.
# Before the fix it leaked into the label set as a ghost; it must never appear
# in the checker's output again (it is prose, not a label).
GHOST_SENTENCE = "no closure request"


def _run_checker() -> subprocess.CompletedProcess:
    runner = sys.executable
    return subprocess.run(
        [runner, str(CHECKER)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_parity_guard_exits_zero_on_live_tree():
    """The SSOT shape (tiers, guards, labels, pointers) must stay intact."""
    proc = _run_checker()
    if proc.returncode == 2 and "GUARD-ENV-ERROR" in proc.stdout:
        # Missing PyYAML in this interpreter — the checker's own env discipline
        # (exit 2, fail-closed). Not a parity failure; skip honestly.
        import pytest

        pytest.skip("PyYAML unavailable in this environment (checker exit 2)")
    assert proc.returncode == 0, (
        f"parity guard failed on the live tree (exit {proc.returncode}):\n"
        f"{proc.stdout}\n{proc.stderr}"
    )
    assert "Loop-contract parity OK" in proc.stdout


def test_guard7_warning_never_names_comment_text_as_label():
    """Ghost-label regression pin: comment prose must stay out of the label set.

    Before the comment-strip fix, the waste warning named
    ``'report-only, no closure request; recovery: n/a'`` — a verbatim quote of a
    WO-body sentence living in a *comment* of the frozenset block. The warning
    may still name REAL SSOT labels missing from the admin-lane CLAIMABLE array
    (waste direction, e.g. 'bridge:receipt' / 'report-only'), but never prose.
    """
    proc = _run_checker()
    if proc.returncode == 2 and "GUARD-ENV-ERROR" in proc.stdout:
        import pytest

        pytest.skip("PyYAML unavailable in this environment (checker exit 2)")
    out = (proc.stdout or "") + (proc.stderr or "")
    assert GHOST_SENTENCE not in out, (
        "guard-7 output contains comment prose as a label — the "
        "comment-strip fix in check_loop_contract_parity.py regressed:\n" + out
    )


def test_checker_file_still_strips_comments_before_label_scan():
    """Source-level pin: the fix must keep the comment-strip step in place.

    A future refactor that reverts to scanning the raw block would silently
    re-mint ghosts (the live tree currently carries the quoted sentence), so
    the structural marker of the fix is pinned here as well as behaviorally.
    """
    src = CHECKER.read_text(encoding="utf-8")
    assert "loop_labels_block" in src, (
        "guard-7 must derive the label scan from the comment-stripped block "
        "(loop_labels_block), not the raw frozenset capture"
    )
    assert 'ln.split("#", 1)[0]' in src, (
        "guard-7 comment-strip step is missing — quoted comment prose would "
        "leak into the label set again"
    )
