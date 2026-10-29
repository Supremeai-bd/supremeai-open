#!/usr/bin/env python3
"""bandit_sast_guard.py — Python source static-security ratchet gate (#1809).

Mission (issue #1809, scout radar lane R38):
    Every adjacent security surface has a machine gate — dependency CVEs
    (Trivy, #1735->#1768), CI workflows (zizmor, #1776), import contracts
    (import-linter, #1791), runtime LLM behavior (garak, #1748), secrets
    (gitleaks composite), license SSOT (#1796). The Python source plane had
    zero mechanical coverage: the 2026-10-28 scout scan found 45 HIGH-severity
    findings (weak hashes in session-store/crown-jewel routes, shell=True in
    the agent command executor and deploy switch, tarfile unsafe-members in
    the privileged backup-restore path) that were invisible until that
    one-off run. This guard makes that plane a shrink-only ratchet.

Behavior contract (the #1796 KNOWN_DRIFTS ratchet, externalized to a
versioned baseline because the Python surface carries ~919 finding pairs):

    1. Runs the pinned scanner (bandit 1.9.4) over the non-test Python
       surface: targets core scripts gateway browser skills examples
       infrastructure evals; excludes test-pattern files (test_*.py,
       *_test.py, conftest.py, anything under a tests/ dir) and the labeled
       teaching sample core/examples/sample_buggy.py. Post-filtering is done
       here (not via bandit globs) so the exclusion set is one piece of code,
       not scattered CLI glob semantics.
    2. Aggregates findings to (repo-relative path, test_id) -> count and
       compares against scripts/ci/bandit_sast_baseline.json:
         - a (path, id) pair absent from the baseline, or a count ABOVE the
           baselined count, is DRIFT;
         - counts at or below baseline are compliant (a lower count is an
           improvement — shrink the baseline entry in the same change, the
           file may only ever shrink).
    3. Routing (issue #1809 step 3 — triage routing, not agent fixes):
         - drift under scripts/** is fail-closed (exit 1): that surface is
           bridge-able, agents can and must fix it;
         - drift under the satellite mirrors (core/, gateway/, browser/,
           examples/, evals/, infrastructure/, skills/) is REPORT-ONLY
           (exit 0): per the #1809 never-do, agents never edit those mirrors;
           findings route to the owning satellite domain via the §2.2 table
           (U1/U3 — this guard never asserts private-repo state).
       The baseline itself is global: it may only shrink, on any surface.
    4. Honest degradation (#1760 oasdiff pattern): when bandit is not
       installed the guard skips with evidence (exit 0, note emitted) — it
       never fabricates a PASS. A tool-version mismatch is reported as a
       note, not a failure (the baseline provenance records the pin).
    5. `--baseline` regenerates the versioned baseline at the CURRENT head
       (admin action for the landing/floor reset; the diff of the baseline
       file in review IS the audit trail). `--json` emits a machine report.
       `--files f1 f2 ...` (pre-push mode) scans only the named files.

Never-do (issue #1809): no auto-fix mode (findings are triage inputs, not
auto-patches); the baseline may never grow; no agent edits to core/, browser/
or gateway/ mirrors (report-only routing); no scanning .github/**; no secret
values echoed (this guard reports paths, ids and counts — never code lines).

Usage:
    python scripts/ci/bandit_sast_guard.py --check            # roster mode
    python scripts/ci/bandit_sast_guard.py --files a.py b.py  # pre-push mode
    python scripts/ci/bandit_sast_guard.py --baseline         # regenerate floor
    python scripts/ci/bandit_sast_guard.py --json             # machine report
    python scripts/ci/bandit_sast_guard.py --self-test        # hermetic

Exit codes: 0 = pass / known-floor / honest skip · 1 = new drift (scripts/**)
· 2 = usage error.
"""

from __future__ import annotations

import argparse
import contextlib
import json
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
GUARD_TAG = "[bandit-sast-guard]"
BASELINE_PATH = Path("scripts/ci/bandit_sast_baseline.json")

EXIT_PASS = 0
EXIT_DRIFT = 1
EXIT_USAGE = 2

PINNED_BANDIT = "1.9.4"
SCAN_TARGETS = ("core", "scripts", "gateway", "browser", "skills", "examples", "infrastructure", "evals")
SCAN_TIMEOUT = 600
KNOWN_SAMPLE = "core/examples/sample_buggy.py"

