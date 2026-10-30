"""U6 wiring: the tower read-file artifact classifier under standing pytest.

scripts/ci/tower_read_file_artifact_probe.py (#3467) ships an 8-case
``--self-test`` but no standing suite invoked it — a classifier regression
would not trip any CI. This module wires the hermetic half of the probe
(classifier, suspect-stripper model, mojibake undo, blob-sha helper) into
pytest so the evidence verdict contract (PASS / ARTIFACT_MATCH /
ARTIFACT_OTHER / ENCODING_UNSAFE) is enforced on every run.

The live half (``run_live``) is intentionally NOT covered here: it dials the
tower over the network and must stay out of the hermetic suite; its exit
contract (0/1 evidence vs 3 wiring) is exercised by the probe's own CLI.

Refs #3467 (probe + live evidence), #3466 (work order).
"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from scripts.ci.tower_read_file_artifact_probe import (
    SUSPECT,
    classify,
    git_blob_sha,
    run_self_test,
    simulate_strip,
    unmojibake,
)

EVIDENCE_VERDICTS = {"PASS", "ARTIFACT_MATCH", "ARTIFACT_OTHER", "ENCODING_UNSAFE"}


class TowerReadArtifactClassifierTest(unittest.TestCase):
    """The classifier is the evidence plane: every verdict below is a
    regression guard against silent misclassification of tower reads."""

    # --- the canonical 8-case self-test must stay green under pytest ---
    def test_self_test_suite_green(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(run_self_test(), 0, buf.getvalue())

    # --- verdict contract, one case per documented outcome ---
    def test_pass_on_faithful_payload(self) -> None:
        verdict, detail = classify("branches: [main]\n", "branches: [main]\n")
        self.assertEqual(verdict, "PASS")
        self.assertIn("faithful", detail)

    def test_pass_after_mojibake_roundtrip(self) -> None:
        # tower's UTF-8->latin-1 double-decode drift must be undone, not
        # reported as divergence (live 2026-10-30: drift present in ALL reads)
        verdict, _ = classify("dash — here", "dash â\x80\x94 here")
        self.assertEqual(verdict, "PASS")

    def test_artifact_match_names_the_stripped_span(self) -> None:
        # live capture shape: "[main]" reads back as "ain]" (leading "[m" eaten)
        verdict, detail = classify("go: branches: [main]\n", "go: branches: ain]\n")
        self.assertEqual(verdict, "ARTIFACT_MATCH")
        self.assertIn("[m", detail)  # the stripped span is named, never guessed

    def test_artifact_match_on_sgr_color_codes(self) -> None:
        verdict, _ = classify("c=[0;32m and [1;33m and [42m", "c= and  and ")
        self.assertEqual(verdict, "ARTIFACT_MATCH")

    def test_artifact_other_on_unexplained_delta(self) -> None:
        verdict, _ = classify("alpha [main] beta", "alpha [main] GAMMA")
        self.assertEqual(verdict, "ARTIFACT_OTHER")

    def test_encoding_unsafe_on_non_roundtrippable_payload(self) -> None:
        # latin-1 encodable but not utf-8 decodable -> compare is inconclusive
        verdict, _ = classify("ok\n", "caf\u00e9")
        self.assertEqual(verdict, "ENCODING_UNSAFE")

    def test_verdicts_stay_in_the_documented_envelope(self) -> None:
        pairs = [
            ("a", "a"),                      # PASS
            ("[main]", "ain]"),              # ARTIFACT_MATCH
            ("x — y", "x Ã¢ y"),             # mojibake-adjacent ARTIFACT_OTHER
            ("", "zzz"),                     # degenerate inputs
        ]
        for local, tower in pairs:
            verdict, _ = classify(local, tower)
            self.assertIn(verdict, EVIDENCE_VERDICTS, (local, tower, verdict))

    # --- helper contracts the classifier leans on ---
    def test_simulate_strip_hits_only_the_suspect_class(self) -> None:
        text = "[main] [pousr] [ -f x ] [A-Za-z0-9]"
        stripped = simulate_strip(text)
        self.assertLess(len(stripped), len(text))  # never widens
        self.assertEqual(stripped, "ain] [pousr] [ -f x ] [A-Za-z0-9]")

    def test_unmojibake_returns_none_when_not_roundtrippable(self) -> None:
        self.assertIsNone(unmojibake("\u00e9\u00e9"))  # latin-1 bytes, invalid utf-8

    def test_blob_sha_known_git_vector(self) -> None:
        # canonical git vector: printf 'hello\n' | git hash-object --stdin
        self.assertEqual(
            git_blob_sha(b"hello\n"), "ce013625030ba8dba906f756967f9e9ca394464a"
        )

    def test_suspect_class_matches_only_the_documented_shape(self) -> None:
        # evidence-fitted: [digits/semicolons]*m, no ESC byte required
        for span in ("[m", "[42m", "[0;1;33m", "branches: [main]"):
            self.assertTrue(SUSPECT.search(span), span)
        for safe in ("[pousr]", "[ -f x ]", "[A-Za-z0-9]"):
            self.assertFalse(SUSPECT.search(safe), safe)


if __name__ == "__main__":
    unittest.main()
