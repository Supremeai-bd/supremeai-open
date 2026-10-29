#!/usr/bin/env python3
"""Tests for skill_conformance_guard.py (issue #1672).

Dual-mode: runs under pytest AND as a plain stdlib unittest-style script
(python tests/test_skill_conformance_guard.py). Every test is hermetic —
skill trees are built in tempfile dirs, never the live `.agents/skills/`.

The globals()-patch pattern pins the __main__ pitfall from the #2059 lesson:
helpers are reached via the module object so both invocation modes exercise
the same code paths.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

import skill_conformance_guard as G  # noqa: E402


def make_skill(root: Path, name: str, frontmatter: str, body: str = "instructions\n") -> Path:
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(frontmatter + body, encoding="utf-8")
    return d


class ParseTests(unittest.TestCase):
    def test_plain_scalars(self):
        s, notes, err = G.parse_frontmatter(["---", "name: a", "description: b", "---", "body"])
        self.assertIsNone(err)
        self.assertEqual(s, {"name": "a", "description": "b"})
        self.assertEqual(notes, [])

    def test_quoted_scalars(self):
        s, _, err = G.parse_frontmatter(
            ["---", 'name: "q"', "description: 'single'", "---"])
        self.assertIsNone(err)
        self.assertEqual(s["name"], "q")
        self.assertEqual(s["description"], "single")

    def test_continuation_folding(self):
        s, _, err = G.parse_frontmatter(
            ["---", "name: folded", "description: first", "  second", "  third", "---"])
        self.assertIsNone(err)
        self.assertEqual(s["description"], "first second third")

    def test_nested_map_reported_and_skipped(self):
        s, notes, err = G.parse_frontmatter(
            ["---", "name: n", "description: d", "metadata:", "  version: \"1.0.0\"", "---"])
        self.assertIsNone(err)
        self.assertEqual(s["name"], "n")
        self.assertTrue(any("nested map under 'metadata'" in x for x in notes))

    def test_missing_delimiters(self):
        _, _, err = G.parse_frontmatter(["name: x"])
        self.assertIsNotNone(err)
        self.assertTrue(err.startswith("E2"))
        _, _, err2 = G.parse_frontmatter(["---", "name: x"])
        self.assertIsNotNone(err2)


class CheckTests(unittest.TestCase):
    def test_clean_skill_zero_errors(self):
        with tempfile.TemporaryDirectory() as td:
            d = make_skill(Path(td), "clean", "---\nname: clean\ndescription: ok\n---\n")
            errs, warns = G.check_skill_file(d)
            self.assertEqual(errs, [])

    def test_e4_name_directory_drift(self):
        with tempfile.TemporaryDirectory() as td:
            d = make_skill(Path(td), "real", "---\nname: phantom\ndescription: x\n---\n")
            errs, _ = G.check_skill_file(d)
            self.assertTrue(errs[0].startswith("E4"))

    def test_e3_missing_name(self):
        with tempfile.TemporaryDirectory() as td:
            d = make_skill(Path(td), "s", "---\ndescription: x\n---\n")
            errs, _ = G.check_skill_file(d)
            self.assertTrue(errs[0].startswith("E3"))

    def test_e5_missing_description(self):
        with tempfile.TemporaryDirectory() as td:
            d = make_skill(Path(td), "s", "---\nname: s\n---\n")
            errs, _ = G.check_skill_file(d)
            self.assertTrue(errs[0].startswith("E5"))

    def test_e6_over_cap(self):
        with tempfile.TemporaryDirectory() as td:
            d = make_skill(Path(td), "s", "---\nname: s\ndescription: " + "x" * 1025 + "\n---\n")
            errs, _ = G.check_skill_file(d)
            self.assertTrue(errs[0].startswith("E6"))

    def test_w1_w2_w3_inventory(self):
        with tempfile.TemporaryDirectory() as td:
            d = make_skill(Path(td), "s",
                           "---\nname: s\ndescription: d\nrisk: safe\n"
                           "metadata:\n  version: \"1.0.0\"\n---\n")
            errs, warns = G.check_skill_file(d)
            self.assertEqual(errs, [])
            self.assertTrue(any(w.startswith("W1") and "risk" in w for w in warns))
            self.assertTrue(any(w.startswith("W2") for w in warns))
            self.assertTrue(any(w.startswith("W3") for w in warns))


class ScanAndRatchetTests(unittest.TestCase):
    def test_e1_missing_skill_md(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "ghost").mkdir()
            err_rows, warn_rows, skips = G.scan(Path(td))
            self.assertEqual([n for n, _ in err_rows], ["ghost"])
            self.assertTrue(err_rows[0][1][0].startswith("E1"))

    def test_absent_surface_honest_skip(self):
        with tempfile.TemporaryDirectory() as td:
            err_rows, _, skips = G.scan(Path(td) / "nope")
            self.assertEqual(err_rows, [])
            self.assertTrue(any("surface absent" in s for s in skips))

    def test_ratchet_new_violation_fails_closed(self):
        violations, _ = G.ratchet([("new", ["E4: drift"])], {})
        self.assertTrue(any("NEW error" in v for v in violations))

    def test_ratchet_grown_codes_fail(self):
        violations, _ = G.ratchet([("p", ["E4: x", "E6: y"])], {"p": ["E4"]})
        self.assertTrue(any("GROWN" in v for v in violations))

    def test_ratchet_resolved_pin_shrinks(self):
        violations, notes = G.ratchet([], {"old": ["E1"]})
        self.assertEqual(violations, [])
        self.assertTrue(any("old" in n for n in notes))

    def test_ratchet_subset_passes(self):
        violations, _ = G.ratchet([("p", ["E1: missing"])], {"p": ["E1"]})
        self.assertEqual(violations, [])


class LiveSurfaceTests(unittest.TestCase):
    """The live repo surface must stay within the seeded floor (the #2081 lesson)."""

    def test_live_scan_within_baseline(self):
        baseline = G.load_baseline(G.DEFAULT_BASELINE)
        err_rows, _, skips = G.scan(G.DEFAULT_ROOT)
        violations, _ = G.ratchet(err_rows, baseline)
        self.assertEqual(violations, [], f"live surface grew new structural errors: {violations}")

    def test_self_test_battery(self):
        self.assertEqual(G.self_test(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