# Surfaces where drift fail-closes (agent-bridge-able via the zero-credential
# bridge). Everything else in SCAN_TARGETS is a satellite mirror: report-only.
ENFORCED_PREFIXES = ("scripts/",)

BANDIT_ARGS = ("-q", "-r", "--exclude", "tests/conftest", "-f", "json")


def _evidence(msg: str) -> None:
    print(f"{GUARD_TAG} {msg}")


def is_test_path(path: str) -> bool:
    """The one exclusion predicate (docstring clause 1)."""
    parts = path.split("/")
    name = parts[-1]
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
        or any(seg == "tests" for seg in parts[:-1])
    )


def in_scan_targets(rel_path: str) -> bool:
    top = rel_path.split("/", 1)[0]
    return top in SCAN_TARGETS


def load_baseline(repo_root: Path) -> tuple[dict[str, dict[str, int]], dict]:
    """Load the versioned baseline. Unreadable baseline is fail-closed drift."""
    path = repo_root / BASELINE_PATH
    if not path.is_file():
        raise FileNotFoundError(f"baseline missing: {BASELINE_PATH} (run --baseline to create)")
    data = json.loads(path.read_text(encoding="utf-8"))
    findings = data.get("findings")
    if not isinstance(findings, dict):
        raise ValueError("baseline malformed: 'findings' must be an object")
    return findings, data.get("meta", {})


def bandit_version() -> str | None:
    exe = shutil.which("bandit")
    if exe is None:
        return None
    try:
        out = subprocess.run(
            [exe, "--version"], capture_output=True, text=True, timeout=30, check=False
        ).stdout
        for line in out.splitlines():
            if line.strip().startswith("bandit"):
                return line.split()[1].strip()
    except Exception:
        return "unknown"
    return "unknown"


