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

    def test_markdown_reflection_parsing(self):
        body = """## Summary
Fix gateway routing drift.

## Reflection Evidence (why + alternatives_rejected)
- **why:** The routing config omitted anthropic model which caused fail-closed error.
- **alternatives_rejected:**
  - Hardcode model aliases in code: Rejected because violates fail-closed doctrine.
  - Disable contract test: Rejected because test is core SSOT.
"""
        data, ver = ingest_mod.extract_envelope_json(body)
        self.assertEqual(ver, "v2")
        self.assertIsNotNone(data)
        valid, role, reason, k = ingest_mod.validate_knowledge(data, ver)
        self.assertTrue(valid, f"Validation failed: {reason}")
        self.assertEqual(role, "coder")
        self.assertIn("routing config omitted", k["why_this_way"])
        self.assertEqual(len(k["alternatives_rejected"]), 2)
        self.assertEqual(k["alternatives_rejected"][0]["method"], "Hardcode model aliases in code")
        facts = ingest_mod.format_learned_facts(992, role, k, "Fix gateway routing drift")
        self.assertEqual(len(facts), 2)

    def test_parse_touched_files_from_diff(self):
        sample_diff = """diff --git a/scripts/agent.py b/scripts/agent.py
index 123456..789abc 100644
--- a/scripts/agent.py
+++ b/scripts/agent.py
@@ -1,3 +1,3 @@
-old
+new
diff --git a/tests/test_agent.py b/tests/test_agent.py
index abc123..def456 100644
--- a/tests/test_agent.py
+++ b/tests/test_agent.py
"""
        files = ingest_mod.parse_touched_files_from_diff(sample_diff)
        self.assertEqual(files, ["scripts/agent.py", "tests/test_agent.py"])

    def test_run_ingest_with_diff_metadata(self):
        sample_diff = "diff --git a/foo.py b/foo.py\n+print('hello')"
        envelope = {
            "schema": "pr-knowledge-envelope/2",
            "role": "coder",
            "knowledge": {
                "fix_mechanism": "Mechanism",
                "why_this_way": "Why",
                "alternatives_rejected": [{"method": "alt", "why_rejected": "no"}],
                "pitfalls_to_avoid": ["pitfall"],
            },
        }
        body = f"<!-- pr-knowledge-envelope v2 -->\n{ingest_mod.json.dumps(envelope)}\n<!-- /pr-knowledge-envelope -->"
        ok = ingest_mod.run_ingest(
            pr_num=999,
            body=body,
            title="Test Diff Ingest",
            dry_run=True,
            diff_text=sample_diff,
        )
        self.assertTrue(ok)

    def test_read_text_safe_encodings(self):
        import tempfile
        # Test UTF-8
        with tempfile.NamedTemporaryFile("wb", delete=False) as f:
            f.write("hello utf8".encode("utf-8"))
            p_utf8 = f.name
        self.assertEqual(ingest_mod.read_text_safe(p_utf8), "hello utf8")

        # Test UTF-16 LE with BOM
        with tempfile.NamedTemporaryFile("wb", delete=False) as f:
            f.write(b"\xff\xfe" + "hello utf16".encode("utf-16le"))
            p_utf16 = f.name
        self.assertEqual(ingest_mod.read_text_safe(p_utf16), "hello utf16")

        Path(p_utf8).unlink(missing_ok=True)
        Path(p_utf16).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()

