#!/usr/bin/env python3
"""Offline contract tests for the S10 Ecosystem Scout Agent (issue #497).

Covers: role registry (#497 criterion 1 — scout with scoped read-only
weapons), the Surgical Extraction Guard (anti-vending invariant, Gold
Pearl budget, native fitting, provenance hygiene), the 4-phase
methodology pipeline, the EcosystemDossier fail-closed validation matrix,
the MCP tool reference core (`scout_analyze_repository`) and the markdown
artifact export.

Pure stdlib. Run: python3 -m unittest test_s10_ecosystem_scout -v
"""
import sys
import unittest
from pathlib import Path

AGENTS = Path(__file__).resolve().parent.parent / "scripts" / "agents"
sys.path.insert(0, str(AGENTS))

import ecosystem_scout_reference as scout  # noqa: E402
import role_registry as reg  # noqa: E402
import role_trigger_matrix as rtm  # noqa: E402


def dossier(**overrides):
    return scout._valid_dossier(**overrides)


class RoleRegistryContract(unittest.TestCase):
    def test_01_scout_registered(self):
        registry = reg.default_registry()
        self.assertEqual(registry.list_roles(), ("ecosystem-scout",))
        record = registry.get("ecosystem-scout")
        self.assertTrue(record.read_only)

    def test_02_scoped_weapons_superset_of_ssot(self):
        # Issue #497 mandates: read-only URL, AST parser, repo inspector,
        # artifact writer — plus the #489 dispatch weapons.
        self.assertEqual(
            reg.SCOUT_WEAPONS,
            frozenset({"search_web", "read_url_content", "gh_issue_create",
                       "ast_parser", "repo_inspector", "artifact_writer"}))
        self.assertTrue(
            rtm.provision_weapons("ecosystem-scout") <= reg.SCOUT_WEAPONS)

    def test_03_read_only_invariant(self):
        self.assertFalse(reg.SCOUT_WEAPONS & rtm.CODE_WRITE_WEAPONS)
        registry = reg.default_registry()
        self.assertTrue(registry.check_read_only("ecosystem-scout"))

    def test_04_fail_closed_lookups(self):
        registry = reg.default_registry()
        with self.assertRaises(ValueError):
            registry.get("ghost")

    def test_05_fail_closed_registrations(self):
        registry = reg.default_registry()
        bad = [
            reg.RoleRecord(role_id="ghost", display_name="g",
                           operational_weapons=frozenset({"search_web"}),
                           read_only=True, description="x"),
            reg.RoleRecord(role_id="ecosystem-scout", display_name="dup",
                           operational_weapons=reg.SCOUT_WEAPONS,
                           read_only=True, description="x"),
            reg.RoleRecord(role_id="ecosystem-scout", display_name="leak",
                           operational_weapons=reg.SCOUT_WEAPONS
                           | {"write_to_file"},
                           read_only=True, description="x"),
        ]
        for record in bad:
            with self.assertRaises(ValueError):
                registry.register(record)


class SurgicalExtractionGuard(unittest.TestCase):
    def test_06_anti_vending_invariant(self):
        with self.assertRaises(scout.DossierError):
            scout.validate_surgical_extraction(scout.SurgicalExtraction(
                ("c",), "native python blueprint",
                full_repo_vending_prohibited=False))

    def test_07_gold_pearl_components_required(self):
        with self.assertRaises(scout.DossierError):
            scout.validate_surgical_extraction(scout.SurgicalExtraction(
                (), "native python blueprint", True))

    def test_08_blueprint_must_be_native(self):
        with self.assertRaises(scout.DossierError):
            scout.validate_surgical_extraction(scout.SurgicalExtraction(
                ("c",), "drop in the foreign jar", True))

    def test_09_vendor_markers_rejected(self):
        for marker in ("git clone https://example", "npm install org/repo",
                       "copy the whole repository", "vendored tree"):
            with self.assertRaises(scout.DossierError, msg=marker):
                scout.validate_surgical_extraction(scout.SurgicalExtraction(
                    ("c",), f"just {marker} and we are done", True))

    def test_10_gold_pearl_budget(self):
        self.assertEqual(scout.GOLD_PEARL_MIN_LINES, 20)
        self.assertEqual(scout.GOLD_PEARL_MAX_LINES, 100)
        for ok in (20, 50, 100):
            scout.validate_gold_pearl_budget(ok)
        for bad in (19, 101, 0, -5):
            with self.assertRaises(scout.DossierError):
                scout.validate_gold_pearl_budget(bad)

    def test_11_provenance_header(self):
        header = scout.provenance_header("morluto/rea", "MIT")
        self.assertIn("github.com/morluto/rea", header)
        self.assertIn("MIT", header)
        self.assertIn("Adapted for SupremeAI Federation", header)
        with self.assertRaises(scout.DossierError):
            scout.provenance_header("", "MIT")


