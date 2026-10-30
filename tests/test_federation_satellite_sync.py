import unittest
from unittest.mock import patch

from scripts.ci import federation_satellite_sync as sync_mod


class TestFederationSatelliteSync(unittest.TestCase):
    def test_self_test(self):
        self.assertTrue(sync_mod.self_test())

    def test_domain_map_coverage(self):
        expected_slugs = {
            "Supremeai-bd/supremeai-studio",
            "Supremeai-bd/supremeai-core",
            "Supremeai-bd/supremeai-api",
            "Supremeai-bd/supremeai-browser",
            "Supremeai-bd/supremeai-vscode",
        }
        self.assertEqual(set(sync_mod.DOMAIN_MAP.keys()), expected_slugs)

    def test_get_auth_token_explicit(self):
        token = sync_mod.get_auth_token("test-token-123")
        self.assertEqual(token, "test-token-123")

    @patch.dict(sync_mod.os.environ, {"BRIDGE_PUSH_TOKEN": "token-from-env"})
    def test_get_auth_token_env(self):
        token = sync_mod.get_auth_token()
        self.assertEqual(token, "token-from-env")

    @patch("subprocess.run")
    def test_detect_changed_targets(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "studio/src/App.tsx\ngateway/server.py\n"
        targets, umbrella = sync_mod.detect_changed_targets(sync_mod.Path("/tmp"))
        self.assertIn("Supremeai-bd/supremeai-studio", targets)
        self.assertIn("Supremeai-bd/supremeai-api", targets)
        self.assertTrue(umbrella)

    @patch("subprocess.run")
    def test_detect_changed_targets_empty(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "\n"
        targets, umbrella = sync_mod.detect_changed_targets(sync_mod.Path("/tmp"))
        self.assertEqual(targets, [])
        self.assertFalse(umbrella)


    def test_deploy_targets_omits_skip_ci(self):
        self.assertIn("Supremeai-bd/supremeai-studio", sync_mod.DEPLOY_TARGETS)

    # --- (#1676 root cause) domain self-shadow guard -------------------

    def test_self_shadow_cleanup_removes_nested_domain_copy(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            satellite = sync_mod.Path(tmp) / "sat"
            mirror = sync_mod.Path(tmp) / "mirror"
            (satellite / "studio" / "src" / "utils").mkdir(parents=True)
            (satellite / "studio" / "package.json").write_text("{}")
            (satellite / "studio" / "src" / "utils" / "api.ts").write_text("x")
            (satellite / "src" / "utils").mkdir(parents=True)
            (satellite / "src" / "utils" / "api.ts").write_text("root")
            (satellite / "infrastructure" / "proxy").mkdir(parents=True)
            (satellite / "infrastructure" / "proxy" / "wrangler.toml").write_text("k")
            mirror.mkdir()
            removed = sync_mod.prune_domain_self_shadows(satellite, "studio", mirror)
            self.assertIn("studio/package.json", removed)
            self.assertIn("studio/src/utils/api.ts", removed)
            self.assertFalse((satellite / "studio").exists())
            # canonical root files and legitimate satellite-only dirs survive
            self.assertTrue((satellite / "src" / "utils" / "api.ts").exists())
            self.assertTrue((satellite / "infrastructure" / "proxy" / "wrangler.toml").exists())

    def test_self_shadow_noop_when_absent(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            satellite = sync_mod.Path(tmp) / "sat"
            mirror = sync_mod.Path(tmp) / "mirror"
            satellite.mkdir()
            mirror.mkdir()
            self.assertEqual(
                sync_mod.prune_domain_self_shadows(satellite, "studio", mirror), []
            )

    def test_self_shadow_start_gate_fails_closed_on_mirror_contamination(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            satellite = sync_mod.Path(tmp) / "sat"
            mirror = sync_mod.Path(tmp) / "mirror"
            satellite.mkdir()
            (mirror / "studio").mkdir(parents=True)
            with self.assertRaises(RuntimeError):
                sync_mod.prune_domain_self_shadows(satellite, "studio", mirror)

    def test_self_shadow_guard_covers_all_domain_map_entries(self):
        # The mirror itself never carries a same-name nested dir (verified
        # live 2026-10-30: studio/core/gateway/browser/vscode all 0), so the
        # fail-closed start-gate must be safe for every satellite.
        for source_dir in sync_mod.DOMAIN_MAP.values():
            self.assertEqual(
                sync_mod.prune_domain_self_shadows(
                    sync_mod.Path("/nonexistent-sat"), source_dir, sync_mod.Path("/nonexistent-mirror")
                ),
                [],
            )

    # --- (#3441 root cause) package-shadow refresh + fail-loud sync policy ---

    def test_package_shadow_policy_spares_core_shadow(self):
        # supremeai-core's own CI imports `core.*` from the nested copy; the
        # refresh_package policy must leave it in place for the caller to
        # refresh, never delete it (deleting it ModuleNotFoundErrors the
        # satellite's test suite — live evidence Run 41072422845).
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            satellite = sync_mod.Path(tmp) / "sat"
            mirror = sync_mod.Path(tmp) / "mirror"
            (satellite / "core" / "utils").mkdir(parents=True)
            (satellite / "core" / "stale_symbol.py").write_text("old")
            mirror.mkdir()
            removed = sync_mod.prune_domain_self_shadows(
                satellite, "core", mirror, policy="refresh_package"
            )
            self.assertEqual(removed, [])
            self.assertTrue((satellite / "core" / "stale_symbol.py").exists())

    def test_refresh_domain_package_builds_fresh_pruned_copy(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            satellite = sync_mod.Path(tmp) / "sat"
            mirror = sync_mod.Path(tmp) / "mirror"
            (mirror / "monitoring").mkdir(parents=True)
            (mirror / "dag_planner.py").write_text("fresh")
            (mirror / "monitoring" / "logging_config.py").write_text("fresh-log")
            # stale shadow: has a file the mirror dropped, lacks both fresh files
            (satellite / "core").mkdir(parents=True)
            (satellite / "core" / "stale_only.py").write_text("stale")
            (satellite / "core" / "dag_planner.py").write_text("stale")
            count = sync_mod.refresh_domain_package(mirror, satellite, "core")
            self.assertEqual(count, 2)
            self.assertEqual(
                (satellite / "core" / "dag_planner.py").read_text(), "fresh"
            )
            self.assertEqual(
                (satellite / "core" / "monitoring" / "logging_config.py").read_text(),
                "fresh-log",
            )
            self.assertFalse(
                (satellite / "core" / "stale_only.py").exists(),
                "Stale shadow-only file must be pruned by the sync-managed refresh",
            )

    def test_refresh_package_start_gate_still_raises(self):
        # Mirror contamination is fatal under BOTH policies: a mirror carrying
        # a top-level <domain>/ dir must never be synced (fail-closed #1676).
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            satellite = sync_mod.Path(tmp) / "sat"
            mirror = sync_mod.Path(tmp) / "mirror"
            satellite.mkdir()
            (mirror / "core").mkdir(parents=True)
            with self.assertRaises(RuntimeError):
                sync_mod.prune_domain_self_shadows(
                    satellite, "core", mirror, policy="refresh_package"
                )

    def test_policy_and_cloak_targets_are_federation_members(self):
        # A policy naming a non-federation repo silently applies to nothing
        # (dual-SSOT drift class) — both sets must stay inside DOMAIN_MAP.
        self.assertTrue(set(sync_mod.PACKAGE_SHADOW_REFRESH_TARGETS) <= set(sync_mod.DOMAIN_MAP))
        self.assertTrue(set(sync_mod.SATELLITE_CLOAK_ALLOWLIST) <= set(sync_mod.DOMAIN_MAP))
        self.assertIn("Supremeai-bd/supremeai-core", sync_mod.PACKAGE_SHADOW_REFRESH_TARGETS)

    def test_cloak_allowlist_default_is_empty(self):
        # Fail-closed default: nothing may silently degrade until an admin
        # lands a documented cloaking receipt adding it here (#3441).
        self.assertEqual(sync_mod.SATELLITE_CLOAK_ALLOWLIST, frozenset())

    @patch("subprocess.check_output")
    @patch("subprocess.check_call")
    @patch("subprocess.run")
    def test_permission_denied_push_fails_loudly(self, mock_run, mock_check_call, mock_check_output):
        # (#3441 root cause) A permission-class push rejection on a target
        # whose domain changed must NOT degrade to a green no-op — the old
        # silent-True left supremeai-core stale for 3 nights (Run 41072422845).
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = sync_mod.Path(tmp)
            (repo_root / "core").mkdir()
            (repo_root / "core" / "keep.py").write_text("x=1")
            clone_ok = sync_mod.subprocess.CompletedProcess([], 0, stdout="", stderr="")
            commit_ok = sync_mod.subprocess.CompletedProcess([], 0, stdout="", stderr="")
            push_denied = sync_mod.subprocess.CompletedProcess(
                [], 1, stdout="", stderr="remote: Permission to Supremeai-bd/supremeai-core.git denied to user."
            )
            mock_run.side_effect = [clone_ok, commit_ok, push_denied]
            mock_check_output.return_value = "M  keep.py\n"
            ok = sync_mod.sync_satellite(
                "Supremeai-bd/supremeai-core", "core", repo_root, "token", "msg"
            )
            self.assertFalse(
                ok, "Permission-denied push must fail loudly, never return True"
            )

    @patch.object(
        sync_mod,
        "SATELLITE_CLOAK_ALLOWLIST",
        frozenset({"Supremeai-bd/supremeai-core"}),
    )
    @patch("subprocess.check_output")
    @patch("subprocess.check_call")
    @patch("subprocess.run")
    def test_allowlisted_cloak_still_degrades_gracefully(self, mock_run, mock_check_call, mock_check_output):
        # The allowlist is the ONLY sanctioned escape hatch: a deliberately
        # cloaked satellite keeps the old graceful-skip behavior.
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            repo_root = sync_mod.Path(tmp)
            (repo_root / "core").mkdir()
            (repo_root / "core" / "keep.py").write_text("x=1")
            clone_ok = sync_mod.subprocess.CompletedProcess([], 0, stdout="", stderr="")
            commit_ok = sync_mod.subprocess.CompletedProcess([], 0, stdout="", stderr="")
            push_denied = sync_mod.subprocess.CompletedProcess(
                [], 1, stdout="", stderr="remote: Permission to Supremeai-bd/supremeai-core.git denied to user."
            )
            mock_run.side_effect = [clone_ok, commit_ok, push_denied]
            mock_check_output.return_value = "M  keep.py\n"
            ok = sync_mod.sync_satellite(
                "Supremeai-bd/supremeai-core", "core", repo_root, "token", "msg"
            )
            self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
