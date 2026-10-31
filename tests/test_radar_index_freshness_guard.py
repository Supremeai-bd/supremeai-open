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
import re
import shutil
import subprocess
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
    # after #2172 (R52 registration) advanced it R52 -> R53, after #2196
    # (R53 registration) advanced it R53 -> R54, after #2230 (R54
    # registration) advanced it R54 -> R55, after #2249 (R55 adoption
    # + same-cycle registration) advanced it R55 -> R56, and after #2265
    # (R56 same-cycle filer registration) advanced it R56 -> R57, and after
    # #2262 (R57 vault lane, re-slotted from R56 per pass 18) advanced it
    # R57 -> R58, and after #2275 (R58 cohort lane, third-party same-cycle
    # registration per pass 19) advanced it R58 -> R60 — a double skip: the
    # successor slot was already issue-side adopted by #2286 (a board-cited
    # number fails the freeness-verification standard, so the pointer
    # advertises the next fully-clean number instead), and after #2300
    # (R60 client-plane lane, filer same-cycle registration per pass 20)
    # advanced it R60 -> R61, and after #2318 (R61 client-dispatch lane,
    # filer same-cycle registration per pass 21) advanced it R61 -> R62,
    # and after #2314 (R62 registration, its own pass 21 at 93aa098)
    # advanced it R61 -> R63 — then #2322's stale-branch overwrite landed
    # after #2314 and evicted the R62 row, regressing the pointer to 62
    # (the pass-9 cell-clobber class, witnessed live by this gate's own
    # invariant-D subject ghost); the pass-23 re-head restored the union
    # state (pointer R63, R62 row verbatim from 93aa098) and this pin
    # follows the restored pointer per the pass-9 re-head precedent (the
    # pin moves with the pointer on a landed re-head).
    # and after #2372 (R63 double-adoption reconciliation, pass 24) registered
    # the disambiguated rows R63-I (#2343 hooks-bootstrap) / R63-II (#2358
    # MCP-Registry) and advanced it R63 -> R64 (the successor slot's only
    # citation is the scout ticket's own title token — pass-15 self-ref class).
    # and after #2392 (R64 pointer-board agreement guard, pass 25) registered
    # the R64 row and advanced it R64 -> R65 (verified free: tracked scan
    # zero hits; 100-row board sweep zero citations outside the self-ref).
    # and after #2464 (radar-index integrity r2, pass 26) registered the
    # R65 (landed #2454, receipt-verified #2469) / R66 (claimed #2447,
    # receipts #2452/#2469) rows and advanced it R65 -> R67 (verified free:
    # tracked scan zero hits; 112-row board sweep zero citations).
    # and after #2497 (pass 27) registered the R67 row (landed #2492, closes
    # #2486 — invariant D's first live ratchet-drift FAIL on main) and
    # advanced it R67 -> R68 (verified free: tracked scan zero hits; subject
    # scan zero hits; tower capture zero citations, full 200-capture
    # rate-limited, disclosed).
    # and after pass 28 (cycle-35, Job 478344) registered the R68 row
    # (landed 9a13e19 / #2533, closes #2530 — pass-27 registration-default
    # class caught PRE-emptively before the guard ran, no red occurred) and
    # advanced it R68 -> R69 (verified free: tracked scan zero hits; subject
    # scan zero hits; 100-row tower queue capture zero citations).
    # and after pass 29 (cycle-40, Job 478338) registered the R69 row
    # (radar-doc be6e34f / receipt WO #2545 — pass-27 registration-default
    # class recurred, guard RED at HEAD: citation-ghost + subject-ghost pair)
    # and advanced it R69 -> R70 (verified free: tracked scan zero token hits
    # outside hash-substring false positives; tower queue capture zero
    # citations).
    # Bump this literal ONLY together with a landed index-pointer advance.
    # and after pass 30 (cycle-42, Job 478338) registered the R70 row
    # (landed b6ef339 / #2574, closes #2568 — pass-27 registration-default
    # class recurred a third time in five passes, guard RED at HEAD:
    # commit-subject-ghost single, code-plane landing) AND the R71 row
    # (open/claimed, peer scout #2586 — pass-26 adoption-staleness class
    # on the advertised-successor slot) and advanced it R70 -> R72
    # (verified free: tracked scan zero hits; subject scan zero hits;
    # 7-row tower queue capture windowTruncated false, zero citations).
    # and after pass 31 (cycle-43, Job 478338) registered the R72 row
    # (open/unclaimed, peer scout #2608 — annotations residual census,
    # fix surface tower-owner for the 118 non-repo-reachable tools)
    # PRE-EMPTIVELY before any landing cited the token (guard green at
    # registration time — the pass-28 pattern's second application) and
    # advanced it R72 -> R73 (verified free: tracked scan zero hits;
    # subject scan zero hits; 127-row tower queue capture windowTruncated
    # false, zero citations).
    # and after pass 32 (Job 477792, 22:45+08) registered the R73 row
    # (open/claimed, peer scout #2627 — annotations phase-3, pass-26
    # precedent: the advertised R73 was already cited issue-side at
    # allocation time, predicate failed loud BEFORE consumption) and the
    # R74 row (#2633, filer same-cycle registration per pass-5 — MCP
    # 2025-11-25 capability-surface census) and advanced it R73 -> R75 —
    # a corrected skip: the advertised slot itself was taken, so the
    # pointer advertises the next fully-clean number (verified free:
    # tracked scan zero hits; subject scan zero hits; 133-row tower queue
    # capture windowTruncated false, zero citations).
    # and after pass 33 (cycle-45, Job 478338) registered the R75 row
    # (open/claimed, peer scout #2654 — control-plane phantom dependency,
    # pass-26 precedent third application) PRE-EMPTIVELY before any
    # landing cited the token (guard green at registration time — the
    # pass-28 pattern's third application) and advanced it R75 -> R76
    # (verified free: tracked scan zero hits after defusing the cycle-44
    # detector pin's R76 scenery token in test_bridge_freshness.ts, same
    # commit; subject scan zero hits; label-sliced queue capture — the
    # work_queue response now truncates at ~4000ch, single-capture #2286
    # unretrievable — zero R76 citations across the captured classes).
    # and after pass 34 (cycle-46, Job 478338) registered the R76 row
    # (open/unclaimed, peer scout #2691 — guard capture-contract hardening,
    # adopting pass-33's drift-log discovery; pass-26 precedent fourth
    # application) PRE-EMPTIVELY before any landing cited the token (guard
    # green at registration time) and advanced it R76 -> R77 (verified
    # free: word-boundary tree scan zero hits — lockfile substring hits
    # are mid-hash, not citations; subject scan zero hits; label-sliced
    # queue capture zero R77 citations).
    # and after pass 35 (cycle-47, Job 478338) registered the R77 row
    # (open/claimed, peer scout #2718 — row-state truthfulness, filed
    # 18:37:02Z; pass-26 precedent fifth application; row-status refreshes
    # left to that lane's own fix surface) PRE-EMPTIVELY before any landing
    # cited the token (guard green at registration time) and advanced it
    # R77 -> R78 (verified free: word-boundary tree scan zero hits; subject
    # scan zero hits; FULL single-capture queue 69,421ch 115/115 zero
    # R78/R79 citations — the same capture falsified the pass-33/34
    # ~4000ch tower-truncation attribution as observer-side clipping, see
    # docs/reports/QUEUE_TRUNCATION_FALSIFICATION_2026-10-30.md).
    # and after pass 36 (cycle-48, Job 478338) registered the R78 row
    # (landed-class, peer arc — defining WO #2732, fix bd4d262/PR #2733,
    # discovery job J484751: gh-absent dispatch revival via tower board
    # fallback; pass-26 precedent sixth application, post-landing
    # registration reconciling the same landing's D+C ghosts — the first
    # born-and-reconciled-inside-one-dispatch red of the pattern) and
    # advanced it R78 -> R79 (verified free: word-boundary tree hits are
    # mechanism text inside pointer-phrase parentheticals, stripped by the
    # guard's own stripper; subject scan zero hits; FULL single-capture
    # queue 68,341ch 114/114 windowTruncated:false zero hits).
    # and after pass 39 (cycle-52, Job 478338) registered the R79 row
    # (open/in-flight, peer scout arc — defining ticket #2925 "scout(R79):
    # closure verdicts lack a live-state gate", filed 23:32:22Z by
    # ecosystem-scout Job 478520 reading the #2225 second false closure;
    # remedy work order bridge:queued at read time; pass-26 precedent seventh
    # application, registered in-flight (not post-landing) reconciling the
    # C50-witness docs' 5 citation-ghosts same-dispatch) and advanced it
    # R79 -> R80 (verified free: tree word-boundary scan zero; subject scan
    # zero over 200; full queue capture 119/119 windowTruncated:false zero).
    # and after pass 40 (cycle-54, Job 478338) registered the R80 row
    # (open/unclaimed, peer scout arc — defining ticket #3003 "scout(R80):
    # official MCP Registry census >20,000 servers", filed 02:17:19Z citing
    # the advertised pointer in its title ~2h after pass 39; no remedy WO
    # on file at read time — first pure-open registration since R77;
    # pass-26 precedent eighth application, pick-walk-triggered only — the
    # guard was GREEN at 37d69c2, no ghosts/drift) and advanced it
    # R80 -> R81 (verified free: tree word-boundary scan zero; subject scan
    # zero over 200; queue capture 100/100 windowTruncated:false zero).
    # and after #3557's discovery (GLM Agent 18, Job 486801): the pointer
    # advance R81 -> R84 in #3483 skipped this pin — RED on live main across
    # three landings (CI runs no pytest; the pre-push trigger glob was stuck
    # on the day-one SCOUT_RADAR_2026-10-28* names). The same landing adds
    # guard invariant G (pin-truth): the pin-vs-pointer drift class now fails
    # loud at guard time, so this literal can never silently rot again.
    # and after the same-window peer pass 44 (GLM Agent 20, Job 486804 — the
    # #3507/#3516 same-cycle race class witnessed live, reconciled by yield:
    # first registration wins) registered the R84 row post-closure
    # (corroboration record #3554) and advanced the pointer past the landed
    # R85/R86 rows to the next fully-clean number (verified free by BOTH
    # passes: tree word-boundary scan zero; subject scan zero over 200; full
    # queue capture 68/68 windowTruncated:false zero).
    # R87→R89 regeneration (2026-10-31, GLM Agent 14 / Job 486785, standing-suite
    # heal r2): the index legitimately advanced past the landed R88/R89 rows while
    # this literal stayed at 87 — the exact #3624 pointer⇄pin co-obligation class
    # (guard fired report-only, main CI runs no pytest). Regenerated WITH the index
    # per the #3483 rule; scripts/ci/radar_pointer_pin_guard.py now mechanizes the
    # co-obligation for future advances.
    # and after pass 46 (GLM Agent 18, Job 486801, cycle 05:18+08 2026-10-31): this pin co-advances
    # 89 -> 90 in the SAME change that advances the index pointer 89 -> 90 (invariant P2 by
    # construction). Same-window disclosure (the #3507/#3516 race class): this filer caught the
    # pin 87 != pointer 89 drift live at 5e9c0d6 via `radar_pointer_pin_guard.py --check` and
    # recorded it in the R89 report; GLM Agent 14's standing-suite heal r2 (#3821) landed the
    # 87->89 regeneration first — first heal lands wins; this change therefore carries only its
    # OWN co-advance, and Plan-5 (mechanical pre-push wiring of the co-obligation guard, still
    # unwired on main) is recorded in docs/reports/SCOUT_R89_GATEWAY_PROMPT_CACHE_BLINDNESS_2026-10-31.md.
    # and after pass 47 (GLM Agent 21, Job 486808, cycle 05:21+08 2026-10-31): this pin co-advances
    # 90 -> 91 in the SAME change that advances the index pointer 90 -> 91. Same-window disclosure
    # (pass-26 class, fifth recurrence): this filer drafted its lane as R89 with three-plane freeness
    # verified, then caught the peer's issue-side R89 consumption (landing 0d32b24) on a fresh
    # pre-submit queue capture, yielded R89 (first-registration-wins) and re-took the lane as R90 —
    # see index drift log pass 47 + docs/reports/SCOUT_R90_GITHUB_AGENTIC_WORKFLOWS_2026-10-31.md.
    # and after pass 48 (GLM Agent 26, Job 486824, cycle 06:26+08 2026-10-31): this pin co-advances
    # 91 -> 92 in the SAME change that advances the index pointer 91 -> 92 (R91 = gateway
    # retry-storm lockstep lane, live repro inside the defining report) — see index drift log
    # pass 48 + docs/reports/SCOUT_R91_GATEWAY_RETRY_STORM_LOCKSTEP_2026-10-31.md.
    # and after pass 49 (GLM Agent 04, Job 486718, cycle 07:04+08 2026-10-31): this pin co-advances
    # 92 -> 93 in the SAME change that advances the index pointer 92 -> 93 (R92 = tower heartbeat
    # liveness-contract lane, live three-poll timeline inside the defining report) — see index drift
    # log pass 49 + docs/reports/SCOUT_R92_TOWER_HEARTBEAT_LIVENESS_CONTRACT_2026-10-31.md.
    # and after pass 50 (GLM Agent 04, Job 486718, cycle 08:04+08 2026-10-31): this pin co-advances
    # 93 -> 94 in the SAME change that advances the index pointer 93 -> 94 (R93 = #3993/#3994
    # anchor-routing result-None hole lane, offline URL-capture repro inside the defining report)
    # — see index drift log pass 50 + docs/reports/SCOUT_R93_ANCHOR_ROUTING_NONE_HOLE_2026-10-31.md.
    # and after pass 51 (GLM Agent 16, Job 486792, cycle 08:16+08 2026-10-31): this pin co-advances
    # 94 -> 95 in the SAME change that advances the index pointer 94 -> 95 (R94 = credential-free
    # board ground-truth freshness hierarchy lane, 61-open ghost-board vs tower single-fetch
    # spot-check evidence inside the defining report) — see index drift log pass 51 +
    # docs/reports/SCOUT_R94_GROUND_TRUTH_FRESHNESS_2026-10-31.md.
    # and after pass 52 (GLM Agent 09, Job ID 486738, cycle 08:09+08 2026-10-31): this pin co-advances
    # 95 -> 96 in the SAME change that advances the index pointer 95 -> 96 (R95 = October-2026
    # release wave vs the relay plane's three blind spots lane, vendor-official live evidence inside
    # the defining report; collision-yield lane — drafted as R93, yielded to the pass-50 peer's
    # issue-side consumption, re-took R95) — see index drift log pass 52 +
    # docs/reports/SCOUT_R95_OCTOBER_RELEASE_WAVE_RELAY_BLINDSPOTS_2026-10-31.md.
    # and after pass 53 (GLM Agent 04, Job 486718, cycle 09:04+08 2026-10-31): this pin co-advances
    # 96 -> 97 in the SAME change that advances the index pointer 96 -> 97 (R96 = branch-death
    # orphaned-tracking-row lifecycle lane — cleanup_stale_branches × watchdog-mint × register
    # heal-close intersection, 10-row manual bulk-close wave + 5-skip pick-window burn live) —
    # see index drift log pass 53 + docs/reports/SCOUT_R96_BRANCH_DEATH_ROW_LIFECYCLE_2026-10-31.md.
    assert r["pointer"] == 97, "pointer drifted — regenerate expectation with the index"
    baseline = json.loads((REPO_ROOT / BASELINE).read_text(encoding="utf-8"))
    drift, _ = guard.compare(baseline, r["cits"])
    assert not drift, f"live citation-ghost drift: {drift}"