class DossierValidationMatrix(unittest.TestCase):
    def test_12_full_dossier_passes(self):
        scout.validate_dossier(dossier())

    def test_13_verdict_enum(self):
        self.assertEqual(
            scout.VERDICTS,
            ("ADOPT_IMMEDIATELY", "EXTRACT_PATTERNS_ONLY", "MONITOR", "REJECT"))
        with self.assertRaises(scout.DossierError):
            scout.validate_dossier(dossier(verdict="SHIP_IT"))

    def test_14_comparative_analysis_both_directions(self):
        with self.assertRaises(scout.DossierError):
            scout.validate_dossier(dossier(
                comparative_analysis=scout.replace_comparative(
                    superior_capabilities=())))
        with self.assertRaises(scout.DossierError):
            scout.validate_dossier(dossier(
                comparative_analysis=scout.replace_comparative(
                    supremeai_advantages=())))

    def test_15_satellite_routing_mandatory(self):
        with self.assertRaises(scout.DossierError):
            scout.validate_dossier(dossier(
                actionable_takeaways=scout.replace_takeaways(
                    target_satellites=())))
        with self.assertRaises(scout.DossierError):
            scout.validate_dossier(dossier(
                actionable_takeaways=scout.replace_takeaways(
                    target_satellites=(scout.SatelliteAction(
                        "sat", "fork_it", "why"),))))

    def test_16_watchouts_mandatory(self):
        with self.assertRaises(scout.DossierError):
            scout.validate_dossier(dossier(
                watchouts_and_risks=scout.replace_watchouts(
                    security_or_compliance_concerns=())))

    def test_17_adopt_requires_known_license(self):
        scout.validate_dossier(dossier(verdict="ADOPT_IMMEDIATELY"))
        with self.assertRaises(scout.DossierError):
            scout.validate_dossier(dossier(
                verdict="ADOPT_IMMEDIATELY",
                target=scout.replace_target(license="unknown")))

    def test_18_reject_documents_prohibited_practices(self):
        scout.validate_dossier(dossier(verdict="REJECT"))
        with self.assertRaises(scout.DossierError):
            scout.validate_dossier(dossier(
                verdict="REJECT",
                watchouts_and_risks=scout.replace_watchouts(
                    prohibited_practices=())))


class FourPhaseMethodology(unittest.TestCase):
    def _chain(self, **overrides):
        phases = list(scout.PHASES)
        findings = overrides.get("findings", ("finding",))
        skip_artifact = overrides.get("skip_artifact", False)
        return tuple(
            scout.PhaseEvidence(p, findings if p == phases[0] else ("f",),
                                artifact="" if (skip_artifact and
                                                p == scout.PHASE_4_RFC)
                                else "dossier.md")
            for p in phases)

    def test_19_phase_enums_in_order(self):
        self.assertEqual(
            scout.PHASES,
            ("PHASE_1_EXTRACTION", "PHASE_2_DISSECTION",
             "PHASE_3_AUDIT", "PHASE_4_RFC"))
        self.assertEqual(scout.run_methodology(self._chain()), "dossier.md")

    def test_20_order_enforced(self):
        with self.assertRaises(scout.PhaseError):
            scout.run_methodology(tuple(reversed(self._chain())))
        with self.assertRaises(scout.PhaseError):
            scout.run_methodology(self._chain()[1:])

    def test_21_marketing_only_extraction_rejected(self):
        with self.assertRaises(scout.PhaseError):
            scout.run_methodology(self._chain(
                findings=("marketing landing page only",)))

    def test_22_rfc_must_emit_artifact(self):
        with self.assertRaises(scout.PhaseError):
            scout.run_methodology(self._chain(skip_artifact=True))

    def test_23_unknown_phase_rejected(self):
        with self.assertRaises(scout.PhaseError):
            scout.validate_phase_evidence(scout.PhaseEvidence(
                "PHASE_5_HYPE", ("f",)))


