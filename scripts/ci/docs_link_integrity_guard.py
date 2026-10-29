#!/usr/bin/env python3
"""docs_link_integrity_guard.py — R42 markdown internal-link integrity ratchet (#1938).

কেন (Why — Bengali, house style):
    #1909 প্রুন (২০৮ ডক ডিলিট) করার সময় কোনো গার্ড লিংক-গ্রাফ দেখেনি —
    রেফারেন্স রেখে যাওয়া ফাইল মুছে গেলে কেউ জানতই না। এই গার্ড সেই
    টেলিমেট্রি-গ্যাপ বন্ধ করে: প্রতিটি ট্র্যাকড .md-এর প্রতিটি ইন্টারনাল
    লিংক (ফাইল + অ্যাঙ্কর) রেজলভ করে, shrink-only বেসলাইনের সাথে তুলনা করে,
    নতুন ভাঙা লিংক fail-closed করে। এজেন্ট ফ্লিট ডকুমেন্টেশন দিয়ে নেভিগেট
    করে — ডেড লিংক মানে ভাঙা রাউটিং টেবিল, কসমেটিক সমস্যা নয়।

Verdict routing (single bookkeeping, no double-counting):
    - ratcheted   — self-owned lanes (docs/, core/, specs/, ...): NEW or
                    GROWN (file, target, reason) occurrences fail-closed.
                    The baseline may never grow; fixes shrink it.
    - report_only — vendored `.agents/skills/**` packs (#1725 lane, U1/U3):
                    never assert upstream state, never fail, routed to the
                    owning domain.
    - excluded    — `AGENT_RULES.md` ghost citations: constitution_pointer_guard
                    (#1642→#1708) already owns the deleted-authority citation
                    class with its own docs-debt allowlist. Counted for the
                    record, excluded from this gate's ratchet pressure.

Never-do (from #1938):
    No re-creation of deleted authority files; no edits to vendored
    .agents/skills content; no .github/** writes (#1643); no external-URL
    flakiness in verdicts (external schemes are ignored, never checked);
    no baseline growth ever.

Semantics (deterministic, stdlib-only, fully offline):
    - inline links `[text](target)` + reference definitions `[ref]: target`
    - external schemes (http/https/mailto/ftp/tel) and angle forms: ignored
    - `file://` targets: counted as file-uri hygiene findings (ratcheted in
      writable lanes — a developer's local disk path must not land again)
    - same-file `#anchor` and cross-file `path.md#anchor`: anchor validated
      with GitHub-style heading slugs
    - every occurrence counts (a broken link written twice is double damage)
    - exit 0 clean/report-only, exit 1 ratchet violation, exit 2 usage error

Modes:
    --check        roster mode: full-tree sweep vs the baseline (default)
    --files <p..>  pre-push mode: sweep only these changed .md files
    --baseline     regenerate the versioned baseline at the current head (admin)
    --json         machine-readable auditor report on stdout
    --self-test    hermetic offline fixture suite (guard-the-guard)

Run: python3 scripts/ci/docs_link_integrity_guard.py --check
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_TAG = "[docs-link-integrity-guard]"
BASELINE_PATH = Path("scripts/ci/docs_link_integrity_baseline.json")

# Anchor/pure-external walk exclusions (same class as the #1938 scout probe:
# no .git, no dependency trees, no build output).
EXCLUDED_DIRS = {
    ".git", "node_modules", "venv", ".venv", "env", ".env",
    "build", "dist", "out", "__pycache__", ".next", ".pytest_cache",
    "generated", ".mypy_cache", ".ruff_cache", ".tox", ".eggs",
}

VENDORED_PREFIX = ".agents/skills/"   # #1725 lane — report-only, never agent-fixed
EXCLUDED_TARGET_SUBSTR = "AGENT_RULES.md"  # #1642→#1708 pointer-guard debt

EXTERNAL_RE = re.compile(r"^(?:https?|mailto|ftp|tel):", re.IGNORECASE)
FILE_URI_RE = re.compile(r"^file://", re.IGNORECASE)
INLINE_LINK_RE = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
REF_DEF_RE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s+(\S+)\s*$", re.MULTILINE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
SAME_FILE_ANCHOR_RE = re.compile(r"^#(.+)$")


def _evidence(msg: str) -> None:
    """Stable-tagged evidence line — CI greps this."""
    print(f"{GUARD_TAG} {msg}")


def github_slug(text: str) -> str:
    """GitHub-style heading slug: NFKD, lowercase, drop punctuation, spaces->dashes."""
    t = unicodedata.normalize("NFKD", text.strip().lower())
    t = re.sub(r"[^\w\s-]", "", t, flags=re.UNICODE)
    t = re.sub(r"\s+", "-", t)
    return t.strip("-")


def anchors_of(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    found = set()
    for line in text.splitlines():
        m = HEADING_RE.match(line)
        if m:
            found.add(github_slug(m.group(2)))
    return found


def markdown_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS and not d.endswith(".egg-info")]
        for fn in filenames:
            if fn.lower().endswith(".md"):
                out.append(Path(dirpath) / fn)
    return sorted(out)


def classify(rel_file: str, target: str, reason: str) -> str:
    """Single-bookkeeping verdict: ratcheted | report_only | excluded."""
    if rel_file.startswith(VENDORED_PREFIX):
        return "report_only"          # vendored upstream — #1725 lane (U1/U3)
    if EXCLUDED_TARGET_SUBSTR in target:
        return "excluded"             # pointer-guard debt — #1642→#1708
    return "ratcheted"                # self-owned writable lanes


def sweep(root: Path, only_files: list[Path] | None = None) -> tuple[int, list[dict]]:
    """Resolve every internal link occurrence. Returns (checked, findings)."""
    files = markdown_files(root) if only_files is None else sorted(only_files)
    checked = 0
    findings: list[dict] = []
    for f in files:
        rel = f.relative_to(root).as_posix()
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        targets = [m.group(1) for m in INLINE_LINK_RE.finditer(text)]
        targets += REF_DEF_RE.findall(text)
        own_anchors: set[str] | None = None
        for raw in targets:
            t = raw.strip()
            if not t or t.startswith("<"):
                continue
            if EXTERNAL_RE.match(t):
                continue                      # external URLs deliberately out of scope
            checked += 1
            if FILE_URI_RE.match(t):
                findings.append({"file": rel, "target": t, "reason": "file-uri"})
                continue
            same = SAME_FILE_ANCHOR_RE.match(t)
            if same:
                if own_anchors is None:
                    own_anchors = anchors_of(f)
                if same.group(1) not in own_anchors:
                    findings.append({"file": rel, "target": t, "reason": "missing-anchor"})
                continue
            path_part, _, anchor = t.partition("#")
            path_part = path_part.split("?", 1)[0]
            if not path_part:
                continue                      # bare "#" placeholder — no routing claim
            cand = (root / path_part.lstrip("/")) if path_part.startswith("/") else (f.parent / path_part)
            try:
                resolved = cand.resolve()
            except OSError:
                resolved = cand
            inside = str(resolved).startswith(str(root.resolve()))
            if not resolved.exists() or not inside:
                reason = "missing-file"
                findings.append({"file": rel, "target": t, "reason": reason})
                continue
            if anchor:
                tgt = resolved
                if tgt.is_dir():
                    tgt = tgt / "README.md"
                    if not tgt.exists():
                        findings.append({"file": rel, "target": t, "reason": "missing-anchor"})
                        continue
                if anchor not in anchors_of(tgt):
                    findings.append({"file": rel, "target": t, "reason": "missing-anchor"})
    return checked, findings


def key_of(f: dict) -> tuple[str, str, str]:
    return (f["file"], f["target"], f["reason"])


def counts_of(findings: list[dict]) -> dict[tuple[str, str, str], int]:
    return dict(Counter(key_of(f) for f in findings))


def load_baseline(repo_root: Path) -> dict:
    p = repo_root / BASELINE_PATH
    if not p.is_file():
        _evidence(f"FAIL baseline missing: {BASELINE_PATH}")
        raise SystemExit(1)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _evidence(f"FAIL baseline malformed: {exc}")
        raise SystemExit(1)
    floor = data.get("ratchetedFloor") if isinstance(data, dict) else None
    if not isinstance(data, dict) or "schema" not in data or not isinstance(floor, list):
        _evidence("FAIL baseline schema unrecognised (need schema + ratchetedFloor entry list)")
        raise SystemExit(1)
    for e in floor:
        if not isinstance(e, dict) or not {"file", "target", "reason", "allowed"} <= set(e):
            _evidence(f"FAIL baseline ratchetedFloor entry malformed: {e!r}")
            raise SystemExit(1)
    return data


def compare(baseline: dict, findings: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Shrink-only ratchet. Returns (drift, report_only, improvements)."""
    floor = {(e["file"], e["target"], e["reason"]): int(e["allowed"])
             for e in baseline.get("ratchetedFloor", [])}
    current_all = counts_of(findings)
    verdict_by_key = {key_of(f): classify(f["file"], f["target"], f["reason"]) for f in findings}

    drift: list[dict] = []
    improvements: list[dict] = []
    for key, now in sorted(current_all.items()):
        verdict = verdict_by_key[key]
        if verdict != "ratcheted":
            continue
        allowed = floor.get(key, 0)
        if now > allowed:
            drift.append({"file": key[0], "target": key[1], "reason": key[2],
                          "now": now, "allowed": allowed, "kind": "grown" if key in floor else "new"})
        elif key in floor and now < allowed:
            improvements.append({"file": key[0], "target": key[1], "reason": key[2],
                                 "now": now, "allowed": allowed, "kind": "shrunk"})
    # keys that vanished entirely are improvements too
    for key, allowed in sorted(floor.items()):
        if key not in current_all:
            improvements.append({"file": key[0], "target": key[1], "reason": key[2],
                                 "now": 0, "allowed": allowed, "kind": "resolved"})
    return drift, [f for f in findings if verdict_by_key[key_of(f)] == "report_only"], improvements