def test_invariant_g_pin_truth_fires_on_drift() -> None:
    """#3557: the pin literal must equal the advertised pointer (drift replays)."""
    live_block = (
        "def test_live_repo_sweep_passes() -> None:\n"
        "    r = guard.sweep(REPO_ROOT)\n"
        '    assert r["pointer"] == 84, "pointer drifted"\n'
        "\n\n"
    )
    # Matching pin: ran, no findings.
    root = make_tree({guard.INDEX_REL: index_doc(84, [1]),
                      "tests/test_radar_index_freshness_guard.py": live_block})
    r = guard.sweep(root)
    assert r["g_ran"] and not r["g"]
    # The #3483 replay: pointer advertised R84, pin left at 81 — must fire
    # naming the exact was/now pair.
    root = make_tree({guard.INDEX_REL: index_doc(84, [1]),
                      "tests/test_radar_index_freshness_guard.py": live_block.replace("== 84", "== 81")})
    r = guard.sweep(root)
    assert any(f["kind"] == "pin-drifted" and f["was"] == 81 and f["now"] == 84 for f in r["g"])
    # Live block missing: the pin contract changed shape — structural fail.
    root = make_tree({guard.INDEX_REL: index_doc(84, [1]),
                      "tests/test_radar_index_freshness_guard.py": "def unrelated_test() -> None:\n    pass\n"})
    r = guard.sweep(root)
    assert any(f["kind"] == "pin-block-missing" for f in r["g"])
    # Pin file deleted while tests/ exists: structural fail (the carrier is gone).
    root = make_tree({guard.INDEX_REL: index_doc(84, [1])})
    (root / "tests").mkdir()
    r = guard.sweep(root)
    assert any(f["kind"] == "pin-file-missing" for f in r["g"])


