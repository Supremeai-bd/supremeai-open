#!/usr/bin/env python3
"""Offline contract tests for the unified gateway shield (#469).

Rules 18-22 verification, tier 3 (offline unit tests): failover chain
transitions, SSOT key authentication contract, quota admission, usage
attribution, and the Rule 19 no-provider-key-material invariant.
Also validates api-schemas/gateway.openapi.yaml structurally.

Pure stdlib. Run: python3 -m unittest test_gateway_shield -v
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gateway"))

import gateway_shield_reference as gw

ENV = {gw.SSOT_KEY_NAME: "ssot-key-0123456789abcdef"}  # gitleaks:allow


class Rule18Surface(unittest.TestCase):
    def test_01_openai_compatible_surface(self):
        self.assertIn("/v1/models", gw.ROUTES)
        self.assertIn("/v1/chat/completions", gw.ROUTES)

    def test_02_schema_contract_structurally_valid(self):
        raw = (ROOT / "api-schemas" / "gateway.openapi.yaml").read_text(
            encoding="utf-8"
        )
        # The mirror is a byte-parity copy of the api SSOT (#648) and carries
        # a comment header; the contract is the first declaration line, not
        # byte offset zero.
        decls = [
            line.strip()
            for line in raw.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertTrue(decls, "schema carries no declaration lines")
        self.assertEqual(decls[0], "openapi: 3.1.0")
        self.assertIn("/v1/chat/completions:", raw)
        self.assertIn("/v1/models:", raw)
        self.assertIn("X-SupremeAI-Key", raw)
        # SSOT auth scheme is the SupremeAIKey apiKey header (#648 byte-parity);
        # the pre-sync bearerAuth name no longer exists in the contract.
        self.assertIn("SupremeAIKey", raw)
        self.assertIn("type: apiKey", raw)


class Rule19VaultOnlyKeys(unittest.TestCase):
    def test_03_module_never_reads_provider_credentials(self):
        src = (ROOT / "gateway" / "gateway_shield_reference.py").read_text(
            encoding="utf-8"
        )
        for name in gw.PROVIDER_ENV_NAMES:
            self.assertNotIn(f'getenv("{name}"', src)
            self.assertNotIn(f'environ["{name}"]', src)
            self.assertNotIn(f'environ.get("{name}"', src)
            # Provider env names may appear ONLY in the declaration set.
            decl_start = src.index("PROVIDER_ENV_NAMES")
            decl_end = src.index("})", decl_start)
            occurrences = [i for i in range(len(src)) if src.startswith(name, i)]
            outside = [i for i in occurrences if not (decl_start <= i < decl_end)]
            self.assertEqual(
                outside, [], f"{name} referenced outside declaration: {outside}"
            )

    def test_04_no_provider_key_material_in_schema(self):
        raw = (ROOT / "api-schemas" / "gateway.openapi.yaml").read_text(
            encoding="utf-8"
        )
        self.assertTrue(gw.no_provider_key_material(raw))

    def test_05_provider_credentials_never_accepted_by_auth(self):
        for bogus in (
            "gsk_groq_material_012345",
            "aiza=gemini_material_12",
            "sk-or-xx",
            "sk-ant-yy",
        ):
            with self.assertRaises(gw.GatewayError) as cm:
                gw.authenticate({"Authorization": f"Bearer {bogus}"}, ENV)
            self.assertEqual(cm.exception.code, "provider_key_rejected")


class Rule21SsotAuth(unittest.TestCase):
    def test_06_bearer_ssot_key_accepted(self):
        self.assertTrue(
            gw.authenticate({"Authorization": "Bearer ssot-key-0123456789abcdef"}, ENV)
        )

    def test_07_header_ssot_key_accepted(self):
        self.assertTrue(
            gw.authenticate({gw.SSOT_HEADER: "ssot-key-0123456789abcdef"}, ENV)
        )

    def test_08_missing_credential_401(self):
        with self.assertRaises(gw.GatewayError) as cm:
            gw.authenticate({}, ENV)
        self.assertEqual(
            (cm.exception.status, cm.exception.code), (401, "missing_credential")
        )

    def test_09_wrong_key_401(self):
        with self.assertRaises(gw.GatewayError) as cm:
            gw.authenticate({gw.SSOT_HEADER: "wrong-key-0123456789ab"}, ENV)
        self.assertEqual(
            (cm.exception.status, cm.exception.code), (401, "invalid_credential")
        )

    def test_10_unconfigured_gateway_fails_closed_500(self):
        with self.assertRaises(gw.GatewayError) as cm:
            gw.authenticate({}, {})
        self.assertEqual(cm.exception.status, 500)


class Rule20FailoverChain(unittest.TestCase):
    def test_11_full_chain_walk(self):
        self.assertEqual(gw.next_target(gw.DEFAULT_CHAIN, ()), "groq")
        self.assertEqual(gw.next_target(gw.DEFAULT_CHAIN, ("groq",)), "gemini")
        self.assertEqual(
            gw.next_target(gw.DEFAULT_CHAIN, ("groq", "gemini")), "fallback"
        )

    def test_12_chain_exhaustion_503(self):
        d = gw.failover_decision(gw.DEFAULT_CHAIN, gw.DEFAULT_CHAIN)
        self.assertTrue(d["exhausted"])
        self.assertEqual(d["status"], 503)

    def test_13_decision_record_shape(self):
        d = gw.failover_decision(gw.DEFAULT_CHAIN, ("groq", "gemini"))
        self.assertEqual(d["target"], "fallback")
        self.assertEqual(d["served_by_header"], "fallback")
        self.assertEqual(d["chain"], ["groq", "gemini", "fallback"])

    def test_14_empty_chain_fail_closed(self):
        with self.assertRaises(gw.GatewayError):
            gw.next_target((), ())


class Rule22QuotaAndAttribution(unittest.TestCase):
    def test_15_rps_limit_enforced(self):
        tenant = {"tenant": "acme", "rps": 2, "rpm": 100}
        counters = {}
        self.assertTrue(gw.quota_check(tenant, counters, 1.0)["allowed"])
        self.assertTrue(gw.quota_check(tenant, counters, 1.1)["allowed"])
        self.assertFalse(gw.quota_check(tenant, counters, 1.2)["allowed"])

    def test_16_rpm_limit_enforced_then_window_prunes(self):
        tenant = {"tenant": "acme", "rps": 100, "rpm": 2}
        counters = {}
        self.assertTrue(gw.quota_check(tenant, counters, 1.0)["allowed"])
        self.assertTrue(gw.quota_check(tenant, counters, 1.1)["allowed"])
        self.assertFalse(gw.quota_check(tenant, counters, 1.2)["allowed"])
        self.assertTrue(gw.quota_check(tenant, counters, 120.0)["allowed"])

    def test_17_bad_tenant_config_fail_closed(self):
        with self.assertRaises(gw.GatewayError):
            gw.quota_check({"tenant": "x"}, {}, 1.0)

    def test_18_attribution_event_shape_no_secrets(self):
        ev = gw.attribution_event("acme", "llm-large", "groq", 128, now=None)
        self.assertEqual(set(ev), {"tenant", "model", "provider", "total_tokens", "ts"})
        blob = json.dumps(ev)
        self.assertNotIn("ssot-key", blob)

    def test_19_negative_tokens_fail_closed(self):
        with self.assertRaises(gw.GatewayError):
            gw.attribution_event("acme", "m", "groq", -1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
