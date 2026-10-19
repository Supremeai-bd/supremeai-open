#!/usr/bin/env python3
"""Offline contract tests for the Universal Federation Dispatch Engine core."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "ci"))
import federation_dispatch as fd


class RegistryTests(unittest.TestCase):
    def test_twelve_satellites(self):
        self.assertEqual(len(fd.SATELLITE_REPOS), 12)

    def test_full_repo_names(self):
        for full in fd.SATELLITE_REPOS.values():
            self.assertTrue(full.startswith("Supremeai-bd/supremeai-"), full)


class RoutingTests(unittest.TestCase):
    def test_gateway_routes_to_api(self):
        self.assertEqual(fd.route_path("gateway/main.py"), "api")

    def test_multi_domain_split(self):
        plan = fd.plan_dispatch(["vscode/a.ts", "skills/b.md", "gateway/c.py"])
        self.assertEqual(len(plan.targets), 3)
        repos = {t.repo for t in plan.targets}
        self.assertIn("Supremeai-bd/supremeai-vscode", repos)
        self.assertIn("Supremeai-bd/supremeai-skills", repos)
        self.assertIn("Supremeai-bd/supremeai-api", repos)

    def test_monorepo_split_out(self):
        plan = fd.plan_dispatch(["vscode/a.ts", "scripts/agents/loop.py"])
        self.assertIn("scripts/agents/loop.py", plan.monorepo_paths)
        self.assertTrue(
            all("scripts/agents/loop.py" not in t.files for t in plan.targets)
        )

    def test_unrouted_quarantined(self):
        plan = fd.plan_dispatch(["README.md"])
        self.assertTrue(any(p == "README.md" for p, _ in plan.unrouted))
        self.assertEqual(plan.targets, [])

    def test_fail_closed_invalid(self):
        with self.assertRaises(fd.DispatchError):
            fd.plan_dispatch("not-a-list")
        with self.assertRaises(fd.DispatchError):
            fd.plan_dispatch(["", "   "])


class DeterminismTests(unittest.TestCase):
    def test_sorted_targets(self):
        plan = fd.plan_dispatch(["skills/z.md", "vscode/a.ts", "browser/b.ts"])
        self.assertEqual(
            [t.satellite for t in plan.targets],
            sorted(t.satellite for t in plan.targets),
        )

    def test_dedup_within_target(self):
        plan = fd.plan_dispatch(["vscode/a.ts", "vscode/a.ts", "vscode/b.ts"])
        vt = next(t for t in plan.targets if t.satellite == "vscode")
        self.assertEqual(vt.files, ("vscode/a.ts", "vscode/b.ts"))

    def test_json_serializable(self):
        plan = fd.plan_dispatch(["vscode/a.ts", "skills/b.md"])
        data = plan.to_dict()
        self.assertEqual(json.loads(json.dumps(data)), data)


class SSOTTests(unittest.TestCase):
    def test_matrix_reused_from_batcher(self):
        import hourly_satellite_batcher as hb

        for p in (
            "vscode/x.ts",
            "gateway/x.py",
            "infrastructure/mcp-control-plane/y.ts",
            "scripts/agents/loop.py",
            "README.md",
        ):
            self.assertEqual(fd.route_path(p), hb.route_path(p))


class TraceabilityTests(unittest.TestCase):
    def test_source_sha_propagated(self):
        plan = fd.plan_dispatch(["vscode/a.ts"], source_sha="b" * 40)
        self.assertEqual(plan.source_sha, "b" * 40)
        self.assertEqual(plan.to_dict()["source_sha"], "b" * 40)

    def test_render_workflow_yaml_parses(self):
        import yaml

        parsed = yaml.safe_load(fd.render_workflow_yaml())
        self.assertIsInstance(parsed, dict)
        self.assertIn("jobs", parsed)