def test_invariant_g_fixture_tree_honest_skip() -> None:
    """No tests/ directory (fixture tree) — G honest-skips, never fabricates."""
    root = make_tree({guard.INDEX_REL: index_doc(4, [1])})
    r = guard.sweep(root)
    assert not r["g_ran"] and not r["g"]


def test_invariant_e_roster_regressions_fail() -> None:
    """#2392 component 1: pointer revert / row eviction fail closed (ebe630c class)."""
    base2 = {"schema": "radar-index-freshness-baseline/2", "floor": [],
             "roster": {"pointer": 65, "rows": ["R1", "R63", "R64"]}}
    # Pointer regression: the pass-9/22/23 stale-branch overwrite signature.
    findings, ran = guard.invariant_e(64, {"R1", "R63", "R64"}, base2)
    assert ran
    assert any(f["kind"] == "roster-pointer-regressed" and f["was"] == 65 and f["now"] == 64
               for f in findings)
    # Row eviction with the pointer intact — the co-regression blind spot
    # the pin discipline cannot see, now enforced.
    findings, ran = guard.invariant_e(65, {"R1", "R63"}, base2)
    assert ran
    assert any(f["kind"] == "roster-row-evicted" and f["token"] == "R64" for f in findings)


def test_invariant_e_forward_motion_and_v1_skip() -> None:
    """Forward motion (advance + additions) never fails; /1 baselines honest-skip."""
    base2 = {"schema": "radar-index-freshness-baseline/2", "floor": [],
             "roster": {"pointer": 65, "rows": ["R1", "R63", "R64"]}}
    # Fixture token R96: a neutral synthetic successor (pass-4/22 standard,
    # one horizon after pass-25 neutralized its own fixtures) — the suite
    # never embeds the live next-free token in fixture strings, so the next
    # registry pass's tracked-scan for R66 advertisability stays zero-hit
    # here (#2447 Finding 4).
    findings, ran = guard.invariant_e(96, {"R1", "R63", "R64", "R96"}, base2)
    assert ran and findings == []
    findings, ran = guard.invariant_e(None, set(),
                                      {"schema": "radar-index-freshness-baseline/1", "floor": []})
    assert findings == [] and not ran


