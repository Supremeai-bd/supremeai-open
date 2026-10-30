"""Unit tests for the supremeai-skills foundation seed.

Stdlib-only unittest battery per bridge doctrine. Covers: SKILL.md
frontmatter parsing, cursor/plugins manifest normalization, three-stage
progressive disclosure, package manager install/list/remove/pack
roundtrip, registry index validation, and sandbox execution with hard
timeout enforcement.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from registry.manifest_schema import (
    CapabilityDescriptor,
    ManifestError,
    parse_cursor_plugin,
    parse_skill_md,
)
from registry.package_manager import PackageManager, PackageManagerError
from registry.progressive_loader import ProgressiveLoader
from sandbox.executor import SkillSandbox

EXAMPLES = ROOT / "examples"

SKILL_MD_SAMPLE = """---
name: sample-skill
version: 1.2.3
description: A sample capability for tests.
triggers: [alpha, beta]
entry: scripts/run.py
---

Full instructions live here and load only at dispatch.
"""

PLUGIN_JSON_SAMPLE = json.dumps(
    {
        "name": "Thermos_Review",
        "version": "2.0.0",
        "description": "Deep security review workflow.",
        "commands": {
            "security-review": {"description": "full review"},
            "quick-scan": {"description": "fast pass"},
        },
    }
)


def make_skill(root: Path, name: str = "packme") -> Path:
    skill_dir = root / name
    (skill_dir / "scripts").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\nversion: 0.1.0\ndescription: pack test\nentry: scripts/go.py\n---\nbody\n",
        encoding="utf-8",
    )
    (skill_dir / "scripts" / "go.py").write_text(
        "print('packed ok')\n", encoding="utf-8"
    )
    return skill_dir


class TestManifestSchema(unittest.TestCase):
    def test_skill_md_roundtrip(self):
        descriptor, body = parse_skill_md(SKILL_MD_SAMPLE)
        self.assertEqual(descriptor.name, "sample-skill")
        self.assertEqual(descriptor.version, "1.2.3")
        self.assertEqual(descriptor.triggers, ["alpha", "beta"])
        self.assertEqual(descriptor.entry, "scripts/run.py")
        self.assertEqual(descriptor.source_format, "skill-md")
        self.assertIn("dispatch", body)

    def test_skill_md_missing_required_field(self):
        with self.assertRaises(ManifestError):
            parse_skill_md("---\nname: only-name\n---\nbody")

    def test_skill_md_invalid_name(self):
        bad = "---\nname: Bad_Name!\nversion: 1\ndescription: x\n---\nbody"
        with self.assertRaises(ManifestError):
            parse_skill_md(bad)

    def test_cursor_plugin_normalization(self):
        descriptor, _ = parse_cursor_plugin(PLUGIN_JSON_SAMPLE)
        self.assertEqual(descriptor.name, "thermos-review")
        self.assertEqual(descriptor.source_format, "cursor-plugin")
        self.assertEqual(descriptor.triggers, ["security-review", "quick-scan"])
        descriptor.validate()

    def test_cursor_plugin_invalid_json(self):
        with self.assertRaises(ManifestError):
            parse_cursor_plugin("{not json")


class TestProgressiveLoader(unittest.TestCase):
    def setUp(self):
        self.loader = ProgressiveLoader([EXAMPLES])

    def test_discover_indexes_reference_skill(self):
        index = self.loader.discover()
        self.assertIn("echo-greeter", index)
        self.assertEqual(index["echo-greeter"].entry, "scripts/greet.py")

    def test_summaries_are_lightweight(self):
        self.loader.discover()
        for summary in self.loader.summaries():
            self.assertNotIn("instructions", summary)
            self.assertIn("name", summary)

    def test_load_returns_full_instructions(self):
        self.loader.discover()
        loaded = self.loader.load("echo-greeter")
        self.assertIn("Instructions", loaded["instructions"])
        self.assertEqual(loaded["entry"], "scripts/greet.py")

    def test_load_unknown_raises(self):
        self.loader.discover()
        with self.assertRaises(KeyError):
            self.loader.load("does-not-exist")

    def test_trigger_matching(self):
        self.loader.discover()
        self.assertEqual(
            self.loader.match("please greet the operator").name, "echo-greeter"
        )
        self.assertIsNone(self.loader.match("unrelated task text"))

    def test_read_index_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "index.json"
            index.write_text(
                json.dumps({"skills": {"x": {"git": "git@example:x.git"}}}),
                encoding="utf-8",
            )
            skills = ProgressiveLoader.read_index(index)
            self.assertIn("x", skills)
            bad = Path(tmp) / "bad.json"
            bad.write_text(
                json.dumps({"skills": {"y": {"ref": "no-git"}}}), encoding="utf-8"
            )
            with self.assertRaises(ManifestError):
                ProgressiveLoader.read_index(bad)


class TestPackageManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "installed"
        self.root.mkdir()
        self.manager = PackageManager(
            self.root, index_path=Path(self.tmp.name) / "absent.json"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_list_remove_roundtrip(self):
        source = make_skill(Path(self.tmp.name))
        destination = self.manager.install(str(source))
        self.assertTrue((destination / "SKILL.md").is_file())
        self.assertIn("packme", self.manager.list_installed())
        self.manager.remove("packme")
        self.assertNotIn("packme", self.manager.list_installed())

    def test_install_refuses_duplicates(self):
        source = make_skill(Path(self.tmp.name))
        self.manager.install(str(source))
        with self.assertRaises(PackageManagerError):
            self.manager.install(str(source))

    def test_install_rejects_non_skill(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        with self.assertRaises(PackageManagerError):
            self.manager.install(str(empty))

    def test_pack_creates_archive(self):
        skill_dir = make_skill(Path(self.tmp.name))
        archive = self.manager.pack(skill_dir)
        self.assertTrue(archive.is_file())
        self.assertEqual(archive.suffixes[-1], ".skill")

    def test_remove_unknown_fails(self):
        with self.assertRaises(PackageManagerError):
            self.manager.remove("ghost")


class TestSandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.skill = make_skill(Path(self.tmp.name), name="sandboxed")

    def tearDown(self):
        self.tmp.cleanup()

    def test_runs_entry_script(self):
        sandbox = SkillSandbox(self.skill)
        result = sandbox.run("scripts/go.py")
        self.assertEqual(result.returncode, 0)
        self.assertIn("packed ok", result.stdout)
        self.assertFalse(result.timed_out)

    def test_timeout_enforced(self):
        (self.skill / "scripts" / "slow.py").write_text(
            "import time; time.sleep(30)\n", encoding="utf-8"
        )
        result = SkillSandbox(self.skill).run("scripts/slow.py", timeout_s=1.0)
        self.assertTrue(result.timed_out)
        self.assertIn("timeout", result.stderr)

    def test_missing_script_and_escape(self):
        sandbox = SkillSandbox(self.skill)
        with self.assertRaises(FileNotFoundError):
            sandbox.run("scripts/nope.py")
        with self.assertRaises(ValueError):
            sandbox.run("../outside.py")

    def test_sandbox_flag_visible_to_script(self):
        (self.skill / "scripts" / "env.py").write_text(
            "import os; print(os.environ.get('SKILL_SANDBOX'))", encoding="utf-8"
        )
        result = SkillSandbox(self.skill).run("scripts/env.py")
        self.assertEqual(result.stdout.strip(), "1")


class TestDescriptorValidation(unittest.TestCase):
    def test_validate_rejects_bad_name(self):
        descriptor = CapabilityDescriptor(
            name="Space Name", version="1", description="d"
        )
        with self.assertRaises(ManifestError):
            descriptor.validate()


if __name__ == "__main__":
    unittest.main(verbosity=2)
