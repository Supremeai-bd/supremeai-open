#!/usr/bin/env python3
"""tests/test_bump_candidate_probe.py — tests for scripts/ci/bump_candidate_probe.py.

Issue #2106 R50 option C: the dependency freshness probe is REPORT-ONLY.
These tests pin the three contracts that make that safe:

    1. Correctness  — parsers (npm lock v2/v3 + v1 fallback, requirements
       pins), freshness verdict matrix, and the full report pipeline on
       injected fetchers (zero network in tests).
    2. Honesty      — absent surfaces, unparseable locks, and probe failures
       are all surfaced as explicit skip/unknown rows, never silently dropped
       and never turned into a red exit (report-only exit contract).
    3. Never-do     — the live code never writes files, never spawns
       subprocesses, never touches .github/**, and leaves both guard
       baselines byte-identical after a full offline collection; surfaces
       come from npm_dep_cve_guard.LOCK_PATHS (SSOT), never a private copy.

Dual-mode: pytest AND stdlib plain runner (python3 tests/test_bump_candidate_probe.py),
offline and deterministic — the house dual-mode doctrine (test_license_ssot_guard pattern).
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = REPO_ROOT / "scripts" / "ci" / "bump_candidate_probe.py"
NPM_GUARD = REPO_ROOT / "scripts" / "ci" / "npm_dep_cve_guard.py"


def _load_probe():
    spec = importlib.util.spec_from_file_location("_bump_probe_under_test", PROBE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P = _load_probe()


class TmpCase(unittest.TestCase):
    """tmpdir helper base (kept dependency-free)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="bump-probe-test-")
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)


class TestNpmLockParsing(TmpCase):

    def test_v3_packages_block_with_dev_and_nested(self):
        lock = self.tmp / "package-lock.json"
        lock.write_text(json.dumps({
            "lockfileVersion": 3,
            "packages": {
                "": {"name": "root"},
                "node_modules/lodash": {"version": "4.17.20"},
                "node_modules/@org/pkg": {"version": "1.2.3"},
                "node_modules/a/node_modules/b": {"version": "0.0.9"},
                "node_modules/devonly": {"version": "2.0.0", "dev": True},
                "node_modules/linked": {"resolved": "file:../x"},
                "packages/workspace-thing": {"version": "9.9.9"},
            },
        }), encoding="utf-8")
        got = {(p["name"], p["version"], p["dev"]) for p in P.parse_npm_lock(lock)}
        self.assertEqual(got, {
            ("lodash", "4.17.20", False),
            ("@org/pkg", "1.2.3", False),
            ("b", "0.0.9", False),          # nested key reduced to real name
            ("devonly", "2.0.0", True),     # dev kept but tagged
        })  # link (no version) and workspace path excluded

    def test_v1_dependencies_recursive_fallback(self):
        lock = self.tmp / "package-lock-v1.json"
        lock.write_text(json.dumps({"lockfileVersion": 1, "dependencies": {
            "left-pad": {"version": "1.3.0"},
            "outer": {"version": "2.0.0", "dependencies": {"inner": {"version": "0.1.0"}}},
        }}), encoding="utf-8")
        got = {(p["name"], p["version"]) for p in P.parse_npm_lock(lock)}
        self.assertEqual(got, {("left-pad", "1.3.0"), ("outer", "2.0.0"), ("inner", "0.1.0")})

    def test_unparseable_lock_raises_jsonerror_for_honest_skip(self):
        bad = self.tmp / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            P.parse_npm_lock(bad)  # collect_surfaces turns this into a skip row


class TestRequirementsParsing(TmpCase):

    def test_pins_extras_markers_comments_options(self):
        req = self.tmp / "requirements-test.txt"
        req.write_text("\n".join([
            "# comment line",
            "requests==2.31.0",
            "uvicorn[standard]==0.30.1 ; python_version >= '3.9'",
            "-r other.txt",
            "-e ./local",
            "--hash=sha256:abc",
            "Dask_Utils==3.1.2  # trailing note",
            "flask >= 2.0",
            "",
        ]), encoding="utf-8")
        got = {(p["name"], p["version"]) for p in P.parse_requirements(req)}
        self.assertEqual(got, {
            ("requests", "2.31.0"),
            ("uvicorn", "0.30.1"),
            ("dask-utils", "3.1.2"),  # PEP 503 normalization, extras stripped
        })

    def test_unpinned_manifest_yields_zero_pairs(self):
        req = self.tmp / "requirements-unpinned.txt"
        req.write_text("flask\npydantic>=2\n", encoding="utf-8")
        self.assertEqual(P.parse_requirements(req), [])


