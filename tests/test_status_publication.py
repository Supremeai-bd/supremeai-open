#!/usr/bin/env python3
"""Offline tests for the #1729 gateway root lockdown.

Two layers:
  1. Pure-function contract tests on service/status_publication.py (importable
     without fastapi).
  2. AST-level regression pins on gateway/service/app.py: the public root
     handler must not reference operator-only fields; the operator surface must
     exist behind the strict gate. Pins survive without importing the app.

Run:  python -m unittest tests.test_status_publication -v
(or: python tests/test_status_publication.py)
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "gateway" / "service"))

import status_publication as sp  # noqa: E402

APP_PATH = REPO_ROOT / "gateway" / "service" / "app.py"


class PayloadContract(unittest.TestCase):
    def test_public_root_is_exactly_four_fields(self):
        p = sp.build_public_root_payload(chat_ready=True)
        self.assertEqual(tuple(sorted(p)), tuple(sorted(sp.PUBLIC_ROOT_FIELDS)))
        self.assertEqual(p["status"], "healthy")
        self.assertTrue(p["chat_ready"])

    def test_liveness_has_no_fleet_detail(self):
        p = sp.build_liveness_payload(
            status="healthy",
            service_name="supremeai-api",
            version="2.0.0",
            chat_ready=True,
            timestamp="2026-10-28T00:00:00+00:00",
        )
        self.assertEqual(tuple(sorted(p)), tuple(sorted(sp.LIVENESS_FIELDS)))
        self.assertEqual(p["status"], "healthy")
        self.assertEqual(p["timestamp"], "2026-10-28T00:00:00+00:00")

    def test_no_operator_fields_in_public_payloads(self):
        for payload in (
            sp.build_public_root_payload(),
            sp.build_liveness_payload("healthy", "s", "v", False, "t"),
        ):
            self.assertEqual(sp.assert_no_operator_fields(payload), payload)

    def test_guard_raises_on_any_operator_field(self):
        for field in sp.OPERATOR_ONLY_FIELDS:
            with self.assertRaises(ValueError):
                sp.assert_no_operator_fields({"status": "healthy", field: "x"})

    def test_operator_only_fields_cover_audit_findings(self):
        # The eight sensitive field families the #1729 auditor observed live.
        for field in (
            "total_keys",
            "total_healthy_keys",
            "stealth_priority1_configured",
            "stealth_dns",
            "web_session_status",
            "webhook_scout",
            "telegram_webhook_configured",
            "active_providers",
        ):
            self.assertIn(field, sp.OPERATOR_ONLY_FIELDS)

    def test_liveness_timestamp_is_passthrough(self):
        p = sp.build_liveness_payload("healthy", "s", "v", True, "ts-123")
        self.assertEqual(p["timestamp"], "ts-123")


class AppRegressionPins(unittest.TestCase):
    """AST-level pins on app.py (no fastapi import needed)."""

    @classmethod
    def setUpClass(cls):
        src = APP_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(src)
        cls.handlers = {}
        for node in ast.walk(cls.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cls.handlers.setdefault(node.name, node)

    def _route_decorators(self, fn):
        routes = []
        for dec in fn.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                if dec.func.attr in ("get", "api_route") and dec.args:
                    routes.append(ast.literal_eval(dec.args[0]))
                elif dec.func.attr in ("get", "api_route"):
                    routes.append(dec.func.attr)
        return routes

    def test_public_root_exists_and_is_minimal(self):
        fn = self.handlers.get("public_root")
        self.assertIsNotNone(fn, "public_root handler missing")
        body_src = ast.unparse(fn)
        for field in sp.OPERATOR_ONLY_FIELDS:
            self.assertNotIn(field, body_src, f"operator field {field} in public_root")
        self.assertIn("build_public_root_payload", body_src)
        self.assertIn("assert_no_operator_fields", body_src)

    def test_root_route_no_longer_shares_liveness_handler(self):
        fn = self.handlers.get("public_root")
        routes = self._route_decorators(fn)
        self.assertEqual(routes, ["/"], f"public_root must serve only '/', got {routes}")

    def test_health_check_is_redacted(self):
        fn = self.handlers.get("health_check")
        self.assertIsNotNone(fn)
        body_src = ast.unparse(fn)
        for field in sp.OPERATOR_ONLY_FIELDS:
            self.assertNotIn(field, body_src, f"operator field {field} in health_check")
        self.assertIn("build_liveness_payload", body_src)

    def test_liveness_routes_preserved(self):
        routes = self._route_decorators(self.handlers["health_check"])
        for r in ("/health", "/healthz", "/api/health", "/api/v1/health", "/v1/health"):
            self.assertIn(r, routes, f"liveness route {r} lost")

    def test_internal_status_exists_behind_strict_gate(self):
        fn = self.handlers.get("internal_status")
        self.assertIsNotNone(fn, "internal_status handler missing")
        body_src = ast.unparse(fn)
        self.assertIn("_require_operator_key", body_src)
        self.assertIn("total_keys", body_src)  # full fleet detail lives here now

    def test_scout_status_is_gated(self):
        fn = self.handlers.get("webhook_scout_status")
        self.assertIsNotNone(fn)
        self.assertIn("_require_operator_key", ast.unparse(fn))

    def test_strict_gate_has_no_guest_passthrough(self):
        fn = self.handlers.get("_require_operator_key")
        self.assertIsNotNone(fn, "_require_operator_key missing")
        # Call-level check (docstring may legitimately explain why guest trust is banned):
        calls = {
            ast.unparse(n.func) for n in ast.walk(fn) if isinstance(n, ast.Call)
        }
        self.assertNotIn("_is_guest_request", calls, "operator gate must not call guest pass-through")
        body_src = ast.unparse(fn)
        self.assertIn("verify_key", body_src)
        self.assertIn("SUPREMEAI_API_KEY", body_src)

    def test_guest_mode_still_serves_chat(self):
        # The guest pass-through must remain for the chat surface (scope discipline):
        # _verify_client_auth keeps its _is_guest_request branch.
        fn = self.handlers.get("_verify_client_auth")
        self.assertIsNotNone(fn)
        self.assertIn("_is_guest_request", ast.unparse(fn))


if __name__ == "__main__":
    unittest.main(verbosity=2)