class ScoutAnalyzeCore(unittest.TestCase):
    def test_24_manifest_truth_extraction(self):
        d = scout.scout_analyze_repository(scout.ScoutInputs(
            repository="lexmount/moli", license="Apache-2.0",
            manifest_json='{"dependencies": {"playwright-core": "1"}, '
                          '"engines": {"node": "24"}}',
            file_tree=("src/dom.ts", "src/semantic.ts"),
            readme_headline="semantic DOM trees"))
        self.assertEqual(d.target.tech_stack[0], "node:24")
        self.assertIn("dep:playwright-core", d.target.tech_stack)
        self.assertEqual(d.verdict, "MONITOR")
        scout.validate_dossier(d)

    def test_25_python_manifest_extraction(self):
        d = scout.scout_analyze_repository(scout.ScoutInputs(
            repository="example/pyrepo", license="MIT",
            manifest_yaml="- fastapi==0.1\n- pydantic==2.0\n",
            file_tree=("a.py",)))
        self.assertIn("py:fastapi", d.target.tech_stack)
        self.assertIn("py:pydantic", d.target.tech_stack)

    def test_26_fail_closed_inputs(self):
        cases = (
            scout.ScoutInputs(repository=""),
            scout.ScoutInputs(repository="x"),
            scout.ScoutInputs(repository="x", manifest_yaml="a: 1"),
            scout.ScoutInputs(repository="x", manifest_yaml="- fastapi",
                              file_tree=()),
            scout.ScoutInputs(repository="x", manifest_json="{bad",
                              file_tree=("a",)),
            scout.ScoutInputs(repository="x", manifest_yaml="a: 1",
                              file_tree=("a",)),
        )
        for inputs in cases:
            with self.assertRaises(scout.DossierError, msg=repr(inputs)):
                scout.scout_analyze_repository(inputs)


class MarkdownArtifactExport(unittest.TestCase):
    def test_27_standard_artifact_format(self):
        md = scout.render_dossier_markdown(dossier())
        self.assertIn("# Ecosystem Dossier — example/org-repo", md)
        self.assertIn("`EXTRACT_PATTERNS_ONLY`", md)
        self.assertIn("কতটুকু দরকার", md)
        self.assertIn("কীভাবে দরকার", md)
        self.assertIn("supremeai-mcp-control-plane", md)
        self.assertIn("replicate_pattern", md)

    def test_28_provenance_embedded(self):
        md = scout.render_dossier_markdown(dossier())
        self.assertIn("adapted from: github.com/example/org-repo", md)
        self.assertIn("Upstream License: MIT", md)

    def test_29_invalid_dossier_cannot_export(self):
        with self.assertRaises(scout.DossierError):
            scout.render_dossier_markdown(dossier(verdict="HYPE"))


class Canon(unittest.TestCase):
    def test_30_canonical_satellites_present(self):
        for satellite in ("supremeai-browser", "supremeai-agents",
                          "supremeai-mcp-control-plane"):
            self.assertIn(satellite, scout.CANONICAL_SATELLITES)

    def test_31_action_types(self):
        self.assertEqual(scout.ACTION_TYPES,
                         ("adopt_library", "replicate_pattern",
                          "integrate_mcp"))

    def test_32_self_test_entrypoints_green(self):
        self.assertTrue(scout.self_test())
        self.assertTrue(reg.self_test())
        self.assertTrue(rtm.self_test())


if __name__ == "__main__":
    unittest.main(verbosity=2)
