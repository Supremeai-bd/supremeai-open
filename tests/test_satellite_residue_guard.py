#!/usr/bin/env python3
"""Offline tests for scripts/ci/satellite_residue_guard.py (#1676 detection half).

বাংলা: guard-the-guard অফলাইন টেস্ট — classification কোর, calibration (বৈধ
লেআউট অস্পৃষ্ট), রিপোর্ট/exit র‍্যাঙ্কিং, নেটওয়ার্ক স্তরের fail-closed আচরণ
(monkeypatched), roster wiring। কোনো নেটওয়ার্ক নেই। চালান:
    python -m unittest tests.test_satellite_residue_guard -v
"""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

import satellite_residue_guard as guard  # noqa: E402


def sha(i: int) -> str:
    return f"sha{i:03d}"


def studio_like_fixture() -> list[dict]:
    return [
        {"path": "package.json", "type": "blob", "sha": sha(1)},
        {"path": "src/utils/api.ts", "type": "blob", "sha": sha(2)},
        {"path": "src/styles/cockpit.css", "type": "blob", "sha": sha(3)},
        {"path": "infrastructure/cloudflare-studio-proxy/wrangler.toml", "type": "blob", "sha": sha(4)},
        {"path": "studio", "type": "tree", "sha": sha(5)},
        {"path": "studio/package.json", "type": "blob", "sha": sha(1)},
        {"path": "studio/src/utils/api.ts", "type": "blob", "sha": sha(9)},
        {"path": "studio/src/components/auth/ServiceHealthBar.test.ts", "type": "blob", "sha": sha(6)},
        {"path": "studio/src/services/apiClient.ts", "type": "blob", "sha": sha(7)},
    ]


# ---------------------------------------------------------------------------
# classification core
# ---------------------------------------------------------------------------


class TestClassifyResidue(unittest.TestCase):
    def test_detects_all_three_classes(self) -> None:
        got = guard.classify_residue(studio_like_fixture(), "studio")
        by_path = {r["path"]: r for r in got["residue"]}
        self.assertEqual(got["residueCount"], 4)
        self.assertEqual(by_path["studio/package.json"]["classification"], "identical")
        self.assertEqual(by_path["studio/src/utils/api.ts"]["classification"], "diverged")
        self.assertEqual(by_path["studio/src/services/apiClient.ts"]["classification"], "nested-only")
        self.assertTrue(got["anchorDirPresent"])

    def test_twin_strips_exactly_one_anchor_segment(self) -> None:
        got = guard.classify_residue(studio_like_fixture(), "studio")
        row = next(r for r in got["residue"] if r["path"] == "studio/src/utils/api.ts")
        self.assertEqual(row["twin"], "src/utils/api.ts")
        self.assertTrue(row["twinExists"])

    def test_legitimate_root_dirs_untouched(self) -> None:
        # বৈধ root-level infrastructure/ (closeout-প্রমাণিত intended) residue নয়।
        got = guard.classify_residue(studio_like_fixture(), "studio")
        self.assertTrue(all(not r["path"].startswith("infrastructure/") for r in got["residue"]))

    def test_other_named_dirs_are_not_residue(self) -> None:
        # gateway/ নামের dir studio-satellite residue নয় — কেবল নিজের anchor।
        entries = studio_like_fixture() + [
            {"path": "gateway", "type": "tree", "sha": sha(8)},
            {"path": "gateway/main.py", "type": "blob", "sha": sha(2)},
        ]
        got = guard.classify_residue(entries, "studio")
        self.assertTrue(all(not r["path"].startswith("gateway/") for r in got["residue"]))

    def test_clean_satellite(self) -> None:
        entries = [
            {"path": "package.json", "type": "blob", "sha": sha(1)},
            {"path": "src/main.py", "type": "blob", "sha": sha(2)},
        ]
        got = guard.classify_residue(entries, "studio")
        self.assertFalse(got["anchorDirPresent"])
        self.assertEqual(got["residueCount"], 0)

    def test_empty_anchor_dir_is_present_but_zero_residue(self) -> None:
        entries = [{"path": "studio", "type": "tree", "sha": sha(5)}]
        got = guard.classify_residue(entries, "studio")
        self.assertTrue(got["anchorDirPresent"])
        self.assertEqual(got["residueCount"], 0)

    def test_no_root_twin_sibling_nesting(self) -> None:
        # `studio/`-এর ভেতরে `studio/x/y`-এর twin হলো root `x/y` — নিজেই নয়।
        entries = [
            {"path": "x/y", "type": "blob", "sha": sha(1)},
            {"path": "studio/x/y", "type": "blob", "sha": sha(1)},
        ]
        got = guard.classify_residue(entries, "studio")
        self.assertEqual(got["residueCount"], 1)
        self.assertEqual(got["residue"][0]["classification"], "identical")


