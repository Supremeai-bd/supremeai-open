#!/usr/bin/env python3
"""Offline contract tests for the S11 Surgical Adoption Engine (issue #498).

Covers: Gold Pearl extraction (Python AST + TS brace balancing, budget,
fail-closed), native zero-bloat fitting (stdlib-only stubs, standalone
execution), the transplant generator (atomic single-new-file patches,
canonical satellites), the vendored-tree CI guard (R1-R5 fail-closed) and
the two live benchmark blueprints (REA + Moli) with the
কতটুকু দরকার / কীভাবে দরকার breakdown.

Pure stdlib. Run: python3 -m unittest test_s11_surgical_adoption -v
"""

import subprocess
import sys
import unittest
from pathlib import Path

AGENTS = Path(__file__).resolve().parent.parent / "scripts" / "agents"
CI = Path(__file__).resolve().parent.parent / "scripts" / "ci"
sys.path.insert(0, str(AGENTS))
sys.path.insert(0, str(CI))

import scout_extractor as ex
import vendored_tree_guard as vg


def fingerprint_source() -> str:
    lines = ["import hashlib", "", ""]
    lines.append("def evidence_fingerprint(payload: bytes) -> str:")
    lines.append('    """SHA-256 fingerprint, fail-closed."""')
    lines.append("    if not payload:")
    lines.append("        raise ValueError('empty payload')")
    for i in range(30):
        lines.append(
            "    stage_{i} = hashlib.sha256(payload + str({i}).encode())"
            ".hexdigest()".replace("{i}", str(i))
        )
    lines.append("    return stage_29")
    lines.append("")
    lines.append("def unrelated():")
    lines.append("    return 'noise'")
    return "\n".join(lines)


TS_SOURCE = "\n".join(
    [
        "import { Node } from './dom';",
        "",
        "export function semanticFilter(nodes: Node[]): Node[] {",
        "  const out: Node[] = [];",
    ]
    + [f"  if (!nodes[{i}]) throw new Error('unknown node');" for i in range(20)]
    + ["  return out;", "}", "", "export const noise = 1;"]
)


class GoldPearlExtraction(unittest.TestCase):
    def test_01_python_slice_exact(self):
        s = ex.extract_python_slice(fingerprint_source(), "evidence_fingerprint")
        self.assertEqual(s.language, "python")
        self.assertEqual(s.line_count, 35)
        self.assertTrue(s.budget_ok)
        self.assertEqual(s.imports_needed, ("hashlib",))
        self.assertTrue(s.source_segment.startswith("def evidence_fingerprint"))

    def test_02_sibling_code_not_in_slice(self):
        s = ex.extract_python_slice(fingerprint_source(), "evidence_fingerprint")
        self.assertNotIn("unrelated", s.source_segment)
        self.assertNotIn("noise", s.source_segment)

    def test_03_budget_bounds(self):
        self.assertEqual(ex.GOLD_PEARL_MIN_LINES, 20)
        self.assertEqual(ex.GOLD_PEARL_MAX_LINES, 100)
        with self.assertRaises(ex.ExtractionError):
            ex.extract_python_slice("def tiny():\n    return 1\n", "tiny")

    def test_04_missing_and_ambiguous_targets(self):
        with self.assertRaises(ex.ExtractionError):
            ex.extract_python_slice(fingerprint_source(), "ghost")
        doubled = fingerprint_source() + "\n\n" + fingerprint_source()
        with self.assertRaises(ex.ExtractionError):
            ex.extract_python_slice(doubled, "evidence_fingerprint")
        with self.assertRaises(ex.ExtractionError):
            ex.extract_python_slice("", "x")

    def test_05_typescript_brace_balancing(self):
        s = ex.extract_typescript_slice(TS_SOURCE, "semanticFilter")
        self.assertEqual(s.language, "typescript")
        self.assertEqual(s.line_count, 24)
        self.assertTrue(s.source_segment.rstrip().endswith("}"))
        self.assertNotIn("noise", s.source_segment)

    def test_06_typescript_fail_closed(self):
        with self.assertRaises(ex.ExtractionError):
            ex.extract_typescript_slice(TS_SOURCE, "ghost")
        with self.assertRaises(ex.ExtractionError):
            ex.extract_typescript_slice(
                "export function broken() {\n  return 1;\n", "broken"
            )

    def test_07_usage_driven_imports(self):
        # `json` is imported at module level but UNUSED in the slice ->
        # must not be reported; hashlib is used -> reported.
        src = "import json\nimport hashlib\n\n" + "\n".join(
            fingerprint_source().splitlines()[2:]
        )
        s = ex.extract_python_slice(src, "evidence_fingerprint")
        self.assertEqual(s.imports_needed, ("hashlib",))


