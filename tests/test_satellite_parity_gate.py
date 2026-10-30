#!/usr/bin/env python3
"""Offline tests for scripts/ci/satellite_parity_gate.py (#1792).

No network: the GitHub fetch layer is injected/monkeypatched. Run:
    python -m unittest tests.test_satellite_parity_gate -v
"""

from __future__ import annotations

import base64
import io
import json
import sys
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))

import satellite_parity_gate as gate  # noqa: E402

P1 = {"open": "gateway/main.py", "satellite": "Supremeai-bd/supremeai-api", "path": "main.py"}
P2 = {"open": "core/main.py", "satellite": "Supremeai-bd/supremeai-core", "path": "main.py"}
P3 = {"open": "studio/package.json", "satellite": "Supremeai-bd/supremeai-studio",
      "path": "package.json"}


def fake_fetch(mapping):
    """mapping: {(repo, path): bytes | None | Exception}"""
    def _f(repo, path, token, ref="main"):
        key = (repo, path)
        if key not in mapping:
            raise AssertionError(f"unexpected fetch {key}")
        v = mapping[key]
        if isinstance(v, Exception):
            raise v
        return v
    return _f


class ClassifyTests(unittest.TestCase):
    def test_clean(self):
        verdict, d = gate.classify_pair(P1, b"same", b"same", None)
        self.assertEqual(verdict, "clean")
        self.assertEqual(d["size"], 4)

    def test_drift_has_hunks_and_delta(self):
        verdict, d = gate.classify_pair(P1, b"a" * 20, b"b", None)
        self.assertEqual(verdict, "drift")
        self.assertIn("byte-size delta", d["hunks"])
        self.assertIn("+19 B", d["hunks"])

    def test_drift_satellite_absent(self):
        verdict, d = gate.classify_pair(P1, b"data", None, None)
        self.assertEqual(verdict, "drift")
        self.assertIn("absent", d["detail"])

    def test_error_infra(self):
        verdict, _ = gate.classify_pair(P1, None, None, "rate limited")
        self.assertEqual(verdict, "error")

    def test_error_open_absent(self):
        verdict, _ = gate.classify_pair(P1, None, b"x", None)
        self.assertEqual(verdict, "error")


class ExitCodeTests(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(gate.exit_code_for({"summary": {"errors": 0, "drift": 0, "total": 7}}), 0)

    def test_drift(self):
        self.assertEqual(gate.exit_code_for({"summary": {"errors": 0, "drift": 1, "total": 7}}), 1)

    def test_infra_wins(self):
        self.assertEqual(gate.exit_code_for({"summary": {"errors": 2, "drift": 1, "total": 7}}), 2)


class RunGateTests(unittest.TestCase):
    def test_full_flow_two_clean_one_drift(self):
        fetcher = fake_fetch({
            ("Supremeai-bd/supremeai-core", "main.py"): b"same",
            ("Supremeai-bd/supremeai-studio", "package.json"): b"{}",
            ("Supremeai-bd/supremeai-api", "main.py"): b"old",
        })
        with mock.patch.object(gate, "read_open_side", side_effect=[
                b"same", b"same", b"new"]):
            report = gate.run_gate([P1, P2, P3], "tok", fetcher=fetcher, repo_root=None)
        self.assertEqual(report["summary"], {"total": 3, "clean": 1, "drift": 2, "errors": 0})
        self.assertEqual(report["drift"][0]["pair"]["path"], "main.py")
        self.assertIn("byte-size delta", report["drift"][0]["hunks"])

    def test_malformed_pair_is_error_not_crash(self):
        report = gate.run_gate([{"open": "", "satellite": "r", "path": ""}], "tok",
                               fetcher=fake_fetch({}), repo_root=None)
        self.assertEqual(report["summary"]["errors"], 1)

    def test_satellite_infra_is_fail_closed_error(self):
        fetcher = fake_fetch({
            ("Supremeai-bd/supremeai-core", "main.py"):
                urllib.error.HTTPError("u", 403, "forbidden", {}, io.BytesIO(b"")),
        })
        with mock.patch.object(gate, "read_open_side", return_value=b"x"):
            report = gate.run_gate([P2], "tok", fetcher=fetcher, repo_root=None)
        self.assertEqual(report["summary"]["errors"], 1)
        self.assertIn("403", report["errors"][0]["detail"])

    def test_open_side_local_missing_is_error(self):
        report = gate.run_gate([P2], "tok", fetcher=fake_fetch({}),
                               repo_root=Path("/nonexistent-root-xyz"))
        self.assertEqual(report["summary"]["errors"], 1)


class HunkSummaryTests(unittest.TestCase):
    def test_lines_capped(self):
        big = "\n".join(f"line {i}" for i in range(500)) + "\n"
        out = gate.hunk_summary(big.encode(), ("x\n" + big).encode())
        self.assertLessEqual(len(out.splitlines()), gate.MAX_DIFF_LINES + 5)

    def test_delta_sign_negative(self):
        out = gate.hunk_summary(b"short", b"much longer satellite content")
        self.assertIn("open -24 B", out)


class IssueBodyTests(unittest.TestCase):
    def _report(self):
        with mock.patch.object(gate, "read_open_side", return_value=b"new"):
            return gate.run_gate([P1], "tok",
                                 fetcher=fake_fetch({(P1["satellite"], P1["path"]): b"old"}),
                                 repo_root=None)

    def test_body_contains_contract_markers(self):
        rep = self._report()
        body = gate.build_issue_body(rep)
        for marker in ("Report-only", "byte-size delta", "#1792", "no push, no merge",
                       "Remediation"):
            self.assertIn(marker, body)
        self.assertIn("+new", body)  # drift hunks render the diff, not the detail string

    def test_body_errors_section(self):
        rep = {"checkedAt": "2026-10-28T00:00:00Z", "ref": "main", "allRemote": False,
               "summary": {"total": 1, "clean": 0, "drift": 0, "errors": 1},
               "clean": [], "drift": [],
               "errors": [{"pair": P1, "detail": "open-side fetch failed: boom"}]}
        body = gate.build_issue_body(rep)
        self.assertIn("fail-closed", body)
        self.assertIn("boom", body)


class TokenTests(unittest.TestCase):
    def test_chain_prefers_first(self):
        with mock.patch.dict("os.environ", {"SAT_SYNC_PAT": "a", "GITHUB_TOKEN": "b"}):
            self.assertEqual(gate.resolve_token(), "a")

    def test_chain_falls_back(self):
        with mock.patch.dict("os.environ", {"OPEN_SYNC_PAT": "b"}, clear=True):
            self.assertEqual(gate.resolve_token(), "b")

    def test_chain_empty_raises(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeError):
                gate.resolve_token()


class FetchBlobTests(unittest.TestCase):
    def _resp(self, obj):
        return io.BytesIO(json.dumps(obj).encode())

    def test_404_is_none(self):
        err = urllib.error.HTTPError("u", 404, "nf", {}, io.BytesIO(b""))
        with mock.patch.object(gate.urllib.request, "urlopen", side_effect=err):
            self.assertIsNone(gate.fetch_blob("r", "p", "t"))

    def test_infra_raises(self):
        err = urllib.error.HTTPError("u", 403, "forbidden", {}, io.BytesIO(b""))
        with mock.patch.object(gate.urllib.request, "urlopen", side_effect=err):
            with self.assertRaises(urllib.error.HTTPError):
                gate.fetch_blob("r", "p", "t")

    def test_decodes_base64(self):
        payload = {"content": base64.b64encode(b"hello").decode()}
        with mock.patch.object(gate.urllib.request, "urlopen",
                               return_value=self._resp(payload)):
            self.assertEqual(gate.fetch_blob("r", "p", "t"), b"hello")


class SelfTestAndMainTests(unittest.TestCase):
    def test_self_test_passes(self):
        self.assertTrue(gate.self_test())

    def test_main_infra_when_manifest_missing(self):
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            code = gate.main(["--manifest", "/nonexistent/manifest.json"])
        self.assertEqual(code, 2)

    def test_main_refuses_empty_manifest(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"pairs": []}, f)
            path = f.name
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            code = gate.main(["--manifest", path])
        self.assertEqual(code, 2)


