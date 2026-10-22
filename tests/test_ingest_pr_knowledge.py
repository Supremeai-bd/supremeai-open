#!/usr/bin/env python3
"""Contract tests for autonomous PR Knowledge Ingestion Engine."""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

import ingest_pr_knowledge as ingest_mod


class TestIngestPrKnowledge(unittest.TestCase):
    def test_self_test_passes(self):
        code = ingest_mod.run_self_test()
        self.assertEqual(code, 0)

    def test_empty_body_handled(self):
        data, ver = ingest_mod.extract_envelope_json("")
        self.assertIsNone(data)
        self.assertEqual(ver, "empty_body")

    def test_v2_auditor_validation(self):
        envelope = {
            "schema": "pr-knowledge-envelope/2",
            "task_issue_ref": 88,
            "role": "auditor",
            "knowledge": {
                "audit_methodology": "Verified against AST and live MCP",
                "alternative_audit_methods": "Static grep scan",
                "improper_audit_traps": "Aggressive brute-force scanning avoided",
                "prevention_gate": "Added CI contract test",
            },
        }
        body = f"<!-- pr-knowledge-envelope v2 -->\n{ingest_mod.json.dumps(envelope)}\n<!-- /pr-knowledge-envelope -->"
        data, ver = ingest_mod.extract_envelope_json(body)
        self.assertEqual(ver, "v2")
        self.assertIsNotNone(data)
        valid, role, _reason, k = ingest_mod.validate_knowledge(data, ver)
        self.assertTrue(valid)
        self.assertEqual(role, "auditor")
        facts = ingest_mod.format_learned_facts(88, role, k, "Audit PR")
        self.assertTrue(len(facts) >= 1)
        self.assertIn("[PR #88 Audit Gate]", facts[0]["content"])

    def test_v2_missing_field_fails_validation(self):
        envelope = {
            "schema": "pr-knowledge-envelope/2",
            "role": "coder",
            "knowledge": {
                "fix_mechanism": "Some mechanism",
                # missing why_this_way, alternatives_rejected, pitfalls_to_avoid
            },
        }
        valid, _role, reason, _k = ingest_mod.validate_knowledge(envelope, "v2")
        self.assertFalse(valid)
        self.assertIn("Missing role fields", reason)


if __name__ == "__main__":
    unittest.main()
