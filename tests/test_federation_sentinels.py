#!/usr/bin/env python3
"""Offline unit tests for the #1689 sentinel verification layer in
scripts/ci/federation_satellite_sync.py.

The GitHub fetch (_fetch_remote_bytes) is monkeypatched - no network access is
required. Run:  python -m unittest tests.test_federation_sentinels -v
(or: python tests/test_federation_sentinels.py)
"""

from __future__ import annotations

import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

import federation_satellite_sync as sync  # noqa: E402


class SentinelPairLoading(unittest.TestCase):
    def test_fallback_to_defaults_when_manifest_absent(self):
        with tempfile.TemporaryDirectory() as td:
            pairs = sync.load_sentinel_pairs(Path(td))
            self.assertEqual(pairs, [dict(p) for p in sync.DEFAULT_SENTINEL_PAIRS])

    def test_manifest_pairs_override_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            man = root / "scripts" / "ci" / "satellite_sentinels.json"
            man.parent.mkdir(parents=True)
            man.write_text(
                json.dumps(
                    {
                        "pairs": [
                            {"open": "a.py", "satellite": "Supremeai-bd/supremeai-core", "path": "b.py"}
                        ]
                    }
                ),
                encoding="utf-8",
            )
            loaded = sync.load_sentinel_pairs(root)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["open"], "a.py")

    def test_corrupt_manifest_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            man = root / "scripts" / "ci" / "satellite_sentinels.json"
            man.parent.mkdir(parents=True)
            man.write_text("{not valid json", encoding="utf-8")
            pairs = sync.load_sentinel_pairs(root)
            self.assertEqual(pairs, [dict(p) for p in sync.DEFAULT_SENTINEL_PAIRS])

    def test_default_pairs_contract(self):
        for p in sync.DEFAULT_SENTINEL_PAIRS:
            self.assertTrue(p.get("open") and p.get("satellite") and p.get("path"), p)
            self.assertIn(p["satellite"], sync.DOMAIN_MAP)
        self.assertTrue(
            any(
                p["open"] == "gateway/main.py" and p["path"] == "main.py"
                for p in sync.DEFAULT_SENTINEL_PAIRS
            ),
            "api satellite root main.py parity pair is mandatory (#1689)",
        )

    def test_api_root_main_mapping_present_in_source(self):
        """Regression pin: the sync must map gateway/main.py to the api satellite root."""
        src = inspect.getsource(sync)
        self.assertIn('tmp_repo / "main.py"', src)
        self.assertIn('repo_root / "gateway" / "main.py"', src)


class SentinelVerification(unittest.TestCase):
    @staticmethod
    def _write_manifest(root: Path, pairs: list[dict]) -> None:
        man = root / "scripts" / "ci" / "satellite_sentinels.json"
        man.parent.mkdir(parents=True, exist_ok=True)
        man.write_text(json.dumps({"pairs": pairs}), encoding="utf-8")

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.pairs = [
            {"open": "gateway/main.py", "satellite": "Supremeai-bd/supremeai-api", "path": "main.py"},
            {"open": "core/main.py", "satellite": "Supremeai-bd/supremeai-core", "path": "main.py"},
        ]
        self._write_manifest(self.root, self.pairs)
        (self.root / "gateway").mkdir()
        (self.root / "gateway" / "main.py").write_bytes(b"hardened-main")
        (self.root / "core").mkdir()
        (self.root / "core" / "main.py").write_bytes(b"core-main")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.root, ignore_errors=True)

    def test_clean_when_remote_matches(self):
        orig = sync._fetch_remote_bytes

        def per_pair(repo, path, token, ref="main"):
            return b"hardened-main" if repo == "Supremeai-bd/supremeai-api" else b"core-main"

        sync._fetch_remote_bytes = per_pair
        try:
            clean, drift, errors = sync.verify_sentinels(self.root, "t")
            self.assertEqual(len(clean), 2)
            self.assertEqual(drift, [])
            self.assertEqual(errors, [])
        finally:
            sync._fetch_remote_bytes = orig

    def test_drift_detected_with_sha_detail(self):
        orig = sync._fetch_remote_bytes
        sync._fetch_remote_bytes = lambda repo, path, token, ref="main": b"stale-unsanitized"
        try:
            clean, drift, errors = sync.verify_sentinels(self.root, "t")
            self.assertEqual(clean, [])
            self.assertEqual(len(drift), 2)
            self.assertIn("sha256 local=", drift[0]["detail"])
            self.assertEqual(errors, [])
        finally:
            sync._fetch_remote_bytes = orig

    def test_absent_remote_surface_is_drift_not_error(self):
        orig = sync._fetch_remote_bytes
        sync._fetch_remote_bytes = lambda repo, path, token, ref="main": None
        try:
            clean, drift, errors = sync.verify_sentinels(self.root, "t")
            self.assertEqual(len(drift), 2)
            self.assertIn("absent", drift[0]["detail"])
            self.assertEqual(errors, [])
        finally:
            sync._fetch_remote_bytes = orig

    def test_infra_error_is_fail_closed_error(self):
        def boom(repo, path, token, ref="main"):
            raise RuntimeError("rate limited")

        orig = sync._fetch_remote_bytes
        sync._fetch_remote_bytes = boom
        try:
            clean, drift, errors = sync.verify_sentinels(self.root, "t")
            self.assertEqual(clean, [])
            self.assertEqual(drift, [])
            self.assertEqual(len(errors), 2)
            self.assertIn("verification fetch failed", errors[0]["detail"])
        finally:
            sync._fetch_remote_bytes = orig

    def test_satellite_filter_skips_other_pairs(self):
        orig = sync._fetch_remote_bytes
        sync._fetch_remote_bytes = lambda repo, path, token, ref="main": b"hardened-main"
        try:
            clean, drift, errors = sync.verify_sentinels(
                self.root, "t", only_satellites=["Supremeai-bd/supremeai-api"]
            )
            self.assertEqual(len(clean), 1)
            self.assertEqual(clean[0]["satellite"], "Supremeai-bd/supremeai-api")
        finally:
            sync._fetch_remote_bytes = orig

    def test_malformed_pair_is_error(self):
        orig = sync._fetch_remote_bytes
        sync._fetch_remote_bytes = lambda repo, path, token, ref="main": b"x"
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                self._write_manifest(root, [{"open": "only-open"}])
                clean, drift, errors = sync.verify_sentinels(root, "t")
                self.assertEqual(len(errors), 1)
                self.assertIn("malformed", errors[0]["detail"])
        finally:
            sync._fetch_remote_bytes = orig

    def test_missing_open_side_file_is_error_not_drift(self):
        orig = sync._fetch_remote_bytes
        sync._fetch_remote_bytes = lambda repo, path, token, ref="main": b"x"
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                self._write_manifest(root, self.pairs)
                clean, drift, errors = sync.verify_sentinels(root, "t")
                self.assertEqual(len(errors), 2)
                self.assertIn("missing in checkout", errors[0]["detail"])
        finally:
            sync._fetch_remote_bytes = orig


if __name__ == "__main__":
    unittest.main(verbosity=2)
