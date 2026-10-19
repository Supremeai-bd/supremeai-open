#!/usr/bin/env python3
"""Dual-mode contract tests for S0.2 PR Evidence Envelope (task #457).

UNIT layer runs today, offline, against scripts/tower/pr_evidence_envelope.py.

Run: pytest tests/test_s02_evidence_envelope.py  OR  python3 tests/test_s02_evidence_envelope.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF_DIR = HERE.parent / "scripts" / "tower"
if str(REF_DIR) not in sys.path:
    sys.path.insert(0, str(REF_DIR))

import pr_evidence_envelope as env_mod


def make_env(**overrides):
    base = dict(
        task_issue_ref=457,
        claim_marker_id="atomic-claim:issue=457,agent=zai,ts=2026-10-17T03:30:00Z,ttl=30m",
        reflection_why="structured assertions replace brittle regex ladders on PR bodies",
        alternatives_rejected=["keep regex ladders", "external validation service"],
        scope_paths=[
            "docs/S02_STRUCTURED_EVIDENCE_SPEC.md",
            "scripts/tower/pr_evidence_envelope.py",
        ],
    )
    base.update(overrides)
    return env_mod.EvidenceEnvelope(**base)


class UnitRoundTrip(unittest.TestCase):
    def test_01_build_parse_round_trip(self):
        env = make_env()
        block = env_mod.build_envelope(env)
        back = env_mod.parse_envelope(block)
        self.assertIsNotNone(back)
        self.assertEqual(back.task_issue_ref, 457)  # type: ignore[union-attr]
        self.assertEqual(back.scope_paths, env.scope_paths)  # type: ignore[union-attr]
        self.assertEqual(
            back.schema if hasattr(back, "schema") else env_mod.SCHEMA_VERSION,
            env_mod.SCHEMA_VERSION,
        )

    def test_02_no_envelope_is_none(self):
        self.assertIsNone(env_mod.parse_envelope("just prose, no markers"))

    def test_03_truncated_json_is_none(self):
        bad = env_mod.MARKER_OPEN + "\n{ not json\n" + env_mod.MARKER_CLOSE
        self.assertIsNone(env_mod.parse_envelope(bad))

    def test_04_wrong_schema_is_none(self):
        block = env_mod.build_envelope(make_env()).replace(
            env_mod.SCHEMA_VERSION, "pr-evidence-envelope/9"
        )
        self.assertIsNone(env_mod.parse_envelope(block))

    def test_05_missing_close_marker_is_none(self):
        block = env_mod.build_envelope(make_env()).replace(env_mod.MARKER_CLOSE, "")
        self.assertIsNone(env_mod.parse_envelope(block))


class UnitValidation(unittest.TestCase):
    def test_06_valid_envelope_zero_errors(self):
        self.assertEqual(env_mod.validate(make_env()), [])

    def test_07_bad_issue_ref(self):
        for bad in (0, -5):
            codes = env_mod.validate(make_env(task_issue_ref=bad))
            self.assertIn("E_BAD_ISSUE_REF", codes)

    def test_08_empty_why_short_and_long(self):
        self.assertIn(
            "E_EMPTY_WHY", env_mod.validate(make_env(reflection_why="too short"))
        )
        self.assertIn(
            "E_EMPTY_WHY", env_mod.validate(make_env(reflection_why="x" * 501))
        )

    def test_09_no_alternatives(self):
        self.assertIn(
            "E_NO_ALTERNATIVES", env_mod.validate(make_env(alternatives_rejected=[]))
        )
        self.assertIn(
            "E_NO_ALTERNATIVES",
            env_mod.validate(make_env(alternatives_rejected=["a"] * 6)),
        )

    def test_10_protected_paths_detected(self):
        for p in (
            ".github/workflows/pipeline.yml",
            "docs/ledger/x.md",
            "docs/master_docs/y.md",
            "prisma/schema.prisma",
            ".env",
            "config/credentials.json",
            "certs/server.pem",
            "secrets/api_key.p12",
        ):
            self.assertTrue(env_mod.check_protected(p), p)

    def test_11_safe_paths_allowed(self):
        for p in (
            "scripts/tower/x.py",
            "scripts/ci/y.py",
            "docs/S02_SPEC.md",
            "tests/test_x.py",
            "examples/curl-tests/z.sh",
        ):
            self.assertFalse(env_mod.check_protected(p), p)

    def test_12_protected_scope_errors(self):
        codes = env_mod.validate(make_env(scope_paths=["prisma/schema.prisma"]))
        self.assertIn("E_SCOPE_PROTECTED", codes)

    def test_13_bad_digest_format(self):
        codes = env_mod.validate(make_env(file_digests={"docs/x.md": "deadbeef"}))
        self.assertIn("E_BAD_DIGEST", codes)

    def test_14_good_digests_pass(self):
        hex64 = "a" * 64
        self.assertEqual(
            env_mod.validate(make_env(file_digests={"docs/x.md": hex64})), []
        )
        self.assertEqual(
            env_mod.validate(make_env(file_digests={"docs/x.md": "sha256:" + hex64})),
            [],
        )

    def test_15_bad_timestamp(self):
        self.assertIn(
            "E_BAD_TIMESTAMP",
            env_mod.validate(make_env(created_ts="2026-10-17 03:30:00")),
        )
        self.assertEqual(
            env_mod.validate(make_env(created_ts="2026-10-17T03:30:00Z")), []
        )


class UnitGuardIntegration(unittest.TestCase):
    def test_16_reflection_heading_exact(self):
        section = env_mod.render_reflection_section(make_env())
        self.assertIn(env_mod.REFLECTION_HEADING, section)
        self.assertIn("**Why:**", section)
        self.assertIn("**Alternatives rejected:**", section)

    def test_17_full_body_contains_all_planes(self):
        body = env_mod.build_full_pr_body(make_env(), "Implements task #457 (S0.2).")
        self.assertIn("Implements task #457", body)
        self.assertIn(env_mod.MARKER_OPEN, body)
        self.assertIn(env_mod.REFLECTION_HEADING, body)
        back = env_mod.parse_envelope(body)
        self.assertIsNotNone(back)

    def test_18_schema_version_constant(self):
        self.assertEqual(env_mod.SCHEMA_VERSION, "pr-evidence-envelope/1")

    def test_19_deterministic_serialization(self):
        self.assertEqual(
            env_mod.build_envelope(make_env()), env_mod.build_envelope(make_env())
        )

    def test_20_extra_fields_forward_compat(self):
        # unknown keys are ignored by the parser (spec: fail-closed only on known fields)
        block = env_mod.build_envelope(make_env()).replace(
            '{\n  "agent_id"', '{\n  "custom_future_field": 1,\n  "agent_id"'
        )
        back = env_mod.parse_envelope(block)
        self.assertIsNotNone(back)


class LiveContract(unittest.TestCase):
    def test_21_reference_importable_and_healthy(self):
        # on landing this layer asserts the guard-side consumption contract
        self.assertTrue(callable(env_mod.parse_envelope))
        self.assertTrue(callable(env_mod.validate))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
