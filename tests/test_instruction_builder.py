#!/usr/bin/env python3
"""Offline tests for the rebuilt instruction_builder (audit F7-r2 slice).

The original module crashed with unconditional ImportError on every call
(phantom symbols `continuous_agent_loop._load_agent_rules` and
`role_registry.get_role_contract`) and had zero tests — this file locks the
rebuilt living-SSOT contract: honest source label, deterministic envelope,
fail-closed unknown-role handling, and no phantom-symbol regressions.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import instruction_builder as ib


class TestLoadRoleRules(unittest.TestCase):
    def test_returns_real_ssot_source_label(self):
        applicable, prohibited, source = ib.load_role_rules("coder")
        self.assertEqual(source, "role_trigger_matrix.ROLE_CONTRACTS")
        self.assertTrue(applicable, "must_follow bullets must surface as applicable")
        self.assertTrue(prohibited, "must_not + forbidden_operations must surface")

    def test_every_registered_role_loads(self):
        for role_id in sorted(ib.ROLE_CONTRACTS):
            applicable, prohibited, source = ib.load_role_rules(role_id)
            self.assertTrue(len(applicable) >= 0 and source == "role_trigger_matrix.ROLE_CONTRACTS")

    def test_unknown_role_fails_closed(self):
        with self.assertRaises(ValueError):
            ib.load_role_rules("no-such-role")

    def test_merged_canonical_name_is_not_silently_resolved(self):
        # cadence canonical name 'auditor' is NOT a ROLE_IDS-concrete contract;
        # the module must fail closed instead of silently guessing a source.
        with self.assertRaises(ValueError):
            ib.load_role_rules("auditor")


class TestBuildInstruction(unittest.TestCase):
    def test_five_section_shape_deterministic(self):
        block = ib.build_instruction("coder")
        self.assertEqual(
            sorted(block.keys()),
            ["actions", "forbidden", "mode", "rules", "source", "validation"],
        )
        self.assertTrue(block["source"]["deterministic"])
        self.assertFalse(block["source"]["llm_required"])
        # determinism: two builds are byte-identical
        self.assertEqual(ib.build_instruction("coder"), block)

    def test_injected_rules_override(self):
        block = ib.build_instruction(
            "coder", rules=(("custom rule",), ("custom ban",))
        )
        self.assertEqual(block["rules"], ["custom rule"])
        self.assertEqual(block["forbidden"], ["custom ban"])
        self.assertEqual(block["source"]["rules_source"], "injected")

    def test_validation_tiers_ladder(self):
        block = ib.build_instruction("coder")
        self.assertEqual(len(block["validation"]["tiers"]), 3)
        self.assertEqual(tuple(block["validation"]["tiers"]), ib.VALIDATION_TIERS)

    def test_weapons_surfaces_sorted(self):
        block = ib.build_instruction("coder")
        weapons = block["actions"]["weapons"]
        self.assertEqual(weapons, sorted(weapons))
        self.assertTrue(weapons, "coder carries SSOT dispatch weapons")


class TestRenderInstruction(unittest.TestCase):
    def test_envelope_sections_present(self):
        text = ib.build_and_render("coder")
        for section in ("MODE:", "RULES:", "ACTIONS:", "FORBIDDEN:", "VALIDATION:"):
            self.assertIn(section, text)

    def test_empty_sections_render_explicit_marker(self):
        block = ib.build_instruction("coder", rules=((), ()))
        text = ib.render_instruction(block)
        self.assertIn("RULES:\n  - none declared", text)
        self.assertIn("FORBIDDEN:\n  - none declared", text)


class TestNoPhantomRegression(unittest.TestCase):
    """AST-based guard: phantom symbols must never resurface as LIVE code.

    Docstring/comment mentions of the dead names are allowed (history
    documentation); Import/Name/Attribute usage is not — that is what made
    the original module dead-on-arrival (audit F7-r2).
    """

    @staticmethod
    def _live_code_facts(source: str) -> tuple[set, set]:
        import ast

        tree = ast.parse(source)
        imported_modules: set[str] = set()
        used_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_modules.add(node.module or "")
                used_names.update(a.name for a in node.names)
            elif isinstance(node, (ast.Name, ast.Attribute)):
                used_names.add(getattr(node, "id", getattr(node, "attr", "")))
        return imported_modules, used_names

    def test_no_phantom_symbol_is_live_code(self):
        source = Path(ib.__file__).read_text(encoding="utf-8")
        imported, used = self._live_code_facts(source)
        self.assertNotIn("_load_agent_rules", used)
        self.assertNotIn("get_role_contract", used)

    def test_no_loop_or_stale_registry_import_coupling(self):
        source = Path(ib.__file__).read_text(encoding="utf-8")
        imported, _ = self._live_code_facts(source)
        for banned in ("continuous_agent_loop", "role_registry"):
            hits = {m for m in imported if m and banned in m}
            self.assertFalse(hits, f"stale import coupling resurfaced: {hits}")


if __name__ == "__main__":
    unittest.main()