class NativeZeroBloatFitting(unittest.TestCase):
    def test_08_stub_generation_with_provenance(self):
        s = ex.extract_python_slice(fingerprint_source(), "evidence_fingerprint")
        stub = ex.generate_adaptation_stub(s, "morluto/rea", "MIT")
        self.assertIn("github.com/morluto/rea", stub)
        self.assertIn("MIT", stub)
        self.assertIn("zero-dependency", stub)

    def test_09_stub_runs_standalone(self):
        s = ex.extract_python_slice(fingerprint_source(), "evidence_fingerprint")
        stub = ex.generate_adaptation_stub(s, "morluto/rea", "MIT")
        namespace: dict = {}
        exec(compile(stub, "<stub>", "exec"), namespace)  # noqa: S102
        digest = namespace["evidence_fingerprint"](b"abc")
        self.assertEqual(len(digest), 64)

    def test_10_fail_closed_on_empty_payload(self):
        s = ex.extract_python_slice(fingerprint_source(), "evidence_fingerprint")
        stub = ex.generate_adaptation_stub(s, "morluto/rea", "MIT")
        namespace: dict = {}
        exec(compile(stub, "<stub>", "exec"), namespace)  # noqa: S102
        with self.assertRaises(ValueError):
            namespace["evidence_fingerprint"](b"")

    def test_11_foreign_imports_rejected(self):
        s = ex.ExtractedSlice(
            "python",
            "needs_pandas",
            "import pandas as pd\ndef f():\n    return 1\n",
            1,
            3,
            ("pandas",),
        )
        with self.assertRaises(ex.ExtractionError):
            ex.generate_adaptation_stub(s, "x/y", "MIT")
        with self.assertRaises(ex.ExtractionError):
            ex.verify_stub_standalone("import requests\nx = 1\n")

    def test_12_typescript_stubs_routed_not_pythonified(self):
        s = ex.extract_typescript_slice(TS_SOURCE, "semanticFilter")
        with self.assertRaises(ex.ExtractionError):
            ex.generate_adaptation_stub(s, "lexmount/moli", "Apache-2.0")

    def test_13_stdlib_allowlist_is_zero_dep(self):
        for module in ex.STDLIB_ALLOWLIST:
            root = module.split(".")[0]
            self.assertIn(root, sys.stdlib_module_names, module)


class TransplantGenerator(unittest.TestCase):
    def test_14_atomic_new_file_patch(self):
        patch = ex.generate_transplant_patch(
            "supremeai-mcp-control-plane",
            "src/ledger/evidence_record.py",
            ex.generate_adaptation_stub(
                ex.extract_python_slice(fingerprint_source(), "evidence_fingerprint"),
                "morluto/rea",
                "MIT",
            ),
        )
        self.assertTrue(patch.new_file)
        self.assertGreater(patch.byte_size, 0)
        self.assertIn("supremeai-mcp-control-plane", ex.CANONICAL_SATELLITES)

    def test_15_canonical_satellite_enforced(self):
        with self.assertRaises(ex.ExtractionError):
            ex.generate_transplant_patch("unknown-sat", "a.py", "x = 1\n")

    def test_16_unsafe_paths_rejected(self):
        for path in ("/abs/path.py", "../escape.py", ""):
            with self.assertRaises(ex.ExtractionError, msg=path):
                ex.generate_transplant_patch("supremeai-open", path, "x = 1\n")

    def test_17_stub_reverified_at_transplant(self):
        with self.assertRaises(ex.ExtractionError):
            ex.generate_transplant_patch("supremeai-open", "ok.py", "import requests\n")
        with self.assertRaises(ex.ExtractionError):
            ex.generate_transplant_patch("supremeai-open", "bad.py", "def broken(:\n")


