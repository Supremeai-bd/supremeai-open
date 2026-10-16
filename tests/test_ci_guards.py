#!/usr/bin/env python3
"""CI guard unit tests (#392) — offline fail-closed behavior verification.

Covers the two #392 behaviors that are testable without network:
  1. Claim Gate predicate (issue_has_active_claim) — fail-closed on unclaimed
     issues, unreadable issues, and the status:unclaimed released-marker veto.
  2. Knowledge Sharing predicate (build_reflection_section / build_pr_body) —
     every generated PR body carries a non-empty Reflection Evidence section,
     and missing WO content degrades to an honest pointer, never fabrication.

Run:  pytest tests/test_ci_guards.py -q
      (or) python3 tests/test_ci_guards.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest.mock as mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OPENER_PATH = REPO_ROOT / "scripts" / "ci" / "auto_bridge_pr_opener.py"
PIPELINE_PATH = REPO_ROOT / ".github" / "workflows" / "pipeline.yml"
TEMPLATE_PATH = REPO_ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md"
HANDOFF = "docs/CLAIM_GUARDS_OPERATOR_HANDOFF.md"

try:
    import pytest
    _HAS_PYTEST = True
except ImportError:
    _HAS_PYTEST = False


class _ManualSkip(Exception):
    pass


# pytest.skip.Exception (Skipped) may surface in the manual runner when pytest is
# importable — catch both so dual-mode runners count skips identically.
_SKIP_EXCS: tuple = (_ManualSkip,)
if _HAS_PYTEST:
    _SKIP_EXCS = _SKIP_EXCS + (pytest.skip.Exception,)


def _skip(reason: str):
    """Dual-mode skip: pytest.skip under pytest; _ManualSkip under the manual runner."""
    if _HAS_PYTEST:
        pytest.skip(reason)
    print(f"  \u2298 SKIP: {reason}")
    raise _ManualSkip(reason)


def _pipeline_applied() -> bool:
    """True when the operator has applied the hand-off (docs/CLAIM_GUARDS_OPERATOR_HANDOFF.md)."""
    if not PIPELINE_PATH.exists():
        return False
    text = PIPELINE_PATH.read_text(encoding="utf-8")
    return "claim-guard:" in text and "knowledge-sharing-guard:" in text


def _template_applied() -> bool:
    return TEMPLATE_PATH.exists() and "## Reflection Evidence" in TEMPLATE_PATH.read_text(encoding="utf-8")

_spec = importlib.util.spec_from_file_location("auto_bridge_pr_opener", OPENER_PATH)
opener = importlib.util.module_from_spec(_spec)
sys.modules["auto_bridge_pr_opener"] = opener
_spec.loader.exec_module(opener)


def _gh_result(payload: dict | None, returncode: int = 0):
    """Build a mock for subprocess.run mimicking `gh issue view --json labels,comments`."""
    out = json.dumps(payload) if payload is not None else ""
    res = mock.Mock()
    res.returncode = returncode
    res.stdout = out
    res.stderr = "boom" if returncode else ""
    return res


# ── Claim Gate predicate: active-claim zoo ───────────────────────────────────

def test_claim_pass_on_status_claimed_label():
    with mock.patch.object(opener.subprocess, "run", return_value=_gh_result(
        {"labels": [{"name": "status:claimed"}], "comments": []})):
        assert opener.issue_has_active_claim(1) is True


def test_claim_pass_on_status_in_progress_label():
    with mock.patch.object(opener.subprocess, "run", return_value=_gh_result(
        {"labels": [{"name": "status:in-progress"}], "comments": []})):
        assert opener.issue_has_active_claim(2) is True


def test_claim_pass_on_bridge_work_order_label():
    # A filed Bridge Work Order IS the zero-credential claim vehicle (#392 design).
    with mock.patch.object(opener.subprocess, "run", return_value=_gh_result(
        {"labels": [{"name": "bridge:queued"}], "comments": []})):
        assert opener.issue_has_active_claim(394) is True


def test_claim_pass_on_atomic_claim_comment():
    with mock.patch.object(opener.subprocess, "run", return_value=_gh_result(
        {"labels": [],
         "comments": [{"body": "working on it\n<!-- atomic-claim -->\nslot=agent-1"}]})):
        assert opener.issue_has_active_claim(3) is True


def test_claim_fail_on_unclaimed_issue():
    with mock.patch.object(opener.subprocess, "run", return_value=_gh_result(
        {"labels": [], "comments": []})):
        assert opener.issue_has_active_claim(4) is False


def test_claim_veto_unclaimed_marker_beats_stale_atomic_claim():
    # stale_claim_releaser vocabulary: status:unclaimed releases the claim;
    # a stale atomic-claim comment must NOT count after release.
    with mock.patch.object(opener.subprocess, "run", return_value=_gh_result(
        {"labels": [{"name": "status:unclaimed"}],
         "comments": [{"body": "<!-- atomic-claim -->"}]})):
        assert opener.issue_has_active_claim(5) is False


def test_claim_status_label_beats_unclaimed_marker():
    # A fresh re-claim (label re-added after release) always wins.
    with mock.patch.object(opener.subprocess, "run", return_value=_gh_result(
        {"labels": [{"name": "status:unclaimed"}, {"name": "status:claimed"}],
         "comments": []})):
        assert opener.issue_has_active_claim(6) is True


def test_claim_fail_closed_on_gh_failure():
    # Unreadable issue = NO verifiable claim (never guess-open the gate).
    with mock.patch.object(opener.subprocess, "run", return_value=_gh_result(None, returncode=1)):
        assert opener.issue_has_active_claim(7) is False


def test_claim_fail_closed_on_exception():
    with mock.patch.object(opener.subprocess, "run", side_effect=RuntimeError("network down")):
        assert opener.issue_has_active_claim(8) is False


def test_claim_fail_closed_on_malformed_json():
    res = mock.Mock()
    res.returncode = 0
    res.stdout = "not-json{"
    with mock.patch.object(opener.subprocess, "run", return_value=res):
        assert opener.issue_has_active_claim(9) is False


# ── Knowledge Sharing: reflection section builder ────────────────────────────

WO_BODY = """### Task ID
bridge-20261016-x