def test_board_sweep_predicate_offline() -> None:
    """#2392 component 2 / #2372 option B: the captured-title sweep predicate."""
    # Fixture token R97: a neutral synthetic successor — the tracked-tree
    # freeness scan for the REAL advertised successor must stay zero-hit
    # outside pointer context (pass-4/22 standard), so the suite never
    # embeds the live next-free token in fixture strings.
    queue = {"workOrders": [
        {"number": 2401, "title": "scout(R97): a third-party lane citing the candidate"},
        {"number": 2402, "title": "guard(docs): register R60 row + next-free R97 (WO mirror)"},
        {"number": 2403, "title": "unrelated lane with R59 only"},
        {"number": 2392, "title": "scout(R64): the successor lane's own defining ticket"},
    ]}
    # Third-party title citation of the candidate fails, naming the issue.
    fnd = guard.board_sweep(queue, 97, set())
    assert any(f["issue"] == 2401 and f["token"] == "R97" for f in fnd)
    # A WO mirror quoting the allocation rule (pointer phrase) never self-trips.
    assert not any(f["issue"] == 2402 for f in fnd)
    # The self-ref exception (a): the successor lane's own defining ticket.
    assert guard.board_sweep(queue, 97, {2401}) == []
    # Legacy `issueNumber` key accepted (pre-#2286 shape).
    legacy = guard.board_sweep([{"issueNumber": 9, "title": "cites R97 here"}], 97, set())
    assert len(legacy) == 1 and legacy[0]["issue"] == 9