def render(drift: list[dict], report_only: list[dict], excluded: list[dict], improvements: list[dict], checked: int) -> None:
    if improvements:
        for it in improvements:
            _evidence(f"SHRUNK {it['file']} -> {it['target']} ({it['reason']}) {it['allowed']}->{it['now']} "
                      f"(shrink the baseline entry in this same change)")
    if report_only:
        _evidence(f"REPORT-ONLY {len(report_only)} vendored .agents/skills finding(s) — routed to the #1725 lane, never agent-fixed")
        for r in report_only:
            print(f"  {GUARD_TAG} vendored: {r['file']} -> {r['target']} ({r['reason']})")
    if excluded:
        _evidence(f"EXCLUDED {len(excluded)} AGENT_RULES.md ghost citation(s) — owned by constitution_pointer_guard (#1642->#1708), not double-counted here")
    if drift:
        for d in drift:
            _evidence(f"DRIFT {d['kind']}: {d['file']} -> {d['target']} ({d['reason']}) {d['now']}/{d['allowed']}")
        _evidence(f"FAIL {len(drift)} new/grown ratcheted link-integrity finding(s) over {checked} checked — the baseline may never grow")
    else:
        _evidence(f"OK {checked} internal link occurrences swept; ratchet holds")


def self_test() -> bool:
    """Hermetic fixture suite — offline, tempdir, no repo mutation."""
    ok = True

    def check(name: str, cond: bool) -> None:
        nonlocal ok
        print(f"{'PASS' if cond else 'FAIL'} {name}")
        ok = ok and cond

    def tree(files: dict[str, str], baseline: dict | None) -> tuple[Path, Path]:
        tmp = Path(tempfile.mkdtemp(prefix="dlig-selftest-"))
        for rel, content in files.items():
            p = tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        base = {"schema": "docs-link-integrity-baseline/1",
                "generatedAt": "1970-01-01", "headAtGeneration": "test",
                "ratchetedFloor": {}, "knownReportOnly": [], "knownExcluded": []}
        if baseline:
            base.update(baseline)
        (tmp / BASELINE_PATH).parent.mkdir(parents=True, exist_ok=True)
        (tmp / BASELINE_PATH).write_text(json.dumps(base), encoding="utf-8")
        return tmp, tmp / BASELINE_PATH

    # S1: clean tree passes
    root, _ = tree({"docs/a.md": "# H\n\n[ok](b.md)\n", "docs/b.md": "# B\n"}, None)
    _, findings = sweep(root)
    check("S1 clean-tree-no-findings", not findings)

    # S2: new broken link is a ratchet drift
    root, _ = tree({"docs/a.md": "[dead](ghost.md)\n"}, None)
    _, findings = sweep(root)
    check("S2-missing-file-found", findings and findings[0]["reason"] == "missing-file"
          and classify(findings[0]["file"], findings[0]["target"], findings[0]["reason"]) == "ratcheted")

    # S3: baseline-pinned drift reports, does not fail
    root, basep = tree({"docs/a.md": "[dead](ghost.md)\n"},
                       {"ratchetedFloor": [{"file": "docs/a.md", "target": "ghost.md", "reason": "missing-file", "allowed": 1}]})
    checked, findings = sweep(root)
    drift, _ro, _im = compare(json.loads(basep.read_text()), findings)
    check("S3-pinned-drift-not-drift", checked == 1 and not drift)

    # S4: AGENT_RULES ghost routes excluded (pointer-guard debt, not ours)
    root, _ = tree({"docs/a.md": "[rules](../AGENT_RULES.md)\n"}, None)
    _, findings = sweep(root)
    check("S4-ghost-excluded", findings and classify(findings[0]["file"], findings[0]["target"], findings[0]["reason"]) == "excluded")

    # S5: vendored pack path routes report-only (#1725)
    root, _ = tree({".agents/skills/somepack/SKILL.md": "[x](missing.md)\n"}, None)
    _, findings = sweep(root)
    check("S5-vendored-report-only", findings and classify(findings[0]["file"], findings[0]["target"], findings[0]["reason"]) == "report_only")

    # S6: occurrence growth on a pinned key fails (double damage counts twice)
    root, basep = tree({"docs/a.md": "[d](ghost.md)\n\n[d2](ghost.md)\n"},
                       {"ratchetedFloor": [{"file": "docs/a.md", "target": "ghost.md", "reason": "missing-file", "allowed": 1}]})
    _, findings = sweep(root)
    drift, _ro, _im = compare(json.loads(basep.read_text()), findings)
    check("S6-grown-occurrence-fails", len(drift) == 1 and drift[0]["kind"] == "grown")

    # S7: valid GitHub-slug cross-file anchor resolves (not a finding)
    root, _ = tree({
        "docs/a.md": "[s](b.md#serve-an-agent-over-http)\n",
        "docs/b.md": "# T\n\n## Serve an agent over HTTP\n",
    }, None)
    _, findings = sweep(root)
    check("S7-valid-anchor-resolves", not findings)

    # S8: invalid cross-file anchor is a missing-anchor finding
    root, _ = tree({
        "docs/a.md": "[s](b.md#no-such-heading)\n",
        "docs/b.md": "# T\n",
    }, None)
    _, findings = sweep(root)
    check("S8-bad-anchor-found", findings and findings[0]["reason"] == "missing-anchor")

    # S9: external URLs are ignored (never checked, no flakiness)
    root, _ = tree({"docs/a.md": "[gh](https://github.com/x/y)\n[hi](mailto:a@b.c)\n"}, None)
    checked, findings = sweep(root)
    check("S9-external-ignored", checked == 0 and not findings)

    # S10: file:// hygiene is a ratcheted finding in writable lanes
    root, _ = tree({"docs/a.md": "[l](file:///f:/supremeai/spec.md)\n"}, None)
    _, findings = sweep(root)
    check("S10-file-uri-ratcheted", findings and findings[0]["reason"] == "file-uri"
          and classify(findings[0]["file"], findings[0]["target"], findings[0]["reason"]) == "ratcheted")

    # S11: resolved anchor that vanished -> improvement path does not crash compare
    root, basep = tree({"docs/a.md": "# fine\n"}, {"ratchetedFloor": [{"file": "docs/a.md", "target": "ghost.md", "reason": "missing-file", "allowed": 1}]})
    _, findings = sweep(root)
    drift, _ro, im = compare(json.loads(basep.read_text()), findings)
    check("S11-resolved-key-improves", not drift and len(im) == 1 and im[0]["kind"] == "resolved")

    print(f"{'SELF-TEST OK: docs_link_integrity_guard' if ok else 'SELF-TEST FAILED: docs_link_integrity_guard'}")
    return ok


