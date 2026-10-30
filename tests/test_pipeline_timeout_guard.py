#!/usr/bin/env python3
"""tests/test_pipeline_timeout_guard.py — born-with-guard battery for #3386 option B.

# বাংলা নোট: R82 স্কাউট ফাইন্ডিং (pipeline.yml-এ ৪টি job-এ timeout-minutes
# অনুপস্থিত, ডিফল্ট ৩৬০-মিনিট সিলিং খোলা) হেল করতে scripts/ci/
# pipeline_timeout_guard.py গার্ডটি জন্ম নিয়েছে। এই ব্যাটারি গার্ডের চুক্তি
# লক করে রাখে: বেসলাইন মোডে পরিচিত গ্যাপ নন-ফেটাল কিন্তু প্রকাশিত, বেসলাইনের
# বাইরে নতুন পিনহীন জব = ভায়োলেশন (U6 — একবার আবিষ্কৃত ভুল আর ফিরে আসবে না),
# --strict = শূন্য-অবস্থা প্রয়োগ (admin পিন বসালেই), এবং যেকোনো অপাঠযোগ্য
# সারফেস fail-closed (কখনো মিথ্যা সবুজ নয়, #1760)।

Run:
  pytest tests/test_pipeline_timeout_guard.py          # CI (test-matrix)
  python3 tests/test_pipeline_timeout_guard.py         # stdlib dual-mode

Refs: #3386 (R82 receipt + option B prescription) · #3352 (sequencing-honesty
flip precedent) · #1814 (exit-code family) · #1760 (honest-skip).
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

import pipeline_timeout_guard as guard

CLEAN_YAML = """\
name: clean
jobs:
  a:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps: [{run: 'true'}]
  b:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps: [{run: 'true'}]
"""

R82_SHAPE_YAML = """\
name: r82
jobs:
  test-matrix:
    runs-on: ubuntu-latest
    strategy: {fail-fast: false}
    steps: [{run: 'true'}]
  secrets-scan:
    runs-on: ubuntu-latest
    steps: [{run: 'true'}]
  mcp-tower:
    runs-on: ubuntu-latest
    steps: [{run: 'true'}]
  sdk-typescript:
    runs-on: ubuntu-latest
    steps: [{run: 'true'}]
  guard-job:
    runs-on: ubuntu-latest
    timeout-minutes: 3
    steps: [{run: 'true'}]
"""

GROWTH_YAML = """\
name: growth
jobs:
  test-matrix:
    runs-on: ubuntu-latest
    strategy: {fail-fast: false}
    steps: [{run: 'true'}]
  brand-new-job:
    runs-on: ubuntu-latest
    steps: [{run: 'true'}]
"""

METADATA_ONLY_YAML = """\
name: metadata
jobs:
  call-reusable:
    uses: ./.github/workflows/other.yml
  pinned:
    runs-on: ubuntu-latest
    timeout-minutes: 3
    steps: [{run: 'true'}]
"""

BROKEN_YAML = "jobs: [oops, not: a: mapping\n"


class PipelineTimeoutGuardTest(unittest.TestCase):
    def _wf(self, tmp: Path, name: str, body: str) -> Path:
        p = tmp / name
        p.write_text(body, encoding="utf-8")
        return p

    def test_clean_workflow_green_in_both_modes(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._wf(Path(td), "clean.yml", CLEAN_YAML)
            self.assertTrue(guard.scan_workflow(p)["ok"])
            self.assertTrue(guard.scan_workflow(p, strict=True)["ok"])

    def test_r82_shape_baseline_discloses_known_gaps_non_fatal(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._wf(Path(td), "r82.yml", R82_SHAPE_YAML)
            rep = guard.scan_workflow(p)
            self.assertTrue(rep["ok"], "known baseline gaps must stay non-fatal in baseline mode")
            self.assertEqual(sorted(rep["knownBaselineGaps"]), sorted(guard.KNOWN_BASELINE_GAPS))
            self.assertEqual(rep["runnerJobs"], 5)
            self.assertEqual(rep["pinned"], 1)

    def test_r82_shape_strict_mode_is_red(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._wf(Path(td), "r82.yml", R82_SHAPE_YAML)
            rep = guard.scan_workflow(p, strict=True)
            self.assertFalse(rep["ok"], "strict mode must fail on the R82 gaps until option A lands")
            self.assertEqual(len(rep["violations"]), 4)

    def test_growth_beyond_baseline_is_violation(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._wf(Path(td), "growth.yml", GROWTH_YAML)
            rep = guard.scan_workflow(p)
            self.assertFalse(rep["ok"], "a NEW unpinned job must be a violation even in baseline mode (U6)")
            self.assertEqual(rep["violations"], ["brand-new-job"])
            self.assertNotIn("test-matrix", rep["violations"])

    def test_metadata_only_jobs_outside_budget_surface(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._wf(Path(td), "metadata.yml", METADATA_ONLY_YAML)
            rep = guard.scan_workflow(p)
            self.assertEqual(rep["runnerJobs"], 1, "reusable-workcall jobs (no runs-on) consume no runner minutes")
            self.assertTrue(rep["ok"])

    def test_unparseable_workflow_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._wf(Path(td), "bad.yml", BROKEN_YAML)
            with self.assertRaises(guard.WorkflowUnreadableError):
                guard.scan_workflow(p)

    def test_missing_workflow_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(guard.WorkflowUnreadableError):
                guard.scan_workflow(Path(td) / "absent.yml")

    def test_self_test_battery_passes(self):
        self.assertEqual(guard._self_test(), 0)

    def test_live_pipeline_matches_r82_baseline(self):
        """Live tree contract: the shipped pipeline.yml must carry exactly the
        R82 baseline gaps and nothing more — any extra gap is a regression this
        battery catches from the test lane without touching the protected yml."""
        live = REPO_ROOT / ".github" / "workflows" / "pipeline.yml"
        if not live.exists():
            self.skipTest("pipeline.yml not present in this checkout")
        rep = guard.scan_workflow(live)
        self.assertEqual(sorted(rep["unpinned"]), sorted(guard.KNOWN_BASELINE_GAPS),
                         "live pipeline drifted from the R82 baseline — update KNOWN_BASELINE_GAPS in the same PR as option A")


if __name__ == "__main__":
    unittest.main(verbosity=2)