class ManifestGatewayCoverageTests(unittest.TestCase):
    """#3656: the manifest must pin the Dockerfile-load-bearing gateway/ package.

    #1772 made `COPY gateway/ gateway/` build-critical on supremeai-api, but v1
    of the manifest pinned only root artifacts - so the scheduled gate was
    structurally blind to the #3649 failed-deploy drift class (satellite
    gateway/ absent, live-verified 2026-10-30 with a positive-control probe).
    These pins keep the manifest covering its own layout contract.
    """

    @classmethod
    def setUpClass(cls):
        cls.manifest_path = (Path(__file__).resolve().parents[1]
                             / "scripts" / "ci" / "satellite_sentinels.json")
        cls.manifest = json.loads(cls.manifest_path.read_text(encoding="utf-8"))
        cls.pairs = cls.manifest["pairs"]

    def _api_pairs(self):
        return [p for p in self.pairs if p.get("satellite") == "Supremeai-bd/supremeai-api"]

    def test_gateway_package_sentinels_present(self):
        pinned = {(p.get("open"), p.get("path")) for p in self._api_pairs()}
        self.assertIn(("gateway/__init__.py", "gateway/__init__.py"), pinned)
        self.assertIn(("gateway/main.py", "gateway/main.py"), pinned)

    def test_package_sentinels_are_package_true(self):
        # a regression to root-flattened paths would silently re-blind the
        # gate to the COPY gateway/ gateway/ dependency (#3649 class).
        # gateway/main.py legitimately maps to TWO surfaces (root main.py
        # entrypoint + package gateway/main.py); uniqueness is per (open, path).
        for want in ("gateway/__init__.py", "gateway/main.py"):
            match = [p for p in self._api_pairs()
                     if p.get("open") == want and p.get("path", "").startswith("gateway/")]
            self.assertEqual(len(match), 1, want)
            self.assertTrue(match[0].get("path", "").startswith("gateway/"), want)
        pinned = {(p.get("open"), p.get("path")) for p in self.pairs}
        self.assertEqual(len(pinned), len(self.pairs))

    def test_manifest_open_paths_exist_on_disk(self):
        # manifest-rot guard: a sentinel whose open-side file is gone would
        # make every scheduled run error (exit 2, fail-closed) forever
        root = self.manifest_path.parents[2]
        missing = [p["open"] for p in self.pairs
                   if not (root / p["open"]).is_file()]
        self.assertEqual(missing, [])

    def test_gateway_dockerfile_still_copies_the_package(self):
        # the dependency that makes the package sentinels load-bearing: if the
        # satellite layout contract changes again, revisit the manifest (#3656)
        dockerfile = (self.manifest_path.parents[2] / "gateway" / "Dockerfile")
        self.assertTrue(dockerfile.is_file())
        self.assertIn("COPY gateway/ gateway/", dockerfile.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