def _git_head_provenance(root: Path) -> str:
    """Live generation provenance for baseline stamps (#2180).

    Returns "<short-hash> (<subject>)" for the repo at `root`; on any failure
    (hermetic sandboxes without git) returns an honest fallback instead of a
    frozen literal. Best-effort by design: provenance is informational — the
    gate's load-bearing field is ratchetedFloor only. Same helper shape as the
    radar guard's (#2180 class fix); deliberately duplicated, not shared, so
    each guard stays standalone-runnable in pre-push.
    """
    try:
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(root),
            capture_output=True, text=True, timeout=10,
        )
        subj = subprocess.run(
            ["git", "log", "-1", "--format=%s"], cwd=str(root),
            capture_output=True, text=True, timeout=10,
        )
        if head.returncode == 0 and subj.returncode == 0:
            h = head.stdout.strip()
            s = " ".join(subj.stdout.split())[:96]
            if h:
                return f"{h} ({s})" if s else h
    except (OSError, subprocess.SubprocessError):
        pass
    return "unknown (git unavailable at generation)"


def build_baseline(root: Path) -> dict:
    checked, findings = sweep(root)
    ratch: Counter = Counter()
    report_only: list[dict] = []
    excluded: list[dict] = []
    for f in findings:
        v = classify(f["file"], f["target"], f["reason"])
        if v == "ratcheted":
            ratch[key_of(f)] += 1
        elif v == "report_only":
            report_only.append(f)
        else:
            excluded.append(f)
    return {
        "schema": "docs-link-integrity-baseline/1",
        "generatedAt": datetime.now(timezone.utc).date().isoformat(),
        "headAtGeneration": _git_head_provenance(root),
        "probe": "scripts/ci/docs_link_integrity_guard.py",
        "note": "shrink-only floor: ratchetedFloor is an entry list; each entry pins (file, target, reason) -> allowed occurrence count; "
                "report_only = vendored .agents/skills (#1725 lane); excluded = AGENT_RULES.md ghosts (#1642->#1708). "
                "The floor may never grow.",
        "ratchetedFloor": [
            {"file": k[0], "target": k[1], "reason": k[2], "allowed": v}
            for k, v in sorted(ratch.items())
        ],
        "knownReportOnly": report_only,
        "knownExcluded": excluded,
        "checkedAtGeneration": checked,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="R42 markdown internal-link integrity ratchet (#1938)")
    parser.add_argument("--check", action="store_true", help="roster mode: full-tree sweep vs baseline (default)")
    parser.add_argument("--files", nargs="*", help="pre-push mode: sweep only these changed .md files")
    parser.add_argument("--baseline", action="store_true", help="regenerate the versioned baseline at current head (admin)")
    parser.add_argument("--json", action="store_true", help="machine-readable auditor report on stdout")
    parser.add_argument("--self-test", action="store_true", help="hermetic offline self-test suite")
    args = parser.parse_args()

    if args.self_test:
        return 0 if self_test() else 1

    root = REPO_ROOT

    if args.baseline:
        data = build_baseline(root)
        # #2180: the note is FILE-OWNED narrative history (genesis ratchet,
        # dated shrink stamps — pinned by tests); a canonical regen must carry
        # it forward instead of clobbering it with the builder's short template.
        # Provenance/checked fields stay builder-owned live stamps. Best-effort:
        # a missing/malformed prior baseline simply leaves the template note.
        p = root / BASELINE_PATH
        if p.is_file():
            try:
                prev = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(prev.get("note"), str) and prev["note"].strip():
                    data["note"] = prev["note"]
            except (OSError, json.JSONDecodeError):
                pass
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0

    baseline = load_baseline(root)
    only = [Path(p) for p in args.files] if args.files else None
    if only:
        # The pre-push hook feeds `git diff --name-only` output: repo-relative
        # paths. Normalize against the repo root BEFORE any is_file()/sweep use
        # (a relative Path silently raises ValueError inside relative_to()).
        only = [p if p.is_absolute() else root / p for p in only]
        for m in [str(p.relative_to(root)) for p in only if not p.is_file()]:
            _evidence(f"SKIP missing-file {m} (deleted in this push; roster full-sweep owns stranded targets)")
        only = [p for p in only if p.is_file()]
        if not only:
            _evidence("OK no surviving changed .md files to sweep")
            return 0
    checked, findings = sweep(root, only)
    drift, report_only, improvements = compare(baseline, findings)
    excluded = [f for f in findings if classify(f["file"], f["target"], f["reason"]) == "excluded"]

    if args.json:
        print(json.dumps({
            "guard": GUARD_TAG, "checked": checked, "mode": "files" if only else "check",
            "drift": drift, "reportOnly": report_only, "excluded": excluded,
            "improvements": improvements, "verdict": "fail" if drift else "pass",
        }, indent=2, ensure_ascii=False))
    else:
        render(drift, report_only, excluded, improvements, checked)
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