def test_wiring_roster_and_pre_push() -> None:
    roster = (REPO_ROOT / "scripts" / "ci" / "run_all_guards.py").read_text(encoding="utf-8")
    assert "scripts/ci/radar_index_freshness_guard.py" in roster, "guard missing from the live roster"
    hook = (REPO_ROOT / ".githooks" / "pre-push").read_text(encoding="utf-8")
    assert "RADAR INDEX FRESHNESS GUARD (#2091)" in hook, "guard missing from the live pre-push hook"
    assert guard.GUARD_TAG in hook, "hook must invoke the guard's evidence tag"


# --------------------------------------------------------------------------- #
# #2180 — baseline provenance is live, never a frozen literal                  #
# --------------------------------------------------------------------------- #

def test_build_baseline_provenance_is_live() -> None:
    data = guard.build_baseline(REPO_ROOT)
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO_ROOT),
                          capture_output=True, text=True)
    if head.returncode == 0:
        assert data["headAtGeneration"].startswith(head.stdout.strip()), (
            "headAtGeneration must pin the actual HEAD at generation time (#2180)")
    else:
        assert data["headAtGeneration"] == "unknown (git unavailable at generation)"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["generatedAt"]), (
        "generatedAt must be a live UTC date (#2180)")
    text = (REPO_ROOT / guard.INDEX_REL).read_text(encoding="utf-8")
    _tokens, bases = guard.parse_registry(text)
    expect = f"R{min(bases)}-R{max(bases)}" if bases else "unknown (empty registry at generation)"
    assert data["registryRowsAtGeneration"] == expect, (
        "registryRowsAtGeneration must derive from the live registry (#2180)")