def run_bandit_json(paths: list[str], cwd: Path) -> dict:
    """Invoke bandit and return the parsed JSON report. Raises on hard failure."""
    exe = shutil.which("bandit")
    if exe is None:
        raise FileNotFoundError("bandit binary not found on PATH")
    cmd = [exe, *BANDIT_ARGS, *paths]
    proc = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, errors="replace", timeout=SCAN_TIMEOUT, check=False
    )
    # bandit exits 1 when findings exist — that is not a scan failure.
    if proc.returncode not in (0, 1):
        raise RuntimeError(
            f"bandit exited {proc.returncode}: {(proc.stderr or '')[:400]}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"bandit produced unparseable JSON: {exc}") from exc


def aggregate(report: dict) -> tuple[dict[str, dict[str, int]], int, int]:
    """Aggregate a bandit JSON report to (path -> {test_id: count}).

    Applies the exclusion predicate (docstring clause 1). Returns
    (aggregates, raw_count, skipped_count). Bandit emits repo-CWD-relative
    POSIX paths already; normalize defensively anyway.
    """
    agg: dict[str, dict[str, int]] = {}
    raw = skipped = 0
    for item in report.get("results", []):
        raw += 1
        rel = str(item.get("filename", "")).replace("\\", "/").lstrip("./")
        if not rel:
            skipped += 1
            continue
        if is_test_path(rel) or rel == KNOWN_SAMPLE:
            skipped += 1
            continue
        if not in_scan_targets(rel):
            skipped += 1
            continue
        tid = str(item.get("test_id", "UNKNOWN"))
        agg.setdefault(rel, {})
        agg[rel][tid] = agg[rel].get(tid, 0) + 1
    return agg, raw, skipped


def compare(
    current: dict[str, dict[str, int]], baseline: dict[str, dict[str, int]]
) -> tuple[list[dict], list[dict], list[dict]]:
    """Ratchet compare. Returns (drift, improvements, notes).

    drift: list of {path, test_id, baseline, current, surface}
    improvements: baselined pairs whose count shrank (shrink-the-baseline hints)
    """
    drift: list[dict] = []
    improvements: list[dict] = []
    for path in sorted(current):
        for tid in sorted(current[path]):
            cur = current[path][tid]
            base = baseline.get(path, {}).get(tid, 0)
            if cur > base:
                drift.append(
                    {
                        "path": path,
                        "test_id": tid,
                        "baseline": base,
                        "current": cur,
                        "surface": path.split("/", 1)[0],
                    }
                )
            elif base > 0 and cur < base:
                improvements.append({"path": path, "test_id": tid, "baseline": base, "current": cur})
    return drift, improvements, []


def build_baseline_report(repo_root: Path) -> dict:
    """Full-surface scan -> the versioned baseline document (docstring clause 5)."""
    existing = [t for t in SCAN_TARGETS if (repo_root / t).is_dir()]
    report = run_bandit_json(existing, repo_root)
    agg, _raw, _skipped = aggregate(report)
    total = sum(sum(counts.values()) for counts in agg.values())
    head = "unknown"
    try:
        head = subprocess.run(
            ["git", "log", "-1", "--format=%h %ad", "--date=short"],
            cwd=repo_root, capture_output=True, text=True, timeout=30, check=False,
        ).stdout.strip() or "unknown"
    except subprocess.SubprocessError as exc:
        # provenance is best-effort — but never a silent swallow (B110-clean):
        # the failure itself becomes the recorded evidence.
        head = f"unknown (git probe failed: {exc.__class__.__name__})"
    return {
        "meta": {
            "issue": 1809,
            "tool": "bandit",
            "tool_version": PINNED_BANDIT,
            "command": "bandit " + " ".join([*BANDIT_ARGS, "<targets>"]),
            "head": head,
            "dated": "2026-10-28",
            "exclusions": [
                "test-pattern files (test_*.py, *_test.py, conftest.py, any tests/ dir)",
                f"{KNOWN_SAMPLE} (labeled teaching sample)",
                "paths outside the scan targets",
            ],
            "totals": {
                "findings_in_baseline": total,
                "files": len(agg),
                "pairs": sum(len(counts) for counts in agg.values()),
            },
            "doctrine": (
                "shrink-only ratchet: entries may only be REMOVED (in the same change "
                "that fixes them); counts may only shrink. New (path, id) pairs or "
                "grown counts are drift."
            ),
        },
        "findings": dict(sorted(agg.items())),
    }


def evaluate(repo_root: Path, files: list[str] | None = None) -> tuple[int, list[dict], list[dict], list[str]]:
    """Single decision tree. Returns (exit, drift, improvements, notes)."""
    notes: list[str] = []
    version = bandit_version()
    if version is None:
        notes.append(
            f"bandit not installed — skipped with evidence (honest degradation, "
            f"#1760 pattern; pip install bandit=={PINNED_BANDIT} to enable)"
        )
        return EXIT_PASS, [], [], notes
    if version not in (PINNED_BANDIT, "unknown"):
        notes.append(f"bandit version {version} != pinned {PINNED_BANDIT} — proceeding with evidence note")
    try:
        baseline, _meta = load_baseline(repo_root)
    except (FileNotFoundError, ValueError) as exc:
        return EXIT_DRIFT, [{"path": str(BASELINE_PATH), "test_id": "BASELINE", "baseline": 0, "current": 0, "surface": "meta", "detail": str(exc)}], [], notes

    if files:
        targets = [f for f in files if f.endswith(".py") and in_scan_targets(Path(f).as_posix())]
        if not targets:
            notes.append("no scanned-surface .py files in the changed set — nothing to scan")
            return EXIT_PASS, [], [], notes
        report = run_bandit_json(targets, repo_root)
    else:
        existing = [t for t in SCAN_TARGETS if (repo_root / t).is_dir()]
        report = run_bandit_json(list(existing), repo_root)

    current, raw, skipped = aggregate(report)
    notes.append(f"scan: {raw} raw finding(s), {skipped} excluded by the guard predicate")
    drift, _improvements, _ = compare(current, baseline)
    enforced = [d for d in drift if d["path"].startswith(ENFORCED_PREFIXES)]
    report_only = [d for d in drift if not d["path"].startswith(ENFORCED_PREFIXES)]
    if enforced:
        return EXIT_DRIFT, enforced, report_only, notes
    return EXIT_PASS, [], drift, notes


def render(drift: list[dict], report_only: list[dict], improvements: list[dict], notes: list[str]) -> None:
    for note in notes:
        _evidence(f"note | {note}")
    for d in report_only:
        _evidence(
            f"SATELLITE-DRIFT (report-only, routes to {d['surface']}) | {d['path']} | "
            f"{d['test_id']} | baseline {d['baseline']} -> current {d['current']}"
        )
    for d in drift:
        _evidence(
            f"NEW-DRIFT (fail-closed) | {d['path']} | {d['test_id']} | "
            f"baseline {d['baseline']} -> current {d['current']}"
        )
    for imp in improvements:
        _evidence(
            f"IMPROVED (shrink the baseline entry in the same change) | {imp['path']} | "
            f"{imp['test_id']} | {imp['baseline']} -> {imp['current']}"
        )
    if not drift and not report_only and not improvements:
        _evidence("ratchet clean: no new or grown findings on the scanned surface")


def self_test() -> bool:
    """Hermetic guard-the-guard (offline; fixtures, no bandit needed)."""
    print("[self-test] Running bandit SAST guard tests...")
    import bandit_sast_guard as g

    # 1. Exclusion predicate: the exact #1809 exclusion set.
    assert not g.is_test_path("scripts/ci/bandit_sast_guard.py")
    assert g.is_test_path("core/tests/test_x.py")
    assert g.is_test_path("scripts/agents/test_foo.py")
    assert g.is_test_path("core/api/conftest.py")
    assert g.is_test_path("gateway/tests/unit/deep_test.py")
    assert not g.is_test_path("scripts/ci/data/fixture.py")
    assert g.in_scan_targets("core/api/x.py") and not g.in_scan_targets("studio/src/x.ts")
    assert not g.in_scan_targets(".github/workflows/x.yml")
    print("  PASS | exclusion predicate: test-patterns, targets, .github excluded")
    # 2. Aggregation: exclusions + counting.
    fake = {
        "results": [
            {"filename": "scripts/a.py", "test_id": "B602", "issue_severity": "HIGH"},
            {"filename": "scripts/a.py", "test_id": "B602", "issue_severity": "HIGH"},
            {"filename": "scripts/test_a.py", "test_id": "B101"},
            {"filename": "core/examples/sample_buggy.py", "test_id": "B102"},
            {"filename": "core/b.py", "test_id": "B324"},
            {"filename": "studio/outside.py", "test_id": "B101"},
        ]
    }
    agg, raw, skipped = g.aggregate(fake)
    assert raw == 6 and skipped == 3, (raw, skipped)
    assert agg == {"scripts/a.py": {"B602": 2}, "core/b.py": {"B324": 1}}, agg
    print("  PASS | aggregation: counts, test-file + sample + off-target exclusions")
    # 3. Ratchet compare: new pair, grown count, shrunk count, equal count.
    baseline = {"scripts/a.py": {"B602": 2}, "core/b.py": {"B324": 1}}
    drift, improvements, _ = g.compare({"scripts/a.py": {"B602": 2}, "core/b.py": {"B324": 1}}, baseline)
    assert not drift and not improvements
    drift, _, _ = g.compare({"scripts/new.py": {"B105": 1}}, baseline)
    assert drift and drift[0]["path"] == "scripts/new.py"
    drift, _, _ = g.compare({"scripts/a.py": {"B602": 3}}, baseline)
    assert drift and drift[0]["current"] == 3
    _, improvements, _ = g.compare({"scripts/a.py": {"B602": 1}}, baseline)
    assert improvements and improvements[0]["current"] == 1
    print("  PASS | ratchet: equal/grown/shrunk/new-pair semantics")
    # 4. Decision tree on a sandbox repo: scripts drift exit 1, satellite drift
    #    report-only exit 0, honest skip when bandit is absent.
    with tempfile.TemporaryDirectory(prefix="bandit-sast-guard-") as td:
        root = Path(td)
        (root / "scripts" / "ci").mkdir(parents=True)
        (root / BASELINE_PATH).write_text(
            json.dumps({"meta": {"issue": 1809}, "findings": {"core/b.py": {"B324": 1}}}),
            encoding="utf-8",
        )
        saved_run, saved_ver = g.run_bandit_json, g.bandit_version
        try:
            g.bandit_version = lambda: "1.9.4"
            g.run_bandit_json = lambda paths, cwd: {
                "results": [
                    {"filename": "scripts/new.py", "test_id": "B602"},
                    {"filename": "core/b.py", "test_id": "B324"},
                    {"filename": "core/c.py", "test_id": "B324"},
                ]
            }
            code, drift, report_only, _notes = g.evaluate(root)
            assert code == EXIT_DRIFT and drift[0]["path"] == "scripts/new.py", (code, drift)
            assert any(d["path"] == "core/c.py" for d in report_only), report_only
            assert not any(d["path"] == "core/b.py" for d in drift + report_only)
            print("  PASS | decision tree: scripts fail-closed, satellite report-only")
            # --files filtering: non-.py and off-target files produce an honest skip.
            code2, drift2, _ro2, notes2 = g.evaluate(root, files=["README.md", "studio/x.py"])
            assert code2 == EXIT_PASS and not drift2 and any("nothing to scan" in n for n in notes2)
            print("  PASS | --files mode: off-target changed set -> honest skip")
            g.bandit_version = lambda: None
            code3, _, _, notes3 = g.evaluate(root)
            assert code3 == EXIT_PASS and any("not installed" in n for n in notes3)
            print("  PASS | bandit absent -> skip with evidence, never a fake PASS")
            # Malformed baseline is fail-closed, never a silent pass.
            (root / BASELINE_PATH).write_text("{not json", encoding="utf-8")
            g.bandit_version = lambda: "1.9.4"
            code4, drift4, _, _ = g.evaluate(root)
            assert code4 == EXIT_DRIFT and drift4[0]["test_id"] == "BASELINE"
            print("  PASS | malformed baseline -> fail-closed")
        finally:
            g.run_bandit_json, g.bandit_version = saved_run, saved_ver
    # 5. Live wiring: roster + pre-push carry the guard (when run inside the repo).
    roster = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"
    if roster.is_file():
        assert "scripts/ci/bandit_sast_guard.py" in roster.read_text(encoding="utf-8"), (
            "guard missing from run_all_guards roster"
        )
    hook = REPO_ROOT / ".githooks" / "pre-push"
    if hook.is_file():
        assert "bandit_sast_guard.py" in hook.read_text(encoding="utf-8"), (
            "guard missing from pre-push hook"
        )
    print("  PASS | roster + pre-push wiring present (when run inside the repo)")
    # 6. Baseline provenance sanity (when run inside the repo).
    bl_path = REPO_ROOT / BASELINE_PATH
    if bl_path.is_file():
        meta = json.loads(bl_path.read_text(encoding="utf-8")).get("meta", {})
        assert meta.get("tool") == "bandit" and meta.get("tool_version") == PINNED_BANDIT
        assert meta.get("doctrine", "").startswith("shrink-only")
    print("[self-test] bandit SAST guard self-tests PASSED (6 test cases)!")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Python source static-security ratchet gate (#1809, bandit)"
    )
    parser.add_argument("--check", action="store_true", help="roster mode: full-surface ratchet compare")
    parser.add_argument("--files", nargs="*", help="pre-push mode: scan only these files")
    parser.add_argument("--baseline", action="store_true", help="regenerate the versioned baseline at current head (admin)")
    parser.add_argument("--json", action="store_true", help="machine-readable report on stdout")
    parser.add_argument("--self-test", action="store_true", help="hermetic self-test suite (offline)")
    args = parser.parse_args()

    if args.self_test:
        return EXIT_PASS if self_test() else EXIT_DRIFT

    if args.baseline:
        doc = build_baseline_report(REPO_ROOT)
        out = REPO_ROOT / BASELINE_PATH
        out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        _evidence(
            f"baseline regenerated at {BASELINE_PATH} | head {doc['meta']['head']} | "
            f"{doc['meta']['totals']['findings_in_baseline']} finding(s) in "
            f"{doc['meta']['totals']['pairs']} pair(s) — review the diff; the file may only shrink"
        )
        return EXIT_PASS

    code, drift, report_only, notes = evaluate(REPO_ROOT, files=args.files or None)
    if args.json:
        print(
            json.dumps(
                {
                    "guard": "bandit_sast_guard",
                    "mode": "files" if args.files else "check",
                    "exit": code,
                    "pinned_bandit": PINNED_BANDIT,
                    "enforced_prefixes": list(ENFORCED_PREFIXES),
                    "new_drift": drift,
                    "satellite_drift_report_only": report_only,
                    "notes": notes,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        render(drift, report_only, [], notes)
    if code == EXIT_DRIFT:
        print(
            f"{GUARD_TAG} ❌ NEW Python-source security drift under {list(ENFORCED_PREFIXES)}: "
            f"fix it or extend the surface responsibly — the baseline may never grow.",
            file=sys.stderr,
        )
    return code


if __name__ == "__main__":
    sys.exit(main())
