#!/usr/bin/env python3
"""satellite_trigger_integrity_guard.py — preventive tripwire for satellite
mirror workflow push-trigger integrity (#2511/#2512 sync-clobber family).

Why this guard exists (2026-10-30, GLM Agent 29, task-3538 cycle): while
triaging the browser-repo CI incident the agent lane nearly filed false
evidence that every satellite mirror carried a corrupted push filter. A
byte-count probe (occurrences of chr(91) + "main" + chr(93) counted on disk
and printed as numbers) proved all six mirror workflows intact — the
"corruption" existed only in the agent read-plane's rendered tool output,
where the literal bracket-main-bracket sequence was displayed as
"ain" + "]". LLM agents that eyeball rendered strings for byte-level claims
can manufacture defects that do not exist. This guard turns the trigger
surface into a machine count so the class stays closed:

  - every first-level <dir>/.github/workflows/*.y*ml (satellite mirrors)
  - the on.push section must carry a branches filter that includes the
    default branch "main" (flow sequence, quoted flow list, or block list)

Verdicts (fail-closed):
  INTACT                  — filter lists main
  TRIGGER_CLOBBERED       — branches value malformed / main missing
  UNFILTERED              — push section without any branches filter
                            (informational; runs on every branch by design)
  INSUFFICIENT_EVIDENCE   — no workflow files censused at all (exit 2)

Usage:
  python satellite_trigger_integrity_guard.py --self-test
  python satellite_trigger_integrity_guard.py --check --root /path/to/repo
  python satellite_trigger_integrity_guard.py --check --root . --json

Method note for byte-sensitive audits (#3538 lesson): never certify a
byte-level claim from a rendered string; count occurrences numerically.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_BRANCH = "main"

INTACT = "INTACT"
CLOBBERED = "TRIGGER_CLOBBERED"
UNFILTERED = "UNFILTERED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

# The on: block ends at the next top-level key (permissions:, jobs:, etc.).
TOP_LEVEL_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*:", re.MULTILINE)
PUSH_KEY = re.compile(r"^  push:\s*$", re.MULTILINE)
BRANCH_KEY = re.compile(r"^    branches:\s*(.*)$")
BLOCK_ITEM = re.compile(r"^      -\s+(\S+)")


def extract_push_branch_values(text: str) -> list[str] | None:
    """Return the raw branches filter tokens under on.push.

    None  -> the push section carries no branches filter (UNFILTERED)
    []    -> branches key present with an empty value
    [..]  -> parsed filter tokens
    """
    on_match = re.search(r"^on:", text, re.MULTILINE)
    if not on_match:
        return None
    on_end = TOP_LEVEL_KEY.search(text, on_match.end())
    on_block = text[on_match.start() : (on_end.start() if on_end else len(text))]
    push_match = PUSH_KEY.search(on_block)
    if not push_match:
        return None
    rest = on_block[push_match.end() :]
    push_end = re.search(r"^  [A-Za-z_][A-Za-z0-9_-]*:", rest, re.MULTILINE)
    push_block = on_block[push_match.start() : (push_match.end() + (push_end.start() if push_end else len(rest)))]
    for line in push_block.splitlines():
        m = BRANCH_KEY.match(line)
        if not m:
            continue
        raw = m.group(1).strip()
        if raw.startswith("["):
            close = raw.rfind("]")
            inner = raw[1 : close if close != -1 else len(raw)]
            return [tok.strip().strip("'\"") for tok in inner.split(",") if tok.strip()]
        if raw:
            return [raw]
        tokens = []
        for pline in push_block.splitlines():
            bm = BLOCK_ITEM.match(pline)
            if bm:
                tokens.append(bm.group(1))
        return tokens
    return []


def classify_branches(tokens: list[str] | None) -> str:
    if not tokens:
        return UNFILTERED
    if DEFAULT_BRANCH in tokens:
        return INTACT
    return CLOBBERED


def census_file(text: str) -> dict:
    tokens = extract_push_branch_values(text)
    return {"push_branches": tokens, "verdict": classify_branches(tokens)}


def census_surface(root: Path) -> tuple[list[dict], list[str]]:
    """Census every satellite mirror workflow: <dir>/.github/workflows/*.y*ml
    for first-level directories other than the repo-root .github itself."""
    rows: list[dict] = []
    files: list[str] = []
    if not root.is_dir():
        return rows, files
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        wf_dir = entry / ".github" / "workflows"
        if not wf_dir.is_dir():
            continue
        for wf in sorted(wf_dir.glob("*.y*ml")):
            files.append(str(wf))
            try:
                text = wf.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                rows.append({"file": str(wf), "verdict": INSUFFICIENT_EVIDENCE, "push_branches": None})
                continue
            rows.append({"file": str(wf), **census_file(text)})
    return rows, files


def _self_test() -> int:
    o, c = chr(91), chr(93)
    good = o + "main" + c  # assembled: never write the bracket-main-bracket literal inline
    intact_flow = "on:\n  push:\n    branches: " + good + "\n  pull_request:\njobs: {}\n"
    intact_block = "on:\n  push:\n    branches:\n      - main\n      - 'release/*'\njobs: {}\n"
    intact_list = "on:\n  push:\n    branches: ['main', 'release/*']\njobs: {}\n"
    clobber_scalar = "on:\n  push:\n    branches: ain" + c + "\n  pull_request:\njobs: {}\n"
    clobber_flow = "on:\n  push:\n    branches: [ain" + c + c + "\njobs: {}\n"
    unfiltered = "on:\n  push:\n  pull_request:\njobs: {}\n"
    no_push = "on:\n  pull_request:\njobs: {}\n"

    cases = [
        ("intact-flow", intact_flow, INTACT),
        ("intact-block", intact_block, INTACT),
        ("intact-list", intact_list, INTACT),
        ("clobber-scalar", clobber_scalar, CLOBBERED),
        ("clobber-flow", clobber_flow, CLOBBERED),
        ("unfiltered-push", unfiltered, UNFILTERED),
        ("no-push-section", no_push, UNFILTERED),
    ]
    failures = 0
    for name, text, want in cases:
        got = census_file(text)["verdict"]
        ok = got == want
        print(f"  self-test {name}: {got} {'PASS' if ok else 'FAIL'}")
        if not ok:
            failures += 1

    # Fail-closed: an empty surface must never certify the fleet.
    rows, _ = census_surface(Path("/nonexistent-root-that-has-no-mirrors"))
    ok = len(rows) == 0
    print(f"  self-test empty-surface: rows={len(rows)} {'PASS' if ok else 'FAIL'}")
    if not ok:
        failures += 1

    print(f"satellite_trigger_integrity_guard self-test: {'PASS' if failures == 0 else 'FAIL'} ({failures} failure(s))")
    return 0 if failures == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true", help="run offline fixtures and exit")
    parser.add_argument("--check", action="store_true", help="census satellite mirror triggers")
    parser.add_argument("--root", default=".", help="open-repo checkout holding the satellite mirrors")
    parser.add_argument("--json", action="store_true", help="print the census rows as JSON")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()
    if not args.check:
        parser.print_help()
        return 0

    root = Path(args.root)
    rows, files = census_surface(root)
    if not files:
        print("[satellite-trigger-integrity] no satellite mirror workflows found -> INSUFFICIENT_EVIDENCE")
        return 2

    bad = [r for r in rows if r["verdict"] == CLOBBERED]
    blind = [r for r in rows if r["verdict"] == INSUFFICIENT_EVIDENCE]
    verdict = "INTACT_FLEET" if not bad and not blind else "TRIGGER_DEFECT_FLEET"
    code = 0 if not bad and not blind else 2

    print(f"[satellite-trigger-integrity] files={len(files)} verdict={verdict} exit={code}")
    markers = {INTACT: "ok", CLOBBERED: "CLOBBER", UNFILTERED: "info", INSUFFICIENT_EVIDENCE: "blind"}
    for r in rows:
        print(f"  [{markers.get(r['verdict'], '?')}] {r['file']} branches={r.get('push_branches')}")
    if bad:
        o, c = chr(91), chr(93)
        print(
            "[satellite-trigger-integrity] clobbered mirrors leave push-CI mis-wired on the satellite "
            "default branch; fix is admin-lane (.github/** per #2512): set `branches: "
            + o
            + "main"
            + c
            + "` in each mirror and let federation_satellite_sync repair the satellites"
        )
    if args.json:
        print(json.dumps(rows, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