def test_git_provenance_fallback_hermetic() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="rifg-nogit-"))
    assert guard._git_head_provenance(tmp) == "unknown (git unavailable at generation)"



# --------------------------------------------------------------------------- #
# #2187 — invariant D: commit-plane ghost scan (offline, first-run-clean)      #
# --------------------------------------------------------------------------- #

def test_hyphenated_pointer_form_is_stripped() -> None:
    # Finding 3: "next-free R53" (real landed subjects #2172/#2178) used to
    # escape the stripper; the widened `next[-\s]free` gap cleans it, while a
    # non-pointer R53 mention still ghosts.
    assert guard.scan_subjects(
        ["guard(docs): register R52 row + next-free R53 (#2172)"], {52}) == []
    assert guard.scan_subjects(
        ["pass 11 — moves next free to **R53** (verified free repo-wide)"], set()) == []
    ghosts = guard.scan_subjects(["radar R53 filed from the advertised slot"], set())
    assert any(f["base"] == 53 and f["kind"] == "commit-subject-ghost" for f in ghosts)


def test_real_subject_corpus_resolves_floor_born_empty() -> None:
    corpus = [
        "guard(docs): R51 registration per #2137 (#2145)",
        "feat(docs): scout(R52 option A) — register the lane (#2165)",
        "guard(docs): register R52 row + next-free R53 (#2172)",
        "fix(ci): #2180 - baseline provenance were frozen literals (#2184)",
        "a10: receipt eleven (run 5077) - standing trip-wire repeat fire",
    ]
    assert guard.scan_subjects(corpus, set(range(1, 53))) == []