class VendoredTreeGuard(unittest.TestCase):
    def test_18_rules_r1_to_r5(self):
        self.assertEqual(vg.EXIT_VIOLATION, 2)
        cases = (
            ([vg.AddedFile("vendor/lib/foo.py", 100)], "R1"),
            ([vg.AddedFile("src/node_modules/x/index.js", 10)], "R1"),
            ([vg.AddedFile("src/blob.jar", 10)], "R2"),
            ([vg.AddedFile("src/huge.bin", vg.VENDORED_FILE_MAX_BYTES + 1)], "R2"),
            (
                [
                    vg.AddedFile(f"m{i}.py", 10)
                    for i in range(vg.VENDORED_TREE_FILE_COUNT + 1)
                ],
                "R3",
            ),
            ([vg.AddedFile("package-lock.json", 400)], "R4"),
            ([vg.AddedFile("Cargo.lock", 400)], "R4"),
            ([vg.AddedFile(f"f{i}.py", 300 * 1024) for i in range(8)], "R5"),
        )
        for files, rule in cases:
            verdict = vg.guard_added_files(files)
            self.assertEqual(verdict.exit_code, 2, rule)
            self.assertTrue(any(v.startswith(rule) for v in verdict.violations), rule)

    def test_19_clean_pr_passes(self):
        verdict = vg.guard_added_files(
            [
                vg.AddedFile("scripts/agents/scout_extractor.py", 9000),
                vg.AddedFile("tests/test_s11_surgical_adoption.py", 7000),
            ]
        )
        self.assertEqual(verdict.exit_code, 0)
        self.assertEqual(vg.guard_added_files([]).exit_code, 0)

    def test_20_constants_from_issue_doctrine(self):
        self.assertEqual(vg.VENDORED_FILE_MAX_BYTES, 512 * 1024)
        self.assertEqual(vg.VENDORED_TREE_MAX_TOTAL_BYTES, 2 * 1024 * 1024)
        self.assertIn("node_modules/", vg.VENDORED_DIR_ROOTS)

    def test_21_self_test_entrypoints_green(self):
        self.assertTrue(ex.self_test())
        self.assertTrue(vg.self_test())


class BenchmarkBlueprints(unittest.TestCase):
    def test_22_both_live_benchmarks_present(self):
        names = {b.benchmark for b in ex.BENCHMARK_BLUEPRINTS}
        self.assertEqual(names, {"REA Evidence Ledger", "Moli Semantic Tree"})

    def test_23_breakdown_pair_present(self):
        for b in ex.BENCHMARK_BLUEPRINTS:
            ex.validate_blueprint(b)
            self.assertTrue(b.what_is_needed)  # কতটুকু দরকার
            self.assertTrue(b.how_needed)  # কীভাবে দরকার
            self.assertTrue(b.prohibited)

    def test_24_zero_bloat_plans_are_native(self):
        for b in ex.BENCHMARK_BLUEPRINTS:
            self.assertIn(b.native_target, ("python", "typescript"))
            self.assertTrue(
                any(
                    "zero" in step
                    or "stdlib" in step
                    or "no cargo" in step
                    or "no JVM" in step
                    for step in b.zero_bloat_plan
                )
            )

    def test_25_upstream_attribution(self):
        repos = {b.upstream_repository for b in ex.BENCHMARK_BLUEPRINTS}
        self.assertEqual(repos, {"morluto/rea", "lexmount/moli"})
        for b in ex.BENCHMARK_BLUEPRINTS:
            self.assertIn(b.license, ("MIT", "Apache-2.0"))

    def test_26_blueprint_fail_closed(self):
        with self.assertRaises(ex.ExtractionError):
            ex.validate_blueprint(
                ex.AdoptionBlueprint(
                    "", "r", "MIT", "g", "w", "h", "python", ("z",), ("p",)
                )
            )
        with self.assertRaises(ex.ExtractionError):
            ex.validate_blueprint(
                ex.AdoptionBlueprint(
                    "b", "r", "MIT", "g", "w", "h", "java", ("z",), ("p",)
                )
            )


class CliSmoke(unittest.TestCase):
    def test_27_extractor_cli_json(self):
        import json
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
            fh.write(fingerprint_source())
            path = fh.name
        try:
            out = subprocess.run(
                [
                    sys.executable,
                    str(AGENTS / "scout_extractor.py"),
                    "--extract",
                    path,
                    "evidence_fingerprint",
                    "--json",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        payload = json.loads(out.stdout)
        self.assertEqual(payload["lines"], 35)
        self.assertTrue(payload["budget_ok"])

    def test_28_guard_cli_exit_semantics(self):
        clean = subprocess.run(
            [
                sys.executable,
                str(CI / "vendored_tree_guard.py"),
                "--files-json",
                '[{"path": "src/ok.py", "bytes": 100}]',
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(clean.returncode, 0)
        dirty = subprocess.run(
            [
                sys.executable,
                str(CI / "vendored_tree_guard.py"),
                "--files-json",
                '[{"path": "vendor/x.py", "bytes": 10}]',
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(dirty.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
