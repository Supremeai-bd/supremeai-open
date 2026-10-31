"""
gateway/tests/test_storage_and_endpoints.py — Offline tests for:
1. Conversation-ID carry-over and history persistence.
2. Server-side LiveLogs ring buffer and admin endpoints.
3. User preferences and Tool-card removal persistence.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

BASE = os.path.dirname(os.path.abspath(__file__))
SAT = os.path.abspath(os.path.join(BASE, ".."))
if SAT not in sys.path:
    sys.path.insert(0, SAT)

try:
    from service import storage
    from service.app import app, log_ring_buffer
except ImportError:
    from gateway.service import storage
    from gateway.service.app import app, log_ring_buffer

from starlette.testclient import TestClient


class TestStorageAndEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        storage.init_db()
        cls.client = TestClient(app)

    def test_01_conversation_persistence(self):
        conv_id = "test-conv-001"
        user_id = "usr-test-123"

        # Save conversation
        c = storage.save_conversation(conv_id, user_id=user_id, title="Test Session")
        self.assertEqual(c["id"], conv_id)
        self.assertEqual(c["title"], "Test Session")

        # Add user message
        m1 = storage.add_message(conv_id, "user", "Hello AI", user_id=user_id)
        self.assertEqual(m1["role"], "user")
        self.assertEqual(m1["content"], "Hello AI")

        # Add assistant message
        m2 = storage.add_message(conv_id, "assistant", "Hello human!", extra={"model": "w.ge"}, user_id=user_id)
        self.assertEqual(m2["role"], "assistant")

        # Retrieve conversation
        conv = storage.get_conversation(conv_id, user_id=user_id)
        self.assertIsNotNone(conv)
        self.assertEqual(conv["message_count"], 2)
        self.assertEqual(len(conv["messages"]), 2)
        self.assertEqual(conv["messages"][0]["content"], "Hello AI")
        self.assertEqual(conv["messages"][1]["content"], "Hello human!")

        # List conversations
        convs = storage.list_conversations(user_id=user_id)
        self.assertGreaterEqual(len(convs), 1)
        found = [x for x in convs if x["id"] == conv_id]
        self.assertTrue(bool(found))
        self.assertEqual(found[0]["message_count"], 2)

        # Delete conversation
        ok = storage.delete_conversation(conv_id, user_id=user_id)
        self.assertTrue(ok)
        self.assertIsNone(storage.get_conversation(conv_id, user_id=user_id))

    def test_02_user_preferences_and_tool_cards(self):
        user_id = f"usr-pref-test-{time.time()}"

        # Initial preferences should have default structure
        p0 = storage.get_user_preferences(user_id)
        self.assertEqual(p0["preferences"]["hidden_tool_cards"], [])

        # Hide a tool card via action
        storage.save_user_preferences(user_id, {"action": "hide_tool", "tool_id": "card-browser"})
        p1 = storage.get_user_preferences(user_id)
        self.assertIn("card-browser", p1["preferences"]["hidden_tool_cards"])

        # Hide another tool card directly in list
        storage.save_user_preferences(user_id, {"hidden_tool_cards": ["card-browser", "card-deployer"], "theme": "cosmic-dark"})
        p2 = storage.get_user_preferences(user_id)
        self.assertEqual(p2["preferences"]["hidden_tool_cards"], ["card-browser", "card-deployer"])
        self.assertEqual(p2["preferences"]["theme"], "cosmic-dark")

        # Unhide a tool card
        storage.save_user_preferences(user_id, {"action": "unhide_tool", "tool_id": "card-browser"})
        p3 = storage.get_user_preferences(user_id)
        self.assertNotIn("card-browser", p3["preferences"]["hidden_tool_cards"])
        self.assertIn("card-deployer", p3["preferences"]["hidden_tool_cards"])

    def test_03_livelogs_ring_buffer(self):
        logger = logging.getLogger("supremeai.gateway")
        logger.setLevel(logging.INFO)
        test_msg = "LiveLogs Verification Log Entry #42"
        logger.info(test_msg)

        logs = log_ring_buffer.get_logs(limit=20, search="LiveLogs Verification")
        self.assertGreaterEqual(len(logs), 1)
        self.assertEqual(logs[-1]["level"], "INFO")
        self.assertIn(test_msg, logs[-1]["message"])

    def test_04_conversation_endpoints(self):
        headers = {"X-Guest-Mode": "true", "X-User-Id": "usr-endpoint-test"}

        # Create conversation
        r_create = self.client.post("/api/v1/chat/conversations", json={"title": "Dashboard Session"}, headers=headers)
        self.assertEqual(r_create.status_code, 200)
        c_id = r_create.json()["conversation"]["id"]

        # List conversations
        r_list = self.client.get("/api/v1/chat/conversations", headers=headers)
        self.assertEqual(r_list.status_code, 200)
        self.assertIn("conversations", r_list.json())

        # Get conversation details
        r_get = self.client.get(f"/api/v1/chat/conversations/{c_id}", headers=headers)
        self.assertEqual(r_get.status_code, 200)
        self.assertEqual(r_get.json()["id"], c_id)

        # Delete conversation
        r_del = self.client.delete(f"/api/v1/chat/conversations/{c_id}", headers=headers)
        self.assertEqual(r_del.status_code, 200)
        self.assertEqual(r_del.json()["status"], "deleted")

    def test_05_admin_livelogs_endpoint(self):
        headers = {"X-Guest-Mode": "true"}
        r = self.client.get("/admin-api/logs?limit=10", headers=headers)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["status"], "ok")
        self.assertIsInstance(data["logs"], list)

    def test_06_preferences_and_tool_card_endpoints(self):
        headers = {"X-Guest-Mode": "true", "X-User-Id": "usr-endpoint-pref"}

        # Get preferences
        r_get = self.client.get("/api/v1/user/preferences", headers=headers)
        self.assertEqual(r_get.status_code, 200)
        self.assertIn("preferences", r_get.json())

        # Hide tool card
        r_hide = self.client.delete("/api/v1/user/preferences/tool-card/card-voice", headers=headers)
        self.assertEqual(r_hide.status_code, 200)
        self.assertEqual(r_hide.json()["status"], "ok")

        # Verify hidden in GET
        r_check = self.client.get("/api/v1/user/preferences", headers=headers)
        self.assertIn("card-voice", r_check.json()["preferences"]["hidden_tool_cards"])

        # Restore tool card
        r_restore = self.client.post("/api/v1/user/preferences/tool-card/card-voice/restore", headers=headers)
        self.assertEqual(r_restore.status_code, 200)
        self.assertEqual(r_restore.json()["action"], "restored")

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=MagicMock(status_code=200))
    def test_07_health_aggregation(self, _mock_get):
        # ROOT-CAUSE FIX (2026-10-31, GLM Agent 28, Job 486832): আগের সংস্করণ
        # লাইভ Render fleet-কে সত্যিকার HTTP probe করত (api-ulw0/mcp-tower,
        # timeout=4s)। Render free-tier cold-start/spin-down হলে probe 503 বা
        # timeout → status "degraded" → টেস্ট লাল। অর্থাৎ red census নির্ভর করত
        # বাইরের fleet-এর মুডের উপর — flaky red (এই চক্রে 3F/2407P সেনসাসে
        # প্রমাণিত: একবার লাল, isolation-এ সবুজ)। এই টেস্টের দায়িত্ব fleet-এর
        # স্বাস্থ্য নয়, ENDPOINT CONTRACT: probe 200 → "healthy"; probe ব্যর্থ →
        # "degraded" (07b); configure না থাকলে "unknown" (2026-10-24 honesty
        # fix)। তাই network deterministic mock — repo idiom:
        # gateway/tests/test_model_cascades.py-এর class-level httpx patch।
        # TestClient নিজে sync httpx.Client ব্যবহার করে, তাই AsyncClient.get
        # patch শুধু অ্যাপের outbound probe-এ হিট করে — request path অক্ষত।
        r = self.client.get("/api/health-aggregation")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("checks", data)
        self.assertIn("api", data["checks"])
        self.assertEqual(data["checks"]["api"]["status"], "healthy")
        self.assertIn("scraper", data["checks"])
        self.assertIn("tower", data["checks"])
        self.assertIn("primary", data["checks"])
        self.assertIn("worker", data["checks"])

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=ConnectionError("mock fleet down"))
    def test_07b_health_aggregation_honest_degradation(self, _mock_get):
        # Honest-degradation contract pin (07-এর মিরর): probe ব্যর্থ হলে
        # "degraded" — কখনো ভুয়া সবুজ নয়; configure না-থাকা node সৎভাবে
        # "unknown"। live network ছাড়াই 2026-10-24 honesty fix-এর চুক্তি
        # এখন deterministicভাবে পিন করা।
        r = self.client.get("/api/health-aggregation")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["checks"]["api"]["status"], "degraded")
        self.assertEqual(data["checks"]["tower"]["status"], "degraded")
        self.assertEqual(data["checks"]["scraper"]["status"], "unknown")
        self.assertEqual(data["checks"]["primary"]["status"], "unknown")
        self.assertEqual(data["checks"]["worker"]["status"], "unknown")

    @patch.dict(os.environ, {"SUPREMEAI_ADMIN_PASSWORD": "password123"})
    def test_08_auth_login_and_register(self):
        # 1. Login with username field (what studio authStore sends)
        r_username = self.client.post("/api/v1/auth/login", json={"username": "niloyjoy7@gmail.com", "password": "password123"})
        self.assertEqual(r_username.status_code, 200)
        data = r_username.json()
        self.assertIn("access_token", data)
        self.assertIn("user_id", data)
        self.assertEqual(data["role"], "admin")
        self.assertIn("permissions", data)

        # 2. Login with email field
        r_email = self.client.post("/api/v1/auth/login", json={"email": "niloyjoy7@gmail.com", "password": "password123"})
        self.assertEqual(r_email.status_code, 200)

        # 3. User registration
        r_reg = self.client.post("/api/v1/auth/register", json={"username": "newuser@example.com", "password": "securepassword", "name": "New User"})
        self.assertEqual(r_reg.status_code, 200)
        reg_data = r_reg.json()
        self.assertIn("access_token", reg_data)
        self.assertEqual(reg_data["role"], "user")

        # 4. Invalid credentials rejection
        r_invalid = self.client.post("/api/v1/auth/login", json={"username": "unknown@example.com", "password": "123"})
        self.assertEqual(r_invalid.status_code, 401)

    def test_09_workspace_and_conversation_aliases(self):
        headers = {"X-Guest-Mode": "true"}
        # Workspace contract
        r_ws = self.client.get("/api/v1/connections/my-workspace", headers=headers)
        self.assertEqual(r_ws.status_code, 200)
        ws_data = r_ws.json()
        self.assertIn("capabilities", ws_data)
        self.assertGreaterEqual(len(ws_data["capabilities"]), 1)

        # Conversation alias (/api/v1/conversations/)
        r_convs = self.client.get("/api/v1/conversations/", headers=headers)
        self.assertEqual(r_convs.status_code, 200)
        self.assertIn("conversations", r_convs.json())

    def test_10_chat_and_capability_aliases(self):
        headers = {"X-Guest-Mode": "true"}
        # 1. Capability execute alias (replaces 404 for controlPlane.executeCapability)
        r_cap = self.client.post(
            "/api/v1/capabilities/execute",
            json={
                "capability": "conversation.orchestrate",
                "source": "chat",
                "payload": {"prompt": "Hello test capability"},
            },
            headers=headers,
        )
        self.assertEqual(r_cap.status_code, 200)
        cap_data = r_cap.json()
        self.assertEqual(cap_data["status"], "completed")
        self.assertEqual(cap_data["capability"], "conversation.orchestrate")
        self.assertTrue(cap_data["verification"]["verified"])
        self.assertIn("execution_id", cap_data)

        # 2. Stream chat alias (replaces 404 for chatService.sendMessageStream)
        # Should not 404; reaches chat completion pipeline
        r_stream = self.client.post(
            "/api/v1/stream/chat",
            json={"message": "hello stream"},
            headers=headers,
        )
        self.assertNotEqual(r_stream.status_code, 404)


if __name__ == "__main__":
    unittest.main()