def test_commit_subject_ghost_named() -> None:
    ghosts = guard.scan_subjects(["feat: unregistered R97 lane landing"], {1})
    assert len(ghosts) == 1
    assert ghosts[0]["base"] == 97 and ghosts[0]["token"] == "R97"
    assert guard.key_of(ghosts[0]) == ("commit-subject-ghost", 97,
                                       "feat: unregistered R97 lane landing")


def test_invariant_d_end_to_end_on_throwaway_git_history() -> None:
    if not shutil.which("git"):
        return  # honest-skip mirrors the guard's own git-less doctrine
    root = make_tree({guard.INDEX_REL: index_doc(53, [1, 52])})

    def git(*a: str) -> None:
        subprocess.run(["git", *a], cwd=str(root), capture_output=True, text=True, check=False)

    git("init", "-q")
    git("config", "user.email", "hermetic@example")
    git("config", "user.name", "hermetic")
    (root / "seed.txt").write_text("one\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "guard(docs): register R52 row + next-free R53 (#2172)")
    (root / "seed.txt").write_text("two\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "feat: unregistered R97 lane landing")
    ghosts, ran = guard.invariant_d(root, {1, 52})
    assert ran
    assert any(f["base"] == 97 for f in ghosts)
    assert not any(f["base"] == 53 for f in ghosts)  # hyphenated pointer stays clean


def test_invariant_d_honest_skip_without_git() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="rifg-nogit-"))
    ghosts, ran = guard.invariant_d(tmp, {1})
    # In a git-less dir the subprocess fails -> honest-skip, never a fake PASS.
    if ran:  # sandbox has git but the dir is not a repo — skip is still honest
        assert ghosts == [] or all(f["base"] not in {1} for f in ghosts)
    else:
        assert ghosts == []


def test_invariant_d_joins_ratchet_as_fresh_drift() -> None:
    ghosts = [guard_scan := {"kind": "commit-subject-ghost", "subject": "feat: R97 lane",
                             "token": "R97", "base": 97}]
    baseline = {"schema": "radar-index-freshness-baseline/1", "floor": []}
    drift, _ = guard.compare(baseline, ghosts)
    assert len(drift) == 1 and drift[0]["kind"] == "new"
    # Registering the row makes the base resolve — the finding vanishes and
    # the floor entry (never written) stays unborn: first-run-clean holds.
    assert guard.scan_subjects(["feat: R97 lane"], {97}) == []


def test_sweep_carries_commit_plane_fields() -> None:
    root = make_tree({guard.INDEX_REL: index_doc(4, [1])})
    r = guard.sweep(root)
    assert "d" in r and "d_ran" in r
    assert isinstance(r["d"], list)


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
