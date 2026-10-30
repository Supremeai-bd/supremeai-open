"""Parity test for the agent-cadence-dispatcher pilot skill."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from registry.manifest_schema import parse_skill_md

SKILL_DIR = ROOT.parent / "skills" / "agent-cadence-dispatcher"
# ROOT is skills/, so skill lives under ROOT
SKILL_DIR = ROOT / "agent-cadence-dispatcher"


class TestAgentCadenceDispatcherSkill(unittest.TestCase):
    def test_skill_manifest_parses(self):
        text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        descriptor, _body = parse_skill_md(text)
        descriptor.validate()
        self.assertEqual(descriptor.name, "agent-cadence-dispatcher")
        self.assertEqual(descriptor.entry, "scripts/dispatch.py")
        self.assertIn("cadence", descriptor.triggers)

    def test_entry_script_exists(self):
        self.assertTrue((SKILL_DIR / "scripts" / "dispatch.py").is_file())

    def test_progressive_loader_discovers(self):
        from registry.progressive_loader import ProgressiveLoader

        loader = ProgressiveLoader([ROOT])
        index = loader.discover()
        self.assertIn("agent-cadence-dispatcher", index)


if __name__ == "__main__":
    unittest.main(verbosity=2)
