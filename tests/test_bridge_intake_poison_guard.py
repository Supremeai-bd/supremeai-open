"""Offline tests for the #2792 intake poison-order resilience guards.

বাংলা: zero-diff অর্ডার (content অন্যত্র merge) apply no-op → commit-হীন branch →
POST /pulls 422 → intake exit-2 → sync/reporting মৃত (streak #327-#329)। Guard-১
zero-diff clean reject; guard-২ effective-landing belt; amp-৩ gh_ok errors[]
detail; guard-৪ intake rc≠0 হলেও sync চলবে। সব offline (source pins + unit)।
"""

from __future__ import annotations

import pytest

from scripts.bridge.bridge_intake import (
    BridgeError,
    _has_effective_landing,
    gh_ok,
)

from pathlib import Path  # noqa: E402

INTAKE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "bridge" / "bridge_intake.py"


# ---------------------------------------------------------------------------
# Wiring pins — RCA guards sit at the exact choke points.
# ---------------------------------------------------------------------------


def test_guard1_zero_diff_reject_wired_after_caps_zone() -> None:
    src = INTAKE_PATH.read_text(encoding="utf-8")
    assert "zero-diff patch branch — content already merged elsewhere or empty" in src
    g1 = src.index('reject(\n            "zero-diff patch branch')
    caps = src.index('if len(diff.encode("utf-8", "replace")) > MAX_PATCH_BYTES:')
    g2 = src.index("if not _has_effective_landing(")
    assert caps < g1, "guard-1 must sit after the size cap check"
    assert g1 < g2, "guard-1 (cheap zero-diff) must precede guard-2 (post-apply belt)"


def test_guard2_wired_before_pr_creation() -> None:
    src = INTAKE_PATH.read_text(encoding="utf-8")
    g2 = src.index("if not _has_effective_landing(")
    pr = src.index('gh_ok(\n        "POST", f"/repos/{target_repo}/pulls"')
    assert g2 < pr, "guard-2 must reject BEFORE POST /pulls (the proven 422 point)"


def test_guard4_sync_runs_regardless_of_intake_rc() -> None:
    src = INTAKE_PATH.read_text(encoding="utf-8")
    m = src.index("def main() -> int:")
    body = src[m:]
    assert 'rcs.append(cmd_intake(token))' in body
    assert 'rcs.append(cmd_sync(token))' in body
    assert "if rc == 0 and mode" not in body, "old skip-sync-on-intake-failure must be gone"


# ---------------------------------------------------------------------------
# _has_effective_landing truth table (guard-2 semantics)
# ---------------------------------------------------------------------------


def test_fresh_noop_landing_is_ineffective() -> None:
    assert _has_effective_landing(False, False) is False


def test_staged_changes_are_effective() -> None:
    assert _has_effective_landing(True, False) is True


def test_already_applied_retry_is_effective() -> None:
    # E4 resume: commit already on the land branch, only push remains — must proceed.
    assert _has_effective_landing(False, True) is True


def test_both_effective() -> None:
    assert _has_effective_landing(True, True) is True


# ---------------------------------------------------------------------------
# gh_ok errors[] detail (RCA amp-3)
# ---------------------------------------------------------------------------


def test_gh_ok_appends_errors_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.bridge.bridge_intake as bi

    def fake_gh(method, path, token, payload=None):
        return (
            422,
            {
                "message": "Validation Failed",
                "errors": [{"message": "No commits between main and bridge-land/x"}],
            },
        )

    monkeypatch.setattr(bi, "gh", fake_gh)
    with pytest.raises(BridgeError) as excinfo:
        gh_ok("POST", "/repos/x/pulls", "tok")
    msg = str(excinfo.value)
    assert "HTTP 422" in msg
    assert "No commits between main and bridge-land/x" in msg, (
        "GitHub errors[] sub-cause must reach the verdict plane"
    )


def test_gh_ok_without_errors_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.bridge.bridge_intake as bi

    def fake_gh(method, path, token, payload=None):
        return (500, {"message": "boom"})

    monkeypatch.setattr(bi, "gh", fake_gh)
    with pytest.raises(BridgeError) as excinfo:
        gh_ok("GET", "/repos/x", "tok")
    assert "| errors:" not in str(excinfo.value)
    assert "boom" in str(excinfo.value)


def test_gh_ok_success_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.bridge.bridge_intake as bi

    def fake_gh(method, path, token, payload=None):
        return (201, {"number": 7})

    monkeypatch.setattr(bi, "gh", fake_gh)
    assert gh_ok("POST", "/repos/x/pulls", "tok") == {"number": 7}
