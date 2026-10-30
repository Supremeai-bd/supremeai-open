#!/usr/bin/env python3
"""tests/test_docs_link_integrity_guard.py — fail-closed behavioral suite for #1938.

Verifies the R42 markdown internal-link integrity ratchet delivered for #1938:

  - sweep semantics: inline + reference links; external schemes ignored;
    file:// counted as file-uri hygiene; same-file and cross-file anchors
    validated with GitHub-style slugs; every occurrence counts;
  - verdict routing (single bookkeeping, no double-counting): writable-lane
    breaks are ratcheted, vendored .agents/skills/** routes report-only to
    the #1725 lane, AGENT_RULES.md ghost citations route excluded to the
    constitution_pointer_guard (#1642->#1708) debt;
  - ratchet semantics: baseline-pinned keys report without blocking; NEW
    keys and GROWN occurrence counts on pinned keys fail-closed; resolved
    keys surface as improvements (shrink the baseline in the same change);
  - baseline integrity: a missing or malformed baseline fail-closes; the
    live baseline's meta provenance is intact and its ratcheted floor is
    EMPTY at the landing head (the 8 #1938 fixes shipped in the same change);
  - wiring SSOT: the guard is present in the LIVE run_all_guards.py roster
    and the LIVE .githooks/pre-push hook (section 13), never duplicated here;
  - live sweep: the real repo tree passes --check semantics (ratchet holds).

Design (zero-dependency doctrine, dual mode — pytest + stdlib runners):

  - pytest:  pytest tests/test_docs_link_integrity_guard.py
  - stdlib:  python3 tests/test_docs_link_integrity_guard.py  (plain runner)

All tree scenarios are hermetic: built in tempdirs, offline, deterministic —
the same pattern as the guard's own --self-test.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "ci" / "docs_link_integrity_guard.py"
BASELINE = "scripts/ci/docs_link_integrity_baseline.json"
TAG = "[docs-link-integrity-guard]"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
import docs_link_integrity_guard as guard


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #

def make_tree(files: dict[str, str], floor: list[dict] | None = None) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="dlig-test-"))
    for rel, content in files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    baseline = {
        "schema": "docs-link-integrity-baseline/1",
        "generatedAt": "1970-01-01", "headAtGeneration": "test",
        "ratchetedFloor": floor or [],
        "knownReportOnly": [], "knownExcluded": [],
    }
    (tmp / BASELINE).parent.mkdir(parents=True, exist_ok=True)
    (tmp / BASELINE).write_text(json.dumps(baseline), encoding="utf-8")
    return tmp


def run_compare(root: Path, findings: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    baseline = json.loads((root / BASELINE).read_text(encoding="utf-8"))
    return guard.compare(baseline, findings)


# --------------------------------------------------------------------------- #
# wiring SSOT: the live roster and the live hook carry the guard               #
# --------------------------------------------------------------------------- #

def test_guard_module_reachable_and_pinned() -> None:
    assert GUARD.is_file(), f"guard script missing: {GUARD}"
    src = GUARD.read_text(encoding="utf-8")
    assert BASELINE in src, "guard must name its versioned baseline file"
    assert "shrink-only" in src.lower(), "ratchet doctrine must be stated in the guard"
    assert TAG in src, "evidence tag must stay stable for CI grepping"


def test_live_roster_and_hook_wiring() -> None:
    roster = (REPO_ROOT / "scripts" / "ci" / "run_all_guards.py").read_text(encoding="utf-8")
    assert "scripts/ci/docs_link_integrity_guard.py" in roster, "guard missing from live roster"
    hook = (REPO_ROOT / ".githooks" / "pre-push").read_text(encoding="utf-8")
    assert "docs_link_integrity_guard.py --files" in hook, "guard missing from live pre-push hook"
    # r3 re-land (bridge-20261028-r42-docs-link-integrity-r3): wired ADDITIVELY as
    # section 15 — main gained js_dep #1913 (13) and py_dep #1969 (14) between the
    # original base and the re-land, and neither CVE plane may be touched. The
    # original single-order shape (section 13 replacement) was invalidated by the
    # bridge v2 one-target-per-order routing law (the #1980 rejection).
    assert "15. DOCS LINK INTEGRITY GUARD" in hook, "pre-push section 15 header missing"
    assert "13. JS-DEP CVE GUARD" in hook, "js_dep section 13 must survive the docs-link wiring"
    assert "14. PY-DEP CVE GUARD" in hook, "py_dep section 14 must survive the docs-link wiring"


# --------------------------------------------------------------------------- #
# sweep semantics                                                              #
# --------------------------------------------------------------------------- #

def test_sweep_counts_occurrences_not_unique_pairs() -> None:
    root = make_tree({"docs/a.md": "[d](ghost.md)\n\n[d2](ghost.md)\n"})
    _, findings = guard.sweep(root)
    assert len(findings) == 2, "every occurrence must count (double damage)"


def test_sweep_ignores_external_schemes_and_checks_file_uri() -> None:
    root = make_tree({
        "docs/a.md": "[gh](https://github.com/x/y)\n[hi](mailto:a@b.c)\n[local](file:///f:/x.md)\n",
    })
    checked, findings = guard.sweep(root)
    assert checked == 1, "external URLs are deliberately out of scope (#1938 never-do)"
    assert findings[0]["reason"] == "file-uri"


def test_anchor_validation_is_github_slug_semantics() -> None:
    root = make_tree({
        "docs/a.md": "[ok](b.md#serve-an-agent-over-http)\n[bad](b.md#no-such-heading)\n",
        "docs/b.md": "# T\n\n## Serve an agent over HTTP\n",
    })
    _, findings = guard.sweep(root)
    assert [f["reason"] for f in findings] == ["missing-anchor"]


# --------------------------------------------------------------------------- #
# verdict routing                                                              #
# --------------------------------------------------------------------------- #

def test_routing_ratcheted_reportonly_excluded() -> None:
    root = make_tree({
        "docs/a.md": "[d](ghost.md)\n[r](../AGENT_RULES.md)\n",
        ".agents/skills/pack/SKILL.md": "[v](missing.md)\n",
    })
    _, findings = guard.sweep(root)
    verdicts = sorted(
        guard.classify(f["file"], f["target"], f["reason"]) for f in findings
    )
    assert verdicts == ["excluded", "ratcheted", "report_only"]


# --------------------------------------------------------------------------- #
# ratchet semantics                                                            #
# --------------------------------------------------------------------------- #

def test_new_ratcheted_key_fails_and_pinned_key_passes() -> None:
    root = make_tree(
        {"docs/a.md": "[pinned](ghost.md)\n[fresh](other-ghost.md)\n"},
        floor=[{"file": "docs/a.md", "target": "ghost.md", "reason": "missing-file", "allowed": 1}],
    )
    _, findings = guard.sweep(root)
    drift, _ro, _im = run_compare(root, findings)
    assert len(drift) == 1 and drift[0]["kind"] == "new"
    assert drift[0]["target"] == "other-ghost.md"


def test_grown_occurrence_count_fails() -> None:
    root = make_tree(
        {"docs/a.md": "[d](ghost.md)\n\n[d2](ghost.md)\n"},
        floor=[{"file": "docs/a.md", "target": "ghost.md", "reason": "missing-file", "allowed": 1}],
    )
    _, findings = guard.sweep(root)
    drift, _ro, _im = run_compare(root, findings)
    assert len(drift) == 1 and drift[0]["kind"] == "grown"


def test_resolved_key_surfaces_as_improvement() -> None:
    root = make_tree(
        {"docs/a.md": "# fine\n"},
        floor=[{"file": "docs/a.md", "target": "ghost.md", "reason": "missing-file", "allowed": 1}],
    )
    _, findings = guard.sweep(root)
    drift, _ro, im = run_compare(root, findings)
    assert not drift and len(im) == 1 and im[0]["kind"] == "resolved"


# --------------------------------------------------------------------------- #
# baseline integrity                                                           #
# --------------------------------------------------------------------------- #

def test_missing_or_malformed_baseline_fails_closed() -> None:
    root = make_tree({"docs/a.md": "# fine\n"})
    (root / BASELINE).unlink()
    try:
        guard.load_baseline(root)
        raise AssertionError("missing baseline must SystemExit(1)")
    except SystemExit as exc:
        assert exc.code == 1
    (root / BASELINE).write_text("{not json", encoding="utf-8")
    try:
        guard.load_baseline(root)
        raise AssertionError("malformed baseline must SystemExit(1)")
    except SystemExit as exc:
        assert exc.code == 1


def test_live_baseline_provenance_and_empty_floor() -> None:
    data = json.loads((REPO_ROOT / BASELINE).read_text(encoding="utf-8"))
    assert data["schema"] == "docs-link-integrity-baseline/1"
    # #2180: the date is now stamped live at regen time — assert the FORMAT
    # ("baseline must be dated"), not a frozen literal that would red on the
    # first future regen (the literal itself was the same freeze class).
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(data["generatedAt"])), (
        "baseline must be dated (YYYY-MM-DD)")
    # r3 re-land then same-day shrink: the genesis ratchet pinned the ONE
    # satellite-lane entry (core/** routes satellite — the #1980 rejection law)
    # while its fix shipped via bridge-20261028-r42-manifest-satellite-fix; the
    # fix landed as bc810e7 (PR #2028) and mirrored BEFORE the shrink order, so
    # the floor is now EMPTY — the original r3 empty-floor endgame, reached by
    # the routing-legal route. The note must keep the full dated history.
    floor = data["ratchetedFloor"]
    assert floor == [], f"floor must be empty post-shrink (endgame), got {floor}"
    assert "SHRUNK TO 0" in data["note"], "the dated shrink stamp must be kept in the baseline note"
    for token in ("bridge-20261028-r42-docs-link-integrity-r3",
                  "bridge-20261028-r42-manifest-satellite-fix", "bc810e7"):
        assert token in data["note"], f"shrink history must cite {token}"
    assert len(data["knownReportOnly"]) == 3, "3 vendored findings stay pinned report-only (#1725 lane)"
    assert len(data["knownExcluded"]) == 10, "10 AGENT_RULES ghosts stay pinned excluded (#1642->#1708 debt)"


# --------------------------------------------------------------------------- #
# #2180 — regen provenance is live; the file-owned narrative note survives     #
# --------------------------------------------------------------------------- #

def test_regen_note_preserved_and_provenance_live() -> None:
    # The canonical regen path (main --baseline) stamps LIVE provenance and
    # carries the file-owned narrative note forward — the genesis/shrink
    # history pinned by test_live_baseline_provenance_and_empty_floor must
    # never be clobbered by a regen. Exercises main(), not just the builder.
    out = subprocess.run([sys.executable, str(GUARD), "--baseline"], cwd=str(REPO_ROOT),
                         capture_output=True, text=True)
    assert out.returncode == 0, f"--baseline must exit 0: {out.stderr[-300:]}"
    regen = json.loads(out.stdout)
    live = json.loads((REPO_ROOT / BASELINE).read_text(encoding="utf-8"))
    assert regen["note"] == live["note"], "regen must carry the file-owned narrative note forward"
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO_ROOT),
                          capture_output=True, text=True)
    assert head.returncode == 0
    assert regen["headAtGeneration"].startswith(head.stdout.strip()), (
        "regen provenance must pin the actual HEAD at generation time (#2180)")


def test_git_provenance_fallback_hermetic() -> None:
    # A git-less directory gets the honest fallback — never a crash, never a
    # stale literal carried forward as if it were fresh provenance.
    tmp = Path(tempfile.mkdtemp(prefix="dlig-nogit-"))
    assert guard._git_head_provenance(tmp) == "unknown (git unavailable at generation)"


def test_live_repo_ratchet_holds() -> None:
    checked, findings = guard.sweep(REPO_ROOT)
    baseline = json.loads((REPO_ROOT / BASELINE).read_text(encoding="utf-8"))
    drift, _ro, _im = guard.compare(baseline, findings)
    assert not drift, f"live tree must hold the ratchet: {drift}"
    assert checked >= 100, "live sweep must cover the real link graph"


def test_guard_self_test_suite_passes() -> None:
    assert guard.self_test() is True


# --------------------------------------------------------------------------- #
# stdlib dual-mode runner                                                      #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(
        (k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)
    ):
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {name}: {exc}")
    print(f"{len([k for k in globals() if k.startswith('test_')]) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