### Patch Branch
bridge/bridge-20261016-x

### Summary (what + why)
fixes the dispatch contract because readers were blind.

- **alternatives_rejected:**
  - whole-file payload — trips the intake scanner
"""


def test_reflection_carries_guard_compliant_fields():
    refl = opener.build_reflection_section(WO_BODY, 42)
    assert "## Reflection Evidence" in refl
    assert "- **why:**" in refl
    assert "dispatch contract" in refl          # WO summary becomes the why
    assert "whole-file payload" in refl          # WO alternatives carried through


def test_reflection_honest_fallback_without_alternatives():
    body = "### Summary (what + why)\njust a summary.\n"
    refl = opener.build_reflection_section(body, 42)
    assert "decision ledger" in refl, "fallback must point at the agent ledger, not fabricate"
    assert "just a summary." in refl


def test_reflection_missing_summary_still_nonempty_and_honest():
    refl = opener.build_reflection_section("no sections", 42)
    assert "Work order #42 summary (what + why)" in refl
    assert "decision ledger" in refl


def test_pr_body_is_guard_compliant():
    issue = {"number": 394, "title": "🌉 Bridge Work Order — feat(mcp): x", "body": WO_BODY}
    body = opener.build_pr_body(issue, "bridge/bridge-20261016-x")
    # The three things knowledge-sharing-guard greps for:
    assert "## Reflection Evidence" in body
    assert "- **why:** " in body and "blind." in body
    assert "- **alternatives_rejected:**" in body
    # Claim traceability for claim-guard:
    assert "Refs #394" in body
    assert "## Claim & Work Order" in body


def test_pr_body_alternatives_nonempty_for_degenerate_wo():
    issue = {"number": 7, "title": "WO", "body": "### Summary (what + why)\nwhy text\n"}
    body = opener.build_pr_body(issue, "bridge/b")
    lines = body.splitlines()
    idx = next(i for i, l in enumerate(lines) if "alternatives_rejected:**" in l)
    # The label line may be bare (markdown list); the NEXT line must carry the
    # non-empty sub-item — exactly what knowledge-sharing-guard's awk accepts.
    assert idx + 1 < len(lines), "alternatives label must be followed by a sub-item"
    assert lines[idx + 1].strip().startswith("- ") and len(lines[idx + 1].strip()) > 2, \
        f"expected non-empty sub-item after label, got: {lines[idx + 1]!r}"


# ── Guard placement reflection check (issue's 3-tier contract, tier 1) ──────
# These two checks auto-skip until the operator applies the hand-off blocks
# (docs/CLAIM_GUARDS_OPERATOR_HANDOFF.md §1/§4) — the bridge lane hard-blocks
# .github/ writes, so pre-integration CI must stay green, not red (#371 lesson).

def test_pipeline_carries_both_guard_jobs():
    if not _pipeline_applied():
        _skip(f"operator hand-off pending ({HANDOFF} §1/§2)")
    text = PIPELINE_PATH.read_text(encoding="utf-8")
    assert "claim-guard:" in text, "claim-guard job missing from pipeline.yml"
    assert "knowledge-sharing-guard:" in text
    assert "guard-exempt" in text, "admin escape hatch missing"
    assert "status:unclaimed" in text, "released-marker veto missing from claim-guard"
    assert "<!-- atomic-claim -->" in text, "atomic-claim vocabulary missing from claim-guard"


def test_pr_template_exists_with_reflection_section():
    if not TEMPLATE_PATH.exists():
        _skip(f"operator hand-off pending ({HANDOFF} §4)")
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "## Reflection Evidence" in template
    assert "**why:**" in template and "**alternatives_rejected:**" in template


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(vars(sys.modules[__name__]).items())
           if n.startswith("test_") and callable(f)]
    failed = skipped = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  \u2713 {name}")
        except _SKIP_EXCS:
            skipped += 1
        except AssertionError as exc:
            failed += 1
            print(f"  \u2717 {name}: {exc}")
    verdict = "\u2705" if failed == 0 else "\u274c"
    print(f"\n{verdict} test_ci_guards: "
          f"{len(fns) - failed - skipped}/{len(fns)} passed, {skipped} skipped (operator hand-off)")
    sys.exit(1 if failed else 0)
