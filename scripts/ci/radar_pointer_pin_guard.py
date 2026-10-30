#!/usr/bin/env python3
"""radar_pointer_pin_guard.py — pointer-advance ⇄ test-pin co-obligation guard.

The measured instance (2026-10-31, GLM Agent 17 cycle): registration PR
#3624 (WO #3623) advances the radar index's advertised pointer R87→R88 as a
docs-only 3-file diff, and its own 3-tier smoke verified freeness/uniqueness/
row-shape — but the frozen live pin in tests/test_radar_index_freshness_guard.py
(`assert r["pointer"] == 87`, mechanized by #3483) was not bumped in the same
PR. Branch-tree reproduction: the moment the PR lands, the standing suite's
`test_live_repo_sweep_passes` flips from the current citation-ghost red to
`AssertionError: pointer drifted — assert 88 == 87`. PR CI cannot catch this
(test-matrix runs no pytest — the #3665 invisibility class), and main CI runs
no pytest either, so the co-regression would persist until a later agent
cycle regenerates the pin.

The drift log's rule ("Bump this literal ONLY together with a landed
index-pointer advance") is one-directional prose: it tells pin-bumpers what
to do but nothing in the registration path tells pointer-advancers to bump
the pin. This guard codifies the co-obligation mechanically:

  invariant P (tree consistency):   in any tree, the live pin literal equals
                                    the index's advertised next-free number.
  invariant P2 (pre-landing ref):   a ref whose index diff advances the
                                    pointer MUST carry the matching pin
                                    advance in the same ref.

Modes:
  --self-test            hermetic proof of the parsers + both invariants
  --check                invariant P on the current working tree (report-only
                         unless --strict; live cadence lane, not roster)
  --check-ref REF        invariant P2 for a registration PR ref
                         (--base defaults to origin/main; needs git)
Exit codes: 0 pass · 1 findings (or --strict findings) · 2 honest-skip
(unreadable planes).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = "docs/SCOUT_RADAR_INDEX.md"
PIN_TEST_PATH = "tests/test_radar_index_freshness_guard.py"
PIN_TEST_FN = "test_live_repo_sweep_passes"

# The advertised pointer — byte-parity with the fleet guard's own rule
# (radar_index_freshness_guard.py POINTER_RE, verified corpus at aa9de7b:
# "next free: **R51**" / "next free = R37" / "next free to R39"), and the
# same FIRST-match semantics: the allocation-rule header (top of file) is
# the live advertisement; later drift-log "moves next free to R<n>" phrases
# are historical narration and must never win ("the index is the only
# counter" — first advertisement is the counter).
POINTER_RE = re.compile(r"next\s+free[^R\n]{0,14}?R(\d{1,3})\b")
# The live sweep's frozen pin: `assert r["pointer"] == 87, "pointer drifted…"`
PIN_RE = re.compile(r'assert r\["pointer"\]\s*==\s*(\d+)')


def parse_pointer(index_text: str) -> int | None:
    """Advertised next-free R-number — FIRST match, fleet-guard parity
    (radar_index_freshness_guard.parse_pointer): the allocation-rule header
    precedes the historical drift-log narration, so first match is current."""
    m = POINTER_RE.search(index_text)
    return int(m.group(1)) if m else None


def parse_pin(test_text: str) -> int | None:
    """Frozen live pin from test_live_repo_sweep_passes' body (None = absent)."""
    m = re.search(rf"def {PIN_TEST_FN}\(.*?(?=\ndef |\Z)", test_text, re.S)
    if not m:
        return None
    hits = PIN_RE.findall(m.group(0))
    return int(hits[0]) if hits else None


def check_tree(index_text: str, test_text: str) -> dict:
    """Invariant P on file contents (pure; self-test covers every branch)."""
    pointer = parse_pointer(index_text)
    pin = parse_pin(test_text)
    out: dict = {"pointer": pointer, "pin": pin}
    if pointer is None:
        out["verdict"] = "INDEX_UNREADABLE"
        out["evidence"] = "no advertised pointer found (no 'next free … R<n>' phrase)"
        return out
    if pin is None:
        out["verdict"] = "PIN_UNREADABLE"
        out["evidence"] = f"no frozen pin assertion in {PIN_TEST_FN}"
        return out
    if pointer == pin:
        out["verdict"] = "CONSISTENT"
        out["evidence"] = f"pin R{pin} == advertised next-free R{pointer}"
    else:
        out["verdict"] = "PIN_DRIFT"
        out["evidence"] = (f"pin {pin} != advertised next-free {pointer} — "
                           f"regenerate the pin with the index (the #3483 literal)")
    return out