class TestFreshnessVerdict(unittest.TestCase):

    def test_matrix(self):
        self.assertEqual(P.freshness_verdict("1.2.3", "1.3.0"), "BUMP")
        self.assertEqual(P.freshness_verdict("4.17.21", "4.17.21"), "fresh")
        self.assertEqual(P.freshness_verdict("1.2", "1.2.1"), "BUMP")      # shorter tuple
        self.assertEqual(P.freshness_verdict("2.0.0", "1.9.9"), "fresh")   # latest older
        self.assertEqual(P.freshness_verdict("1.0.0", None), "unknown")    # no latest
        self.assertEqual(P.freshness_verdict("1.0.0", "abc-alpha"), "unknown")  # unparseable
        self.assertEqual(P.freshness_verdict("1.0.0-rc1", "1.1.0"), "unknown")  # local chunk


class TestReportPipeline(TmpCase):

    def _fixture_surface(self):
        req = self.tmp / "requirements-test.txt"
        req.write_text("requests==2.31.0\nuvicorn[standard]==0.30.1\ndask==3.1.2\n", encoding="utf-8")
        return [("pip", "requirements-test.txt", P.parse_requirements(req), ""),
                ("npm", "absent/package-lock.json", [], "absent-surface")]

    def test_counts_and_rows_on_injected_fetcher(self):
        fake = {"requests": "2.32.3", "uvicorn": "0.30.1", "dask": None}
        lines, counters = P.build_report(self._fixture_surface(), fetch=lambda k, n: fake.get(n))
        self.assertEqual(counters, {"BUMP": 1, "fresh": 1, "unknown": 1, "skipped": 1})
        self.assertTrue(any("[BUMP  ] pip requests 2.31.0 -> 2.32.3" in l for l in lines))
        self.assertTrue(any("[skip  ] npm absent/package-lock.json — absent-surface" in l for l in lines))
        self.assertTrue(any("SUMMARY: 1 bump candidates" in l for l in lines))
        self.assertTrue(any(l.startswith("BUMP CANDIDATE PROBE") and "option C" in l for l in lines))

    def test_probe_failure_is_honest_unknown_never_exception(self):
        def boom(kind, name):
            raise TimeoutError("simulated outage")
        lines, counters = P.build_report(self._fixture_surface(), fetch=boom)
        self.assertEqual(counters["unknown"], 3)
        self.assertTrue(all("probe-failed: TimeoutError" in l for l in lines if l.startswith("[unknwn]")))

    def test_same_package_across_surfaces_probed_once_not_misreported(self):
        req1 = self.tmp / "requirements-a.txt"
        req2 = self.tmp / "requirements-b.txt"
        for p in (req1, req2):
            p.write_text("requests==2.31.0\n", encoding="utf-8")
        surfaces = [("pip", p.name, P.parse_requirements(p), "") for p in (req1, req2)]
        calls = []

        def fetch(kind, name):
            calls.append(name)
            return "2.32.3"

        lines, counters = P.build_report(surfaces, fetch=fetch)
        self.assertEqual(calls, ["requests"])               # cached: one probe
        self.assertEqual(counters["BUMP"], 2)               # both surfaces BUMP
        self.assertEqual(counters["unknown"], 0)            # no false unknown


class TestNeverDoContracts(unittest.TestCase):
    """The #2106 section-4 never-do list, mechanically pinned."""

    def test_live_code_never_writes_or_spawns(self):
        live_src = PROBE.read_text(encoding="utf-8").split("def _selftest", 1)[0]
        self.assertIsNone(re.search(r"\bsubprocess\b|write_text|write_bytes|(?<![A-Za-z_])open\(", live_src))

    def test_live_code_never_touches_github_protected_path(self):
        live_src = PROBE.read_text(encoding="utf-8").split("def _selftest", 1)[0]
        self.assertNotIn(".github", live_src)

    def test_guard_baselines_byte_identical_after_full_collection(self):
        baselines = [REPO_ROOT / "scripts/ci/npm_dep_cve_baseline.json",
                     REPO_ROOT / "scripts/ci/py_dep_cve_baseline.json"]
        before = {b: b.read_bytes() for b in baselines if b.is_file()}
        self.assertEqual(len(before), 2)
        P.collect_surfaces(REPO_ROOT)
        for b, data in before.items():
            self.assertEqual(b.read_bytes(), data, f"baseline mutated: {b.name}")

    def test_surfaces_ssot_from_guard_not_private_copy(self):
        self.assertTrue(NPM_GUARD.is_file())
        self.assertTrue(
            Path("infrastructure/mcp-control-plane/package-lock.json") in tuple(P._load_npm_guard().LOCK_PATHS)
        )
        # the probe module must not re-declare a lock list of its own
        live_src = PROBE.read_text(encoding="utf-8").split("def _selftest", 1)[0]
        self.assertNotIn("package-lock.json\"", live_src.replace(
            'GUARD_REL = Path("scripts/ci/npm_dep_cve_guard.py")', ""))


