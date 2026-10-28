#!/usr/bin/env python3
"""tests/test_radar_index_freshness_guard.py — fail-closed behavioral suite for #2091.

Verifies the R48 radar-index freshness gate delivered for #2091:

  - invariant A: every R<number> cited in the index's §2 summary tables has
    exactly one registry row; duplicate full-token rows are flagged;
  - invariant B (pointer truth): an advertised next-free number that its own
    registry already consumed fails CLOSED naming the exact R-number — the
    pass-3/4/6 collision class is replayed as three deterministic fixtures;
    pointer-context phrases (allocation rule, drift-log advances, "numbers
    not used" provenance) never self-trip the scans; a tracked filename
    embedding the pointer token fails;
  - invariant C: uppercase R-citations in docs/** resolve to registry rows
    (suffix -V/-VI/-c base-resolve; withdrawn §3-style labels resolve via
    base; lowercase commit-slang "r3" and the risk-engine R0 namespace are
    out of domain); vendored .agents/skills/** routes report-only (#1725);
  - ratchet semantics: baseline-pinned ghost keys report without blocking;
    NEW keys and GROWN counts on pinned keys fail-closed; resolved keys
    surface as improvements (shrink the baseline in the same change);
  - domain: scout R-numbers start at R1 — R0 is never a lane number;
  - live sweep: the real repo tree passes --check semantics (pointer parses,
    invariants hold, the shrink-only floor holds);
  - wiring SSOT: the guard is present in the LIVE run_all_guards.py roster
    and the LIVE .githooks/pre-push hook (section 16), never duplicated here.

Design (zero-dependency doctrine, dual mode — pytest + stdlib runners):

  - pytest:  pytest tests/test_radar_index_freshness_guard.py
  - stdlib:  python3 tests/test_radar_index_freshness_guard.py  (plain runner)

All tree scenarios are hermetic: built in tempdirs, offline, deterministic —
the same pattern as the guard's own --self-test.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "ci" / "radar_index_freshness_guard.py"
BASELINE = "scripts/ci/radar_index_freshness_baseline.json"
TAG = "[radar-index-freshness-guard]"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
import radar_index_freshness_guard as guard


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #

def make_tree(files: dict[str, str]) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="rifg-test-"))
    for rel, content in files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp


def index_doc(pointer: int, rows: list[int], anchors: str = "", extra: str = "") -> str:
    rows_md = "\n".join(f"| R{n} | `f.md` | lane | #1 | verdict | — |" for n in rows)
    return (
        "# Scout Radar Index\n\n"
        f"> **Allocation rule:** take the next free R-number FROM this index (next free: **R{pointer}**).\n\n"
        f"{extra}\n"
        "## 1. R-number registry\n\n"
        "| R# | Radar file | Lane | Filed | Verdict | Status |\n"
        "|----|-----------|------|-------|---------|--------|\n"
        f"{rows_md}\n\n"
        "## 2. Radar cycle anchors\n\n"
        f"{anchors}\n"
        "## 5. Honest limitations\n\nend\n"
    )


# --------------------------------------------------------------------------- #
# invariant A — registry completeness                                          #
# --------------------------------------------------------------------------- #

def test_anchor_ghost_flagged() -> None:
    root = make_tree({guard.INDEX_REL: index_doc(4, [1], anchors="| I | `f.md` (R99) | #1 | |")})
    r = guard.sweep(root)
    assert any(f["kind"] == "anchor-ghost" and f["token"] == "R99" for f in r["a"])


def test_duplicate_registry_row_flagged() -> None:
    doc = index_doc(4, [1]).replace(
        "| R1 | `f.md` | lane | #1 | verdict | — |\n",
        "| R1 | `f.md` | lane | #1 | verdict | — |\n| R1 | `g.md` | lane2 | #2 | verdict | — |\n",
    )
    root = make_tree({guard.INDEX_REL: doc})
    r = guard.sweep(root)
    assert any(f["kind"] == "duplicate-row" and f["token"] == "R1" for f in r["a"])


# --------------------------------------------------------------------------- #
# invariant B — pointer truth (the pass-3/4/6 collision class)                 #
# --------------------------------------------------------------------------- #

def test_pointer_taken_replays_three_logged_collisions() -> None:
    # Each logged same-day collision: the advertised pointer is already a row.
    for pointer in (37, 39, 45):  # passes 3, 4, 6
        root = make_tree({guard.INDEX_REL: index_doc(pointer, [1, pointer])})
        r = guard.sweep(root)
        assert any(f["kind"] == "pointer-taken" and f["pointer"] == pointer for f in r["b"]), pointer


def test_pointer_context_never_self_trips() -> None:
    extra = (
        "> **Drift log:** pass 11 — moves next free to **R51** (verified free repo-wide).\n>\n"
        "> **Numbers NOT used note:** none.\n"
    )
    root = make_tree({guard.INDEX_REL: index_doc(51, [1], extra=extra)})
    r = guard.sweep(root)
    assert r["pointer"] == 51
    assert not any(f["kind"] == "pointer-cited-in-index" for f in r["b"])


def test_pointer_in_tracked_filename_flagged() -> None:
    root = make_tree({guard.INDEX_REL: index_doc(51, [1]),
                      "docs/EVAL_2026-10-28-r51-lane-verdict.md": "# V\nmentions R1\n"})
    r = guard.sweep(root)
    assert any(f["kind"] == "pointer-in-filename" and f["pointer"] == 51 for f in r["b"])


def test_missing_pointer_flagged() -> None:
    doc = index_doc(4, [1]).replace("(next free: **R4**)", "(pointer deliberately omitted)")
    root = make_tree({guard.INDEX_REL: doc})
    r = guard.sweep(root)
    assert any(f["kind"] == "pointer-missing" for f in r["b"])


# --------------------------------------------------------------------------- #
# invariant C — citation existence                                             #
# --------------------------------------------------------------------------- #

def test_citation_ghost_flagged() -> None:
    root = make_tree({guard.INDEX_REL: index_doc(4, [1]),
                      "docs/d.md": "# D\ncites R98\n"})
    r = guard.sweep(root)
    assert any(f["base"] == 98 and f["file"] == "docs/d.md" for f in r["cits"])


def test_suffix_citation_resolves_via_base() -> None:
    doc = (
        "# Idx\n> Allocation rule (next free: **R4**).\n\n"
        "## 1. R\n| R# | F | L | I | V | S |\n|---|---|---|---|---|---|\n"
        "| R23-**V** | `v.md` | lane | #1 | verdict | — |\n"
        "| R23-**VI** | `vi.md` | lane | #2 | verdict | — |\n"
        "| R26 | `c.md` | lane | #3 | verdict | — |\n\n"
        "## 2. Anchors\n| III | `f.md` (R23-V, R23-VI) | #1 | |\n"
        "## 5. End\n"
    )
    root = make_tree({guard.INDEX_REL: doc, "docs/xi.md": "# XI\n~~R26-c~~ withdrawn\n"})
    r = guard.sweep(root)
    assert not r["a"] and not r["cits"]


def test_lowercase_slang_and_r0_namespace_ignored() -> None:
    root = make_tree({guard.INDEX_REL: index_doc(4, [1, 6]),
                      "docs/d.md": "# D\nr3 re-land slang; R0–R6 risk matrix; R6 scout lane\n"})
    r = guard.sweep(root)
    assert not r["cits"]


def test_vendored_citation_report_only() -> None:
    root = make_tree({guard.INDEX_REL: index_doc(4, [1]),
                      ".agents/skills/pack/SKILL.md": "# S\ncites R97\n"})
    r = guard.sweep(root)
    assert not r["cits"] and len(r["report_only"]) == 1


def test_nondocs_lane_out_of_scope() -> None:
    root = make_tree({guard.INDEX_REL: index_doc(4, [1]),
                      "AGENTS.md": "# A\ncites R98 outside docs/**\n"})
    r = guard.sweep(root)
    assert not r["cits"]


# --------------------------------------------------------------------------- #
# ratchet semantics (shrink-only floor over the citation-ghost class)          #
# --------------------------------------------------------------------------- #

def test_pinned_ghost_does_not_block() -> None:
    root = make_tree({guard.INDEX_REL: index_doc(4, [1]),
                      "docs/d.md": "# D\ncites R98\n"})
    r = guard.sweep(root)
    baseline = {"schema": "radar-index-freshness-baseline/1",
                "floor": [{"key": ["citation-ghost", "docs/d.md", 98], "allowed": 1}]}
    drift, _ = guard.compare(baseline, r["cits"])
    assert not drift


def test_grown_ghost_fails_and_resolved_ghost_improves() -> None:
    root = make_tree({guard.INDEX_REL: index_doc(4, [1]),
                      "docs/d.md": "# D\ncites R98: R98 again\n"})
    r = guard.sweep(root)
    baseline = {"schema": "radar-index-freshness-baseline/1",
                "floor": [{"key": ["citation-ghost", "docs/d.md", 98], "allowed": 1}]}
    drift, _ = guard.compare(baseline, r["cits"])
    assert len(drift) == 1 and drift[0]["kind"] == "grown" and drift[0]["now"] == 2
    empty_root = make_tree({guard.INDEX_REL: index_doc(4, [1])})
    r2 = guard.sweep(empty_root)
    drift2, imp = guard.compare(baseline, r2["cits"])
    assert not drift2 and len(imp) == 1 and imp[0]["kind"] == "resolved"


# --------------------------------------------------------------------------- #
# guard-the-guard + live sweep + wiring SSOT                                   #
# --------------------------------------------------------------------------- #

def test_self_test_passes() -> None:
    assert guard.self_test()


def test_live_repo_sweep_passes() -> None:
    r = guard.sweep(REPO_ROOT)
    assert "fatal" not in r
    # Pointer pin regenerated per the R48 gate's own instruction after #2145
    # (R51 registration) legitimately advanced the index next-free R51 -> R52,
    # and after #2172 (R52 registration) legitimately advanced it R52 -> R53.
    # Bump this literal ONLY together with a landed index-pointer advance.
    assert r["pointer"] == 53, "pointer drifted — regenerate expectation with the index"
    baseline = json.loads((REPO_ROOT / BASELINE).read_text(encoding="utf-8"))
    drift, _ = guard.compare(baseline, r["cits"])
    assert not drift, f"live citation-ghost drift: {drift}"


def test_wiring_roster_and_pre_push() -> None:
    roster = (REPO_ROOT / "scripts" / "ci" / "run_all_guards.py").read_text(encoding="utf-8")
    assert "scripts/ci/radar_index_freshness_guard.py" in roster, "guard missing from the live roster"
    hook = (REPO_ROOT / ".githooks" / "pre-push").read_text(encoding="utf-8")
    assert "RADAR INDEX FRESHNESS GUARD (#2091)" in hook, "guard missing from the live pre-push hook"
    assert guard.GUARD_TAG in hook, "hook must invoke the guard's evidence tag"


# --------------------------------------------------------------------------- #
# stdlib plain runner                                                          #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    print(f"{len(fns) - failed}/{len(fns)} tests passed")
    sys.exit(1 if failed else 0)