def check_ref(index_base: str, index_ref: str, test_ref: str) -> dict:
    """Invariant P2 on contents read from two trees (base vs registration ref)."""
    pointer_old = parse_pointer(index_base)
    pointer_new = parse_pointer(index_ref)
    pin_new = parse_pin(test_ref)
    if pointer_new is None:
        return {"verdict": "INDEX_UNREADABLE", "evidence": "ref index pointer unparseable"}
    if pointer_old is None:
        return {"verdict": "BASE_UNREADABLE", "evidence": "base index pointer unparseable"}
    if pointer_new == pointer_old:
        return check_tree(index_ref, test_ref)  # no advance → plain consistency
    if pin_new is None:
        return {"verdict": "PIN_MISSING_ON_REF",
                "evidence": f"pointer advances {pointer_old}→{pointer_new} but ref carries no pin"}
    if pin_new == pointer_new:
        return {"verdict": "CO_ADVANCED",
                "evidence": f"pointer {pointer_old}→{pointer_new} and pin bumped to {pin_new} — co-obligation met"}
    return {"verdict": "POINTER_WITHOUT_PIN",
            "evidence": (f"pointer advances {pointer_old}→{pointer_new} but ref pin stays {pin_new} — "
                         f"landing reds test_live_repo_sweep_passes (pointer-drift class)")}


def _git_show(ref: str, path: str) -> str:
    r = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=REPO_ROOT,
                       capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"git show {ref}:{path} failed: {r.stderr.strip()[:120]}")
    return r.stdout


def self_test() -> list[tuple[str, bool, str]]:
    """Hermetic invariant matrix: every verdict reachable, zero git/network."""
    idx = lambda n: f"intro\n> allocation … (next free: **R{n}**), update in same PR\nfooter\n"
    tst = lambda n: (f"def test_other():\n    assert r[\"pointer\"] == 51\n\n"
                     f"def {PIN_TEST_FN}():\n"
                     f"    assert r[\"pointer\"] == {n}, \"pointer drifted\"\n")
    cases: list[tuple[str, bool, str]] = []

    v = check_tree(idx(87), tst(87))
    cases.append(("P: consistent tree passes", v["verdict"] == "CONSISTENT", str(v)))

    v = check_tree(idx(88), tst(87))
    cases.append(("P: drift flags (the #3624 post-landing state)", v["verdict"] == "PIN_DRIFT", str(v)))

    v = check_tree("no pointer here", tst(87))
    cases.append(("P: unreadable index is honest", v["verdict"] == "INDEX_UNREADABLE", str(v)))

    v = check_tree(idx(87), "def other(): pass")
    cases.append(("P: missing pin function is honest", v["verdict"] == "PIN_UNREADABLE", str(v)))

    v = check_tree(idx(87), idx(87))  # wrong file content → pin missing
    cases.append(("P: pin parser bound to the test fn", v["verdict"] == "PIN_UNREADABLE", str(v)))

    v = check_tree("a (next free: **R90**) b (moves next free to R91) c", tst(90))
    cases.append(("P: first-match parity — header advertisement wins over drift log", v["verdict"] == "CONSISTENT" and v["pointer"] == 90, str(v)))

    v = check_ref(idx(87), idx(88), tst(88))
    cases.append(("P2: co-advanced ref passes", v["verdict"] == "CO_ADVANCED", str(v)))

    v = check_ref(idx(87), idx(88), tst(87))
    cases.append(("P2: pointer-without-pin flags (the #3624 shape)", v["verdict"] == "POINTER_WITHOUT_PIN", str(v)))

    v = check_ref(idx(87), idx(87), tst(87))
    cases.append(("P2: no advance falls back to consistency", v["verdict"] == "CONSISTENT", str(v)))

    v = parse_pin(f"def {PIN_TEST_FN}():\n    assert 1 + 1 == 2\n")
    cases.append(("pin parser: fn without assertion is None", v is None, str(v)))

    return cases


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Radar pointer⇄pin co-obligation guard (#3624 class)")
    p.add_argument("--self-test", action="store_true",
                   help="hermetic invariant matrix (roster mode)")
    p.add_argument("--check", action="store_true",
                   help="invariant P on the working tree (report-only unless --strict)")
    p.add_argument("--check-ref", metavar="REF",
                   help="invariant P2 for a registration-PR ref (needs git)")
    p.add_argument("--base", default="origin/main",
                   help="base ref for --check-ref (default origin/main)")
    p.add_argument("--strict", action="store_true",
                   help="exit 1 on findings (report-only default)")
    args = p.parse_args(argv)

    if args.self_test:
        cases = self_test()
        failed = [c for c in cases if not c[1]]
        for name, ok, ev in cases:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {ev}" if not ok else ""))
        print(f"\n==== {len(cases) - len(failed)}/{len(cases)} self-test cases PASS ====")
        return 1 if failed else 0

    try:
        if args.check_ref:
            res = check_ref(_git_show(args.base, INDEX_PATH),
                            _git_show(args.check_ref, INDEX_PATH),
                            _git_show(args.check_ref, PIN_TEST_PATH))
            print(f"REF PLANE: {args.check_ref} vs base {args.base}")
        elif args.check:
            idx = (REPO_ROOT / INDEX_PATH).read_text(encoding="utf-8")
            tst = (REPO_ROOT / PIN_TEST_PATH).read_text(encoding="utf-8")
            res = check_tree(idx, tst)
            print("TREE PLANE: working tree")
        else:
            p.error("one of --self-test / --check / --check-ref is required")
    except RuntimeError as e:
        print(f"SKIP: plane unreachable ({e})")
        return 2

    print(f"  [{res['verdict']}] {res['evidence']}")
    if res["verdict"] in ("PIN_DRIFT", "POINTER_WITHOUT_PIN") and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
