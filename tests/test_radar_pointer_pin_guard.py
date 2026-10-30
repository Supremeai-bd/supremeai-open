#!/usr/bin/env python3
"""tests/test_radar_pointer_pin_guard.py — parity companion for the pointer⇄pin co-obligation guard.

The test-parity guard (tests/test_test_parity_guard.py) fails closed when any
scripts/ci/*.py guard lacks its tests/test_<name>.py companion — and PR
#3720 (radar_pointer_pin_guard.py, the mechanical co-obligation half of
#3718) landed WITHOUT this file, standing red on main. This suite discharges
that co-obligation for the co-obligation guard itself and pins its behavior:

  - hermetic matrix: the guard's own self_test() invariant matrix is fully
    green (every verdict branch reachable offline);
  - parser semantics (inherited fleet-parity): parse_pointer takes the FIRST
    'next free … R<n>' match (allocation-rule header beats drift-log
    narration); parse_pin extracts the frozen literal only from
    test_live_repo_sweep_passes' body — other functions' assertions are out
    of scope;
  - invariant P verdicts (pure check_tree): CONSISTENT / PIN_DRIFT /
    INDEX_UNREADABLE / PIN_UNREADABLE;
  - invariant P2 verdicts (check_ref): CO_ADVANCED / POINTER_WITHOUT_PIN /
    PIN_MISSING_ON_REF / honest-skip unreadable planes / no-advance
    fallback to plain consistency;
  - CLI contract: --self-test exits 0 green; a mode flag is required;
    --check is report-only (exit 0 even on PIN_DRIFT — strict is opt-in);
  - live-tree truthfulness: on the REAL repo files the parsers agree with
    what check_tree reports, and the verdict is one of the two truthful
    states (CONSISTENT or PIN_DRIFT). Policy consistency itself is already
    enforced by test_live_repo_sweep_passes' frozen pin — asserting it here
    too would double-enforce and flap on every legitimate advance, so this
    suite asserts the guard's TRUTH, not the tree's policy state;
  - wiring SSOT: the guard's --self-test is present in the LIVE
    scripts/ci/run_all_guards.py roster (mirrors the sibling freshness
    suite's wiring check).

Design (zero-dependency doctrine, dual mode — pytest + stdlib runners):
  - pytest:  pytest tests/test_radar_pointer_pin_guard.py
  - stdlib:  python3 tests/test_radar_pointer_pin_guard.py
All scenarios are hermetic (string fixtures, no git/network) except the two
live-tree tests, which read repo files read-only.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "ci"))

import radar_pointer_pin_guard as rppg  # noqa: E402

IDX = rppg.INDEX_PATH
TST = rppg.PIN_TEST_PATH


def idx(n: int) -> str:
    return f"intro\n> allocation … (next free: **R{n}**), update in same PR\nfooter\n"


def tst(n: int) -> str:
    return (
        'def test_other():\n    assert r["pointer"] == 51\n\n'
        f"def {rppg.PIN_TEST_FN}():\n"
        f'    assert r["pointer"] == {n}, "pointer drifted"\n'
    )


class TestHermeticMatrix(unittest.TestCase):
    def test_self_test_matrix_green(self):
        cases = rppg.self_test()
        self.assertTrue(cases, "self_test returned no cases")
        failed = [name for name, ok, _ev in cases if not ok]
        self.assertEqual(failed, [], f"self-test cases failing: {failed}")

    def test_cli_self_test_exit_zero(self):
        self.assertEqual(rppg.main(["--self-test"]), 0)

    def test_cli_requires_mode(self):
        with self.assertRaises(SystemExit):
            rppg.main([])


class TestParserSemantics(unittest.TestCase):
    def test_pointer_first_match_header_wins(self):
        text = "a (next free: **R90**) b (moves next free to R91) c"
        self.assertEqual(rppg.parse_pointer(text), 90)

    def test_pointer_absent_is_none(self):
        self.assertIsNone(rppg.parse_pointer("no pointer here"))

    def test_pin_function_scoped(self):
        # other functions' assertions never win; the live-sweep fn's first
        # assertion is the pin
        self.assertEqual(rppg.parse_pin(tst(87)), 87)

    def test_pin_missing_fn_is_none(self):
        self.assertIsNone(rppg.parse_pin("def other(): pass"))

    def test_pin_fn_without_assertion_is_none(self):
        self.assertIsNone(rppg.parse_pin(f"def {rppg.PIN_TEST_FN}():\n    assert 1 + 1 == 2\n"))


class TestInvariantPCheckTree(unittest.TestCase):
    def test_consistent(self):
        v = rppg.check_tree(idx(87), tst(87))
        self.assertEqual(v["verdict"], "CONSISTENT")
        self.assertEqual(v["pointer"], 87)
        self.assertEqual(v["pin"], 87)

    def test_drift_flags(self):
        v = rppg.check_tree(idx(88), tst(87))
        self.assertEqual(v["verdict"], "PIN_DRIFT")
        self.assertIn("regenerate the pin", v["evidence"])

    def test_index_unreadable_is_honest(self):
        v = rppg.check_tree("no pointer here", tst(87))
        self.assertEqual(v["verdict"], "INDEX_UNREADABLE")

    def test_pin_unreadable_is_honest(self):
        v = rppg.check_tree(idx(87), "def other(): pass")
        self.assertEqual(v["verdict"], "PIN_UNREADABLE")


class TestInvariantP2CheckRef(unittest.TestCase):
    def test_co_advanced_passes(self):
        v = rppg.check_ref(idx(87), idx(88), tst(88))
        self.assertEqual(v["verdict"], "CO_ADVANCED")

    def test_pointer_without_pin_flags(self):
        v = rppg.check_ref(idx(87), idx(88), tst(87))
        self.assertEqual(v["verdict"], "POINTER_WITHOUT_PIN")
        self.assertIn("landing reds", v["evidence"])

    def test_pin_missing_on_ref(self):
        v = rppg.check_ref(idx(87), idx(88), "def other(): pass")
        self.assertEqual(v["verdict"], "PIN_MISSING_ON_REF")

    def test_no_advance_falls_back_to_consistency(self):
        v = rppg.check_ref(idx(87), idx(87), tst(87))
        self.assertEqual(v["verdict"], "CONSISTENT")

    def test_unreadable_planes_are_honest(self):
        self.assertEqual(rppg.check_ref("garbage", idx(88), tst(88))["verdict"], "BASE_UNREADABLE")
        self.assertEqual(rppg.check_ref(idx(87), "garbage", tst(87))["verdict"], "INDEX_UNREADABLE")


class TestCliReportOnlyContract(unittest.TestCase):
    def test_check_is_report_only_even_on_drift(self):
        # --check must NEVER fail the tree plane by default: exit 0 in both
        # truthful states (strict is the explicit opt-in).
        v = rppg.check_tree((_ROOT / IDX).read_text(encoding="utf-8"),
                            (_ROOT / TST).read_text(encoding="utf-8"))
        self.assertIn(v["verdict"], ("CONSISTENT", "PIN_DRIFT"),
                      f"live tree verdict not truthful: {v}")
        self.assertEqual(rppg.main(["--check"]), 0)


class TestLiveTreeTruthfulness(unittest.TestCase):
    """Read-only wiring/truth check on the REAL repo files.

    Deliberately does NOT assert CONSISTENT: the policy (pin == advertised
    pointer) is enforced by test_live_repo_sweep_passes' frozen literal.
    Here we assert the guard's parsers describe the real tree faithfully —
    stable under legitimate pointer advances.
    """

    def test_parsers_agree_with_real_tree(self):
        index_text = (_ROOT / IDX).read_text(encoding="utf-8")
        test_text = (_ROOT / TST).read_text(encoding="utf-8")
        pointer = rppg.parse_pointer(index_text)
        pin = rppg.parse_pin(test_text)
        self.assertIsInstance(pointer, int, "live index pointer unparseable")
        self.assertIsInstance(pin, int, "live pin literal unparseable")
        v = rppg.check_tree(index_text, test_text)
        self.assertIn(v["verdict"], ("CONSISTENT", "PIN_DRIFT"))
        if v["verdict"] == "PIN_DRIFT":
            # evidence must name BOTH real numbers — no fabrication
            self.assertIn(str(pin), v["evidence"])
            self.assertIn(str(pointer), v["evidence"])

    def test_guard_wired_in_live_roster(self):
        roster = (_ROOT / "scripts" / "ci" / "run_all_guards.py").read_text(encoding="utf-8")
        self.assertIn("radar_pointer_pin_guard.py", roster,
                      "guard dropped from the live run_all_guards roster — re-wire it")


if __name__ == "__main__":
    unittest.main(verbosity=2)
