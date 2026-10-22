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
            "Supremeai-bd/supremeai-agents",
            "Supremeai-bd/supremeai-infrastructure",
            "Supremeai-bd/supremeai-mcp-control-plane",
            "Supremeai-bd/supremeai-sdk",
        }
        self.assertEqual(set(sync_mod.DOMAIN_MAP.keys()), expected_slugs)

    def test_get_auth_token_explicit(self):
        token = sync_mod.get_auth_token("test-token-123")
        self.assertEqual(token, "test-token-123")

    @patch.dict(sync_mod.os.environ, {"BRIDGE_PUSH_TOKEN": "token-from-env"})
    def test_get_auth_token_env(self):
        token = sync_mod.get_auth_token()
        self.assertEqual(token, "token-from-env")


if __name__ == "__main__":
    unittest.main()
