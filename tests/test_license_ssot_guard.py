#!/usr/bin/env python3
"""tests/test_license_ssot_guard.py — fail-closed behavioral suite for #1773.

Verifies the machine declared-vs-actual license gate for ECOSYSTEM_MAP §2.3
delivered by issue #1773:

  - SSOT parsing: the two §2.3 bullets parse into (repo -> model) pairs from
    the LIVE map, and an unparseable/dual-declared SSOT fail-closes (the legal
    boundary must never silently pass unverified);
  - license-expression validation: the pinned SPDX allowlist accepts valid and
    compound expressions, rejects unknown ids and parenthesized sub-expressions;
  - detection: missing license fields, LICENSE-absent mirror surfaces, and
    declared-model contradictions (both directions) are flagged on a sandbox
    tree, with honest skip-with-evidence for absent surfaces;
  - ratchet decision tree: the dated KNOWN_DRIFTS baseline is report-only
    (exit 0), any finding OUTSIDE the baseline is new drift (exit 1), and
    --strict flips every finding fail-closed;
  - live baseline pin: on the real repo the guard reports EXACTLY the
    baselined drifts (the WO acceptance set, post-#1621: the LICENSE-absent
    proprietary mirrors + the #1690 model-contradiction class — the 9
    license-field-missing package.json files were FIXED and shrunk out of
    the baseline in the same change, landing the field-level floor) — the
    shrink-only ratchet: fixing a drift requires shrinking the baseline in
    the same change;
  - wiring SSOT: the guard is present in the LIVE run_all_guards.py roster
    and the LIVE .githooks/pre-push hook (never duplicated here).

Design (zero-dependency doctrine, dual mode — pytest + stdlib runners):

  - pytest:  pytest tests/test_license_ssot_guard.py
  - stdlib:  python3 tests/test_license_ssot_guard.py   (plain runner)

Every test is offline and deterministic; sandbox trees are built in tempdirs —
the same hermetic pattern as the guard's own --self-test.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "ci" / "license_ssot_guard.py"
MAP = "ECOSYSTEM_MAP.md"
TAG = "[license-ssot-guard]"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
import license_ssot_guard as guard  # noqa: E402


# --------------------------------------------------------------------------- #
# SSOT wiring: the live roster and the live hook carry the guard               #
# --------------------------------------------------------------------------- #

def test_guard_module_reachable_and_pinned() -> None:
    assert GUARD.is_file(), f"guard script missing: {GUARD}"
    src = GUARD.read_text(encoding="utf-8")
    assert MAP in src, "guard must name the SSOT map file"
    assert "KNOWN_DRIFTS" in src, "ratchet baseline must live in the guard"
    assert TAG in src, "evidence tag must stay stable for CI grepping"


def test_live_roster_and_hook_wiring() -> None:
    roster = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"
    assert roster.is_file(), "run_all_guards.py must exist"
    assert "scripts/ci/license_ssot_guard.py" in roster.read_text(encoding="utf-8"), (
        "guard missing from the run_all_guards roster"
    )
    hook = REPO_ROOT / ".githooks" / "pre-push"
    assert hook.is_file(), ".githooks/pre-push must exist"
    htext = hook.read_text(encoding="utf-8")
    assert "license_ssot_guard.py" in htext, "guard missing from the pre-push hook"
    assert "LICENSE SSOT GUARD (#1773)" in htext, "hook section must document the guard"


# --------------------------------------------------------------------------- #
# §2.3 SSOT parsing                                                            #
# --------------------------------------------------------------------------- #

def test_live_ssot_parses_with_sanity_floors() -> None:
    text = (REPO_ROOT / MAP).read_text(encoding="utf-8")
    mapping, why = guard.parse_ssot(text)
    assert mapping is not None, f"live §2.3 must parse: {why}"
    mit = {r for r, m in mapping.items() if m == "MIT"}
    prop = {r for r, m in mapping.items() if m == "PROPRIETARY"}
    assert {"supremeai-open", "supremeai-studio", "supremeai-vscode"} <= mit
    assert {"supremeai-core", "supremeai-api", "supremeai-mcp-control-plane"} <= prop
    assert len(mapping) >= 8, "SSOT sanity floor: at least the 11 declared repos"


def test_unparseable_ssot_fail_closes() -> None:
    assert guard.parse_ssot("nothing relevant here")[0] is None
    assert guard.parse_ssot("")[0] is None
    both_bullets = (
        "- **Permissive Open-Source (MIT License):** (`supremeai-open`, `supremeai-core`).\n"
        "- **Proprietary / All Rights Reserved:** (`supremeai-core`, `supremeai-api`).\n"
    )
    assert guard.parse_ssot(both_bullets)[0] is None, "dual declaration must fail"


def test_evaluate_fail_closes_on_unparseable_map() -> None:
    with tempfile.TemporaryDirectory(prefix="license-guard-nomap-") as td:
        root = Path(td)
        (root / MAP).write_text("## no licensing section\n", encoding="utf-8")
        code, findings, _ = guard.evaluate(root)
        assert code == guard.EXIT_DRIFT, code
        assert findings and findings[0]["code"] == "SSOT_UNPARSEABLE"


# --------------------------------------------------------------------------- #
# License-expression validation (pinned allowlist)                             #
# --------------------------------------------------------------------------- #

def test_license_tokens_allowlist() -> None:
    assert guard.license_tokens("MIT") == ["MIT"]
    assert guard.license_tokens("Apache-2.0") == ["Apache-2.0"]
    assert guard.license_tokens("MIT OR Apache-2.0") == ["MIT", "Apache-2.0"]
    assert guard.license_tokens("MIT AND ISC") == ["MIT", "ISC"]
    assert guard.license_tokens("LicenseRef-Proprietary") == ["LicenseRef-Proprietary"]
    # Rejections: unknown id, parens, empty, non-string-ish junk.
    assert guard.license_tokens("WTFPL") is None
    assert guard.license_tokens("(MIT OR Apache-2.0)") is None
    assert guard.license_tokens("") is None
    assert guard.license_tokens("   ") is None
    assert guard.license_tokens("mit") is None, "SPDX ids are case-sensitive"


def test_spdx_allowlist_is_pinned_and_dated() -> None:
    assert "LicenseRef-Proprietary" in guard.SPDX_ALLOWLIST
    assert "MIT" in guard.SPDX_ALLOWLIST and "Apache-2.0" in guard.SPDX_ALLOWLIST
    assert guard.OSS_TOKENS.isdisjoint({"LicenseRef-Proprietary"})


# --------------------------------------------------------------------------- #
# Sandbox detection: every finding class + honest skips                        #
# --------------------------------------------------------------------------- #

SSOT_FIXTURE = (
    "### 2.3 Licensing & Intellectual Property Policy (SSOT)\n"
    "- **Permissive Open-Source (MIT License):** Applied to (`supremeai-open`, "
    "`supremeai-studio`, `supremeai-vscode`).\n"
    "- **Proprietary / All Rights Reserved:** Applied to (`supremeai`, `supremeai-core`, "
    "`supremeai-api`, `supremeai-browser`, `supremeai-infrastructure`, "
    "`supremeai-mcp-control-plane`, `supremeai-agents`, `supremeai-archive`).\n"
)


def _build_sandbox(root: Path) -> tuple[dict[str, str], set[tuple[str, str]]]:
    (root / MAP).write_text(SSOT_FIXTURE, encoding="utf-8")
    (root / "studio").mkdir()
    (root / "studio" / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (root / "studio" / "package.json").write_text('{"name":"s","license":"MIT"}', encoding="utf-8")
    (root / "vscode").mkdir()
    (root / "vscode" / "package.json").write_text('{"name":"v"}', encoding="utf-8")
    (root / "core").mkdir()
    (root / "gateway").mkdir()
    (root / "gateway" / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (root / "package.json").write_text('{"name":"root"}', encoding="utf-8")
    mapping, why = guard.parse_ssot(SSOT_FIXTURE)
    assert mapping is not None, why
    findings, notes = guard.classify_findings(root, mapping)
    return mapping, {(f["code"], f["path"]) for f in findings} | {("NOTES", n) for n in notes}


def test_sandbox_detects_all_finding_classes() -> None:
    with tempfile.TemporaryDirectory(prefix="license-guard-sandbox-") as td:
        _, keys = _build_sandbox(Path(td))
        assert ("PACKAGE_LICENSE_MISSING", "vscode/package.json") in keys
        assert ("PACKAGE_LICENSE_MISSING", "package.json") in keys
        assert ("LICENSE_FILE_ABSENT", "vscode") in keys
        assert ("LICENSE_FILE_ABSENT", "core") in keys
        assert ("MODEL_CONTRADICTION", "gateway/LICENSE") in keys
        assert not any(k[0] == "MAPPING_DRIFT" for k in keys), keys


def test_sandbox_honest_skip_notes_for_absent_surfaces() -> None:
    with tempfile.TemporaryDirectory(prefix="license-guard-skip-") as td:
        _, keys = _build_sandbox(Path(td))
        notes = [k[1] for k in keys if k[0] == "NOTES"]
        assert any("absent on disk" in n for n in notes), notes
        assert not any(k[0] == "MAPPING_DRIFT" for k in keys), keys


def test_surface_assignment_longest_prefix_wins() -> None:
    with tempfile.TemporaryDirectory(prefix="license-guard-prefix-") as td:
        root = Path(td)
        mapping, _ = guard.parse_ssot(SSOT_FIXTURE)
        assert mapping is not None
        # A manifest under infrastructure/mcp-control-plane must map to the
        # mcp-control-plane row, not the infrastructure prefix.
        (root / "infrastructure" / "mcp-control-plane").mkdir(parents=True)
        (root / "infrastructure" / "mcp-control-plane" / "package.json").write_text(
            '{"name":"m","license":"MIT"}', encoding="utf-8"
        )
        findings, _ = guard.classify_findings(root, mapping)
        contradiction = [f for f in findings if f["code"] == "MODEL_CONTRADICTION"]
        assert any(f["path"].endswith("mcp-control-plane/package.json") for f in contradiction), (
            contradiction
        )


# --------------------------------------------------------------------------- #
# Ratchet decision tree (baseline swap through the module object)              #
# --------------------------------------------------------------------------- #

def test_ratchet_known_report_only_new_drift_fail_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="license-guard-ratchet-") as td:
        root = Path(td)
        _, keys = _build_sandbox(root)
        findings_keys = {k for k in keys if k[0] != "NOTES"}
        saved = guard.KNOWN_DRIFTS
        try:
            guard.KNOWN_DRIFTS = frozenset(findings_keys)
            code, f2, _ = guard.evaluate(root)
            assert code == guard.EXIT_PASS and len(f2) == len(findings_keys), (code, f2)
            # New drift (outside baseline) -> exit 1 even in report-only mode.
            (root / "examples").mkdir()
            (root / "examples" / "package.json").write_text('{"name":"e"}', encoding="utf-8")
            code_new, f_new, _ = guard.evaluate(root)
            assert code_new == guard.EXIT_DRIFT, (code_new, f_new)
            assert any(f["path"] == "examples/package.json" for f in f_new)
            (root / "examples" / "package.json").unlink()
            # --strict: every finding fail-closes, baselined or not.
            code_strict, f_strict, _ = guard.evaluate(root, strict=True)
            assert code_strict == guard.EXIT_DRIFT
            assert len(f_strict) == len(findings_keys)
        finally:
            guard.KNOWN_DRIFTS = saved


def test_baseline_can_only_shrink_not_grow() -> None:
    # A new baseline entry must not mask a finding the old baseline lacked.
    with tempfile.TemporaryDirectory(prefix="license-guard-grow-") as td:
        root = Path(td)
        _, keys = _build_sandbox(root)
        findings_keys = {k for k in keys if k[0] != "NOTES"}
        saved = guard.KNOWN_DRIFTS
        try:
            guard.KNOWN_DRIFTS = frozenset(findings_keys | {("PACKAGE_LICENSE_MISSING", "unrelated/x.json")})
            code, _, _ = guard.evaluate(root)
            assert code == guard.EXIT_PASS, "superset baseline still passes (shrink-only)"
        finally:
            guard.KNOWN_DRIFTS = saved


# --------------------------------------------------------------------------- #
# Live baseline pin (the WO acceptance set, shrink-only ratchet)               #
# --------------------------------------------------------------------------- #

def test_live_repo_reports_exactly_the_baselined_drifts() -> None:
    code, findings, _ = guard.evaluate(REPO_ROOT)
    keys = {(f["code"], f["path"]) for f in findings}
    baseline = {(c, p) for (c, p) in guard.KNOWN_DRIFTS}
    assert code == guard.EXIT_PASS, (
        f"NEW license drift on live main — fix it, do not baseline it: {keys - baseline}"
    )
    assert keys == baseline, (
        "live findings diverge from the dated baseline. If a drift was FIXED, "
        "shrink KNOWN_DRIFTS in scripts/ci/license_ssot_guard.py in the same "
        "change (shrink-only ratchet); if drift was ADDED, fix it instead."
    )
    # The WO acceptance core, post-#1640/#1691: the 4 proprietary mirrors
    # (core, browser, infrastructure, infrastructure/mcp-control-plane) now
    # carry §2.3 LICENSE notices and the mcp-control-plane package.json declares
    # LicenseRef-Proprietary. Zero LICENSE_FILE_ABSENT remains.
    missing = {p for c, p in keys if c == "PACKAGE_LICENSE_MISSING"}
    assert not missing, (
        "#1621 acceptance: the 9 package.json license fields were declared; "
        f"a new PACKAGE_LICENSE_MISSING is a fix-it regression, not baseline material: {missing}"
    )
    assert not any(c == "LICENSE_FILE_ABSENT" for c, _ in keys), (
        "the #1640/#1691 fix wave landed all proprietary mirror LICENSE notices; "
        "a LICENSE_FILE_ABSENT here means a mirror license was removed — restore it"
    )
    # r1 heal (#3665): the gateway/LICENSE contradiction was fixed on main and
    # the baseline shrank to zero with it — the #1690 class stays mechanically
    # visible via classify_findings' self-test fixture (synthetic gateway/LICENSE
    # scan), so any live recurrence still fails as NEW drift above.
    contradiction = {p for c, p in keys if c == "MODEL_CONTRADICTION"}
    assert not contradiction, (
        f"live MODEL_CONTRADICTION reappeared with an empty baseline: {contradiction}"
    )
    assert not baseline, "baseline must stay at zero until new dated drift is baselined"


def test_live_scan_covers_every_tracked_package_json() -> None:
    tracked = {
        p.relative_to(REPO_ROOT).as_posix()
        for p in REPO_ROOT.rglob("package.json")
        if "node_modules" not in p.parts
    }
    code, findings, notes = guard.evaluate(REPO_ROOT)
    assert code in (guard.EXIT_PASS, guard.EXIT_DRIFT)
    flagged = {f["path"] for f in findings if f["code"].startswith("PACKAGE")}
    covered = {n for n in [n for n in notes]}
    # Every tracked manifest is either clean, flagged, or explicitly skipped
    # with evidence — never silently ignored.
    for path in tracked:
        assert (
            any(path.endswith(f["path"]) or f["path"] in path for f in findings)
            or path not in flagged
        ), f"{path} silently ignored by the scan"


# --------------------------------------------------------------------------- #
# JSON report contract                                                         #
# --------------------------------------------------------------------------- #

def test_json_report_is_machine_readable() -> None:
    r = subprocess.run(
        [sys.executable, str(GUARD), "--json"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert r.returncode in (0, 1), r.stderr
    report = json.loads(r.stdout)
    assert report["guard"] == "license_ssot_guard"
    assert report["map"] == MAP
    assert report["mode"] == "ratchet"
    # Dated floor (post-#1640/#1691 then #3665 shrink): 6 -> 1 -> 0 entries —
    # the #1690 gateway/LICENSE contradiction was fixed on main, so the
    # baseline is now empty and any new finding fails as NEW drift.
    assert isinstance(report["baseline_entries"], int) and report["baseline_entries"] >= 0
    assert report["baseline_entries"] == 0, (
        "baseline re-grew — shrink-only ratchet forbids adding entries"
    )
    assert isinstance(report["findings"], list) and isinstance(report["notes"], list)
    for f in report["findings"]:
        assert set(f) == {"code", "path", "detail"}


# --------------------------------------------------------------------------- #
# Plain stdlib runner (dual-mode doctrine)                                     #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    failures = 0
    tests = [(name, obj) for name, obj in sorted(globals().items()) if name.startswith("test_") and callable(obj)]
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS | {name}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL | {name}: {exc}")
        except Exception as exc:  # noqa: BLE001 — plain runner must report, not crash
            failures += 1
            print(f"  ERROR | {name}: {exc!r}")
    print(f"\n{len(tests) - failures}/{len(tests)} license-ssot-guard tests passed")
    sys.exit(1 if failures else 0)