# ---------------------------------------------------------------------------
# report + exit ranking
# ---------------------------------------------------------------------------


class TestReportAndExit(unittest.TestCase):
    def test_report_totals_and_verdict(self) -> None:
        res = [{"repo": "r/a", "anchor": "studio", **guard.classify_residue(studio_like_fixture(), "studio")}]
        rep = guard.build_report(res, "main")
        self.assertEqual(rep["totals"]["residueFiles"], 4)
        self.assertEqual(rep["totals"]["satellitesWithResidue"], 1)
        self.assertEqual(rep["verdict"], "residue-found")
        self.assertEqual(rep["issue"], 1676)

    def test_exit_ranking(self) -> None:
        clean = guard.build_report([{"repo": "r", "anchor": "studio", "anchorDirPresent": False, "residue": [], "residueCount": 0, "counts": {}}], "main")
        dirty = guard.build_report([{"repo": "r", "anchor": "studio", "anchorDirPresent": True, "residue": [{"path": "studio/x"}], "residueCount": 1, "counts": {}}], "main")
        self.assertEqual(guard.exit_code_for(clean, 0), 0)
        self.assertEqual(guard.exit_code_for(dirty, 0), 1)
        self.assertEqual(guard.exit_code_for(dirty, 2), 2)

    def test_human_report_carries_worklist(self) -> None:
        res = [{"repo": "Supremeai-bd/supremeai-studio", "anchor": "studio", **guard.classify_residue(studio_like_fixture(), "studio")}]
        text = guard.render_human(guard.build_report(res, "main"))
        self.assertIn("RESIDUE FOUND", text)
        self.assertIn("studio/package.json", text)


# ---------------------------------------------------------------------------
# thin network layer — fail-closed behavior (injected, offline)
# ---------------------------------------------------------------------------


class TestScanSatellite(unittest.TestCase):
    def test_infra_error_is_honest_row(self) -> None:
        with mock.patch.object(guard, "fetch_tree", side_effect=RuntimeError("HTTP 403")):
            row = guard.scan_satellite("Supremeai-bd/supremeai-api", "gateway", "", "main")
        self.assertIn("error", row)
        self.assertEqual(row["residueCount"], 0)
        self.assertIsNone(row["anchorDirPresent"])

    def test_scan_passes_entries_through(self) -> None:
        with mock.patch.object(guard, "fetch_tree", return_value=studio_like_fixture()):
            row = guard.scan_satellite("Supremeai-bd/supremeai-studio", "studio", "", "main")
        self.assertEqual(row["residueCount"], 4)

    def test_resolve_token_chain_and_empty(self) -> None:
        env = {k: v for k, v in os.environ.items() if k not in guard.TOKEN_ENV_CHAIN}
        env["SAT_SYNC_PAT"] = "t1"
        with mock.patch.dict("os.environ", env, clear=True):
            self.assertEqual(guard.resolve_token(None), "t1")
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(guard.resolve_token(None), "")
        self.assertEqual(guard.resolve_token("DEFINITELY_UNSET_ENV_VAR_XYZ"), "")


# ---------------------------------------------------------------------------
# self-test + wiring pins
# ---------------------------------------------------------------------------


class TestSelfTestAndWiring(unittest.TestCase):
    def test_guard_self_test_passes(self) -> None:
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            rc = guard.self_test()
        self.assertEqual(rc, 0, buf_out.getvalue())

    def test_roster_entry_present(self) -> None:
        src = (REPO_ROOT / "scripts" / "ci" / "run_all_guards.py").read_text(encoding="utf-8")
        self.assertIn('"scripts/ci/satellite_residue_guard.py", "--self-test"', src)

    def test_ssot_registry_covers_bridge_prefix_routes(self) -> None:
        # bridge_intake.route_files-এর prefix-routing যে repos-গুলোকে namespace-
        # প্রিফিক্সে রাউট করে, residue-SSOT সেগুলোর প্রত্যেকটি কভার করে।
        intake = (REPO_ROOT / "scripts" / "bridge" / "bridge_intake.py").read_text(encoding="utf-8")
        for anchor in ("studio/", "gateway/", "core/", "browser/", "vscode/"):
            self.assertIn(f'"{anchor}"', intake, f"routing anchor {anchor} must exist")
        for repo in guard.SATELLITE_ANCHORS:
            self.assertIn("supremeai-", repo)

    def test_json_report_shape(self) -> None:
        rep = guard.build_report([], "main")
        self.assertIn("guard", rep)
        self.assertIn("satellites", rep)
        json.dumps(rep)  # serializable


if __name__ == "__main__":
    unittest.main()