class TestPoetryPlaneParsing(TmpCase):
    """R51/#2122: the probe's py side imports the guard's OWN synthesizer —
    the poetry plane (pyproject.toml [tool.poetry.dependencies] main group)
    must yield honest fix-side freshness pairs, never a silent blind spot."""

    def _poetry_fixture(self) -> Path:
        pyproject = self.tmp / "pyproject.toml"
        pyproject.write_text("\n".join([
            "[tool.poetry.dependencies]",
            'python = "^3.11"',
            'fastapi = "^0.136.0"',
            'requests = "2.31.0"',
            'httpx = { version = "^0.28.0", extras = ["http2"] }',
            'pillow = { version = "^11.0", optional = true }',
            'mypkg = { path = "../mypkg" }',
            'starlette = "*"',
            'cachetools = ">=5.0.0"',
            "",
        ]), encoding="utf-8")
        return pyproject

    def test_poetry_forms_to_freshness_pairs(self):
        pairs, skips = P.parse_poetry_pyproject(
            self._poetry_fixture(), synth=P._load_py_guard().synthesize_poetry_requirements)
        got = {(p["name"], p["version"], p["upper"], p["open_floor"]) for p in pairs}
        self.assertEqual(got, {
            ("fastapi", "0.136.0", "0.137.0", False),   # caret -> ranged floor/upper
            ("requests", "2.31.0", None, False),        # exact pin
            ("httpx", "0.28.0", "0.29.0", False),       # dict form, extras stripped
            ("cachetools", "5.0.0", None, True),        # open floor, unbounded above
        })
        self.assertTrue(any("optional" in s for s in skips))       # pillow skipped WITH note
        self.assertTrue(any("path" in s for s in skips))           # local source skipped WITH note
        self.assertTrue(any("wildcard-any" in s for s in skips))   # `*` skipped WITH note
        self.assertEqual([p for p in pairs if p["name"] == "python"], [])  # python key excluded

    def test_pep621_only_pyproject_is_empty_not_error(self):
        pyproject = self.tmp / "pyproject.toml"
        pyproject.write_text('[project]\nname = "x"\nversion = "0.1.0"\n', encoding="utf-8")
        pairs, skips = P.parse_poetry_pyproject(
            pyproject, synth=P._load_py_guard().synthesize_poetry_requirements)
        self.assertEqual(pairs, [])
        self.assertEqual(skips, [])

    def test_py_guard_ssot_surface_exposes_both_planes(self):
        g = P._load_py_guard()
        self.assertIn("pyproject.toml", g.MANIFEST_SURFACE)
        self.assertIn("requirements", g.MANIFEST_SURFACE)

    def test_collect_surfaces_enumerates_live_poetry_plane(self):
        rows = P.collect_surfaces(REPO_ROOT)
        pyproj = [r for r in rows if str(r[1]).endswith("pyproject.toml")]
        self.assertTrue(any(r[2] for r in pyproj),
                        f"poetry plane blind spot regressed: {pyproj}")


class TestPoetryVerdict(unittest.TestCase):
    """Range-aware freshness semantics (R51/#2122): BUMP means the pin
    itself needs an edit, never merely that a newer release exists."""

    def test_range_aware_matrix(self):
        self.assertEqual(P.freshness_verdict("0.136.0", "0.136.9", "0.137.0"), "fresh")   # in-range
        self.assertEqual(P.freshness_verdict("0.136.0", "0.137.0", "0.137.0"), "BUMP")    # boundary
        self.assertEqual(P.freshness_verdict("0.136.0", "0.140.1", "0.137.0"), "BUMP")    # outside
        self.assertEqual(P.freshness_verdict("5.0.0", "9.9.9", None, True), "fresh")      # open floor
        self.assertEqual(P.freshness_verdict("1.0.0", "1.1.0", "garbage"), "unknown")     # bad upper


class TestCliContract(unittest.TestCase):

    def test_selftest_hermetic_exit_0(self):
        r = subprocess.run([sys.executable, str(PROBE), "--self-test"],
                           capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("self-test", r.stdout)

    def test_plan_offline_exit_0_and_counts_surfaces(self):
        r = subprocess.run([sys.executable, str(PROBE), "--plan"],
                           capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("offline surface snapshot", r.stdout)
        self.assertIn("locked pairs across", r.stdout)

    def test_mutually_exclusive_flags_exit_2(self):
        r = subprocess.run([sys.executable, str(PROBE), "--plan", "--live"],
                           capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT))
        self.assertEqual(r.returncode, 2)

    def test_unknown_flag_exit_2(self):
        r = subprocess.run([sys.executable, str(PROBE), "--nonsense"],
                           capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT))
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
