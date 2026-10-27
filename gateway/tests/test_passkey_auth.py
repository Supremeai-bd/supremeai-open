"""
gateway/tests/test_passkey_auth.py — Hermetic Tests for Native WebAuthn/Passkey Engine.
"""
import base64
import json
import unittest
import uuid
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient

from gateway.service.app import app
from gateway.service.storage import (
    get_user_passkey,
    list_user_passkeys,
    revoke_user_passkey,
    save_user_passkey,
)


class TestPasskeyAuth(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_passkey_register_options(self):
        resp = self.client.post(
            "/api/auth/passkey/register/options",
            json={
                "user_id": "usr-test-123",
                "email": "test@supremeai.com",
                "role": "user",
                "display_name": "Test User",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("challenge", data)
        self.assertIn("rp", data)
        self.assertIn("user", data)
        self.assertEqual(data["user"]["name"], "test@supremeai.com")

    def test_passkey_login_options(self):
        resp = self.client.post(
            "/api/auth/passkey/login/options",
            json={"role": "user"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("challenge", data)
        self.assertEqual(data["userVerification"], "required")

    def test_passkey_device_storage_lifecycle(self):
        # Hermetic credential id: the shared /tmp gateway_state.db outlives the pytest
        # process, and save_user_passkey's upsert does not reset `revoked` — a constant
        # id revoked by the previous run stayed revoked=1 and step 2's `revoked = 0`
        # lookup returned None (cross-run pollution, class F-K). Unique id per run.
        run_nonce = uuid.uuid4().hex[:12]
        cred_id = "cred-mock-test-" + base64.urlsafe_b64encode(
            f"random-key-{run_nonce}".encode()
        ).decode().rstrip("=")
        user_id = "usr-tester-99"

        # 1. Save
        saved = save_user_passkey(
            credential_id=cred_id,
            user_id=user_id,
            role="user",
            public_key_spki="mock-spki",
            device_name="MacBook Touch ID",
        )
        self.assertEqual(saved["credential_id"], cred_id)

        # 2. Get
        fetched = get_user_passkey(cred_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["device_name"], "MacBook Touch ID")

        # 3. List
        devices = list_user_passkeys(user_id)
        self.assertTrue(any(d["credential_id"] == cred_id for d in devices))

        # 4. Revoke
        revoked = revoke_user_passkey(cred_id, user_id)
        self.assertTrue(revoked)
        self.assertIsNone(get_user_passkey(cred_id))


if __name__ == "__main__":
    unittest.main()
