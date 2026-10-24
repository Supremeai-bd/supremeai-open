"""gateway/tests/test_chat_architecture.py - Unit and acceptance tests for Chat Architecture.

Tests cover:
1. Context Compiler (System Anchor, Platform Grounding Sheet, Sampling Lock, 3-Tier Memory)
2. Response Guard (Identity Bleed Purge, Stub Rejector, Markdown Integrity)
3. Canonical Memory Store (Sequencing, Durable User Memory, Provider Attempts Ledger)
4. Cold-Start and Multi-Provider Invariant Verification
"""
from __future__ import annotations

import os
import tempfile
import pytest

from gateway.service.context_compiler import (
    CORE_SYSTEM_ANCHOR,
    PLATFORM_GROUNDING_SHEET,
    build_system_anchor,
    compile_chat_context,
    resolve_sampling_knobs,
)
from gateway.service.response_guard import (
    is_stub_content,
    purge_identity_bleed,
    repair_markdown,
    validate_and_sanitize,
)
from gateway.service.memory_store import CanonicalMemoryStore


class TestContextCompiler:
    def test_system_anchor_contains_constitution_and_anti_hallucination(self):
        anchor = build_system_anchor()
        assert "You are SupremeAI" in anchor
        assert "NOT a generic model from Google, Meta, OpenAI" in anchor
        assert "DO NOT GUESS or fabricate answers" in anchor
        assert "Cold-Start Safety" in anchor
        assert "Federation Architecture: 12 Product Satellites" in anchor
        assert "Zero-Admin" in anchor

    def test_sampling_knobs_logic_vs_chat(self):
        # Logic / code / debug queries must lock temperature to 0.2
        knobs_logic = resolve_sampling_knobs(
            messages=[{"role": "user", "content": "debug this python error in gateway route"}],
            mode="logic",
        )
        assert knobs_logic["temperature"] == 0.2

        # General conversation queries must lock temperature to 0.4
        knobs_chat = resolve_sampling_knobs(
            messages=[{"role": "user", "content": "কেমন আছেন? আজকের আবহাওয়া কেমন?"}],
            mode="chat",
        )
        assert knobs_chat["temperature"] == 0.4

    def test_compile_chat_context_injects_anchor_and_recent_history(self):
        compiled = compile_chat_context(
            messages=[
                {"role": "user", "content": "প্রথম প্রশ্ন"},
                {"role": "assistant", "content": "প্রথম উত্তর"},
                {"role": "user", "content": "দ্বিতীয় প্রশ্ন"},
            ],
            conversation_id="test-conv-01",
            user_id="usr-test-1",
            language_pref="bn",
        )
        assert len(compiled) >= 4
        # First message must be compiled system anchor
        assert compiled[0]["role"] == "system"
        assert "SupremeAI" in compiled[0]["content"]
        assert "Language preference: bn" in compiled[0]["content"]

        # User and assistant messages follow
        assert compiled[1]["role"] == "user"
        assert compiled[1]["content"] == "প্রথম প্রশ্ন"


class TestResponseGuard:
    def test_purge_identity_bleed(self):
        raw = "Hello, I am Gemini, developed by Google. I can assist you with Meta Llama models."
        scrubbed = purge_identity_bleed(raw)
        assert "Google" not in scrubbed
        assert "Gemini" not in scrubbed
        assert "Meta" not in scrubbed
        assert "SupremeAI" in scrubbed

    def test_stub_detection(self):
        assert is_stub_content("Web Session Active") is True
        assert is_stub_content("health=200") is True
        assert is_stub_content("Authenticated via proxy") is True
        assert is_stub_content("") is True
        assert is_stub_content("ok") is True
        assert is_stub_content("Hello! This is a genuine and detailed response from the architect.") is False

    def test_repair_markdown_unclosed_fence(self):
        broken = "Here is the code:\n```python\nprint('hello world')"
        fixed = repair_markdown(broken)
        assert fixed.count("```") % 2 == 0
        assert fixed.endswith("```")

    def test_validate_and_sanitize_openai_format(self):
        payload = {
            "id": "chatcmpl-test",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "I am Gemini created by Google.\n```python\nx = 1",
                    },
                }
            ],
        }
        sanitized = validate_and_sanitize(payload)
        cleaned_content = sanitized["choices"][0]["message"]["content"]
        assert "Google" not in cleaned_content
        assert "Gemini" not in cleaned_content
        assert "SupremeAI" in cleaned_content
        assert cleaned_content.count("```") % 2 == 0

    def test_validate_and_sanitize_rejects_stub(self):
        payload = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Web Session Active",
                    }
                }
            ]
        }
        with pytest.raises(ValueError, match="stub or broken content rejected"):
            validate_and_sanitize(payload)


class TestMemoryStore:
    def test_canonical_memory_sqlite_lifecycle(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            db_path = tf.name

        try:
            store = CanonicalMemoryStore(db_path=db_path)
            conv_id = "conv-unit-101"
            user_id = "user-101"

            # 1. Save conversation
            store.save_conversation(conv_id, user_id=user_id, title="Test Chat", summary="Summary text")

            # 2. Append sequence-locked messages
            m1 = store.append_canonical_message(conv_id, "user", "Hello architect", user_id=user_id)
            assert m1["sequence_no"] == 1

            m2 = store.append_canonical_message(conv_id, "assistant", "Hello. How can I help?", user_id=user_id)
            assert m2["sequence_no"] == 2

            # 3. Retrieve recent history
            history = store.get_recent_history(conv_id, limit=5)
            assert len(history) == 2
            assert history[0]["content"] == "Hello architect"
            assert history[1]["content"] == "Hello. How can I help?"

            # 4. Durable user memory
            store.upsert_user_memory(user_id, "preferred_lang", "bn-BD", confidence=0.98)
            mems = store.get_user_durable_memories(user_id)
            assert len(mems) == 1
            assert mems[0]["memory_key"] == "preferred_lang"
            assert mems[0]["memory_value"] == "bn-BD"

            # 5. Provider attempt log
            store.log_provider_attempt(
                request_id="req-test-99",
                conversation_id=conv_id,
                provider="stealth-webhook",
                status_code=200,
                latency_ms=350,
            )
        finally:
            if os.path.exists(db_path):
                try:
                    os.remove(db_path)
                except Exception:
                    pass


class TestChatGatewayIntegration:
    def test_pipeline_compiler_and_sanitizer_end_to_end(self, monkeypatch):
        from starlette.testclient import TestClient
        from gateway.service import app as app_module

        # Mock forward_stealth_webhook
        forward_captured_body = {}

        async def mock_forward_stealth_webhook(url, secret, body, timeout=15.0):
            nonlocal forward_captured_body
            forward_captured_body = dict(body)
            # Return identity bleed output with unclosed markdown fence
            return 200, {
                "reply": "I am Gemini, developed by Google.\nHere is your solution:\n```python\nprint('hello from architect')"
            }

        monkeypatch.setattr(app_module, "forward_stealth_webhook", mock_forward_stealth_webhook)
        monkeypatch.setattr(app_module, "STEALTH_WEBHOOK_URL", "https://mock-relay.internal/webhook")
        monkeypatch.setattr(app_module, "STEALTH_WEBHOOK_SECRET", "mock-secret")

        client = TestClient(app_module.app)
        conv_id = "conv-integration-test-01"

        res = client.post(
            "/v1/chat/completions",
            headers={"X-Guest-Mode": "true", "X-Conversation-Id": conv_id},
            json={
                "model": "auto",
                "messages": [{"role": "user", "content": "How does the federation architecture work?"}],
            },
        )

        assert res.status_code == 200
        data = res.json()

        # 1. Verification of Context Compiler:
        # The outbound body forwarded to the webhook must contain the compiled system anchor
        forwarded_messages = forward_captured_body.get("messages", [])
        assert len(forwarded_messages) >= 2
        assert forwarded_messages[0]["role"] == "system"
        assert "You are SupremeAI" in forwarded_messages[0]["content"]
        assert "Platform Grounding Sheet" in forwarded_messages[0]["content"] or "12 Product Satellites" in forwarded_messages[0]["content"]

        # 2. Verification of Response Guard:
        # The response returned to the client must have identity bleed purged and markdown repaired
        content = data["choices"][0]["message"]["content"]
        assert "Google" not in content
        assert "Gemini" not in content
        assert "SupremeAI" in content
        assert content.count("```") % 2 == 0
        assert content.endswith("```")

