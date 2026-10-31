#!/usr/bin/env python3
"""Rename-wave name tolerance — born-red contract tests (Zero-Recurrence U6).

বাংলা: tower_name_tolerance শেয়ার্ড ক্যুরের যান্ত্রিক চুক্তি। প্রেক্ষাপট:
টাওয়ার-রেজিস্ট্রির নাম দ্বিমুখী দোলে (underscore ↔ dot; ঢেউ-১ #2454/#2457,
ঢেউ-৩ live 2026-10-31) এবং মৃত-নামের সাড়া JSON-RPC error নয় — HTTP-200
isError content-text (এমনকি কিছু কলারে str-আকৃতিতে)। এক-বানান hardcode ও
এক-আকৃতি প্রেডিকেট উভয়েই কলার অন্ধ করে — এই টেস্ট দুটোই আটকায়।
Offline only — প্রতিটি পরীক্ষা ফেক-কলাবল ঢোকায়, নেটওয়ার্ক নেই।
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "ci"))

from tower_name_tolerance import (  # noqa: E402
    call_across_names,
    envelope_says_tool_not_found,
    epoch_spellings,
    is_tool_not_found_error_env,
    tolerant_tool_call,
)

DEAD_DOT_TEXT = "MCP error -32602: Tool bridge.work_queue not found"


def _is_error_content(resp: dict) -> dict:
    return {"content": [{"type": "text", "text": DEAD_DOT_TEXT}], "isError": True}


class TestEpochSpellings(unittest.TestCase):
    def test_documented_families_have_both_waves(self):
        self.assertEqual(epoch_spellings("bridge.work_queue"),
                         ("bridge.work_queue", "bridge_work_queue"))
        self.assertEqual(epoch_spellings("bridge.work_order"),
                         ("bridge.work_order", "bridge_work_order"))
        self.assertEqual(epoch_spellings("github.list_prs"),
                         ("github.list_prs", "github_list_prs"))

    def test_unknown_name_is_single_entry_passthrough(self):
        self.assertEqual(epoch_spellings("system_health"), ("system_health",))


class TestNotFoundPredicate(unittest.TestCase):
    def test_jsonrpc_error_envelope_shape(self):
        env = {"error": {"code": -32602, "message": "Tool x not found"}}
        self.assertTrue(is_tool_not_found_error_env(env))
        self.assertTrue(envelope_says_tool_not_found(env))

    def test_http200_is_error_content_shape(self):
        resp = _is_error_content({})
        self.assertFalse(is_tool_not_found_error_env(resp))
        self.assertTrue(envelope_says_tool_not_found(resp))

    def test_jsonrpc_response_result_content_shape(self):
        # বাংলা: চতুর্থ আকৃতি — JSON-RPC success envelope যার result.content-ই
        # isError text বহন করে (MCP tools/call-এর স্ট্যান্ডার্ড শেপ; watchdog-এর
        # _rpc funnel ঠিক এটাই দেখে — live dark ছিল, GLM Agent 11 cycle-15)।
        resp = {"jsonrpc": "2.0", "id": 7, "result": _is_error_content(None)}
        self.assertFalse(is_tool_not_found_error_env(resp))
        self.assertTrue(envelope_says_tool_not_found(resp))

    def test_result_content_shape_falls_through_to_next_spelling(self):
        # বাংলা: funnel-আকৃতিতেও first-live-wins ক্রস করে মৃত বানান —
        # watchdog-কিউর-এর hermetic প্রমাণ (নেটওয়ার্ক নেই)।
        calls: list[str] = []

        def call(n: str):
            calls.append(n)
            if n == "bridge.work_queue":
                return {"jsonrpc": "2.0", "id": 1, "result": _is_error_content(None)}
            return {"jsonrpc": "2.0", "id": 2,
                    "result": {"content": [{"type": "text", "text": "{\"workOrders\": []}"}]}}

        resp = call_across_names(call, epoch_spellings("bridge.work_queue"))
        self.assertEqual(calls, ["bridge.work_queue", "bridge_work_queue"])
        self.assertEqual(resp["result"]["content"][0]["text"], "{\"workOrders\": []}")

    def test_raw_text_shape_from_tool_text_style_callers(self):
        self.assertTrue(envelope_says_tool_not_found(DEAD_DOT_TEXT))

    def test_rbac_forbidden_is_never_not_found(self):
        # ঢেউ-৩ live: জীবিত-নাম RBAC denial-কে মৃত-নাম ভেবে দ্বিতীয় বানানে
        # পালানো ভুল — Forbidden হলো সাড়াই চূড়ান্ত, নাম-পরিবর্তন অন্ধ নয়।
        forbidden_text = ("Forbidden: memory_record_task requires agent role or "
                          "higher (default-deny RBAC). Present a valid MCP Bearer "
                          "token with a sufficient role.")
        self.assertFalse(envelope_says_tool_not_found(forbidden_text))
        forbidden_env = {"error": {"code": -32603, "message": forbidden_text}}
        self.assertFalse(envelope_says_tool_not_found(forbidden_env))

    def test_live_payload_is_never_not_found(self):
        self.assertFalse(envelope_says_tool_not_found(
            {"content": [{"type": "text", "text": '{"totalOpen": 60}'}]}))


class TestCallAcrossNames(unittest.TestCase):
    def test_first_live_wins(self):
        calls = []

        def call(name):
            calls.append(name)
            return {"ok": name}

        out = call_across_names(call, ("a", "b"))
        self.assertEqual(out, {"ok": "a"})
        self.assertEqual(calls, ["a"])

    def test_dead_spelling_falls_through_to_next(self):
        def call(name):
            if name == "a":
                return _is_error_content({})
            return {"ok": name}

        self.assertEqual(call_across_names(call, ("a", "b")), {"ok": "b"})

    def test_str_shape_dead_spelling_falls_through(self):
        def call(name):
            return DEAD_DOT_TEXT if name == "a" else '{"totalOpen": 60}'

        self.assertEqual(call_across_names(call, ("a", "b")), '{"totalOpen": 60}')

    def test_all_dead_returns_last_not_found_response(self):
        def call(_name):
            return _is_error_content({})

        out = call_across_names(call, ("a", "b"))
        self.assertTrue(envelope_says_tool_not_found(out))

    def test_all_raising_reraises_last_exception(self):
        def call(_name):
            raise RuntimeError("tower down")

        with self.assertRaises(RuntimeError):
            call_across_names(call, ("a", "b"))

    def test_exception_then_success_uses_success(self):
        def call(name):
            if name == "a":
                raise RuntimeError("transport")
            return {"ok": name}

        self.assertEqual(call_across_names(call, ("a", "b")), {"ok": "b"})

    def test_rbac_forbidden_stops_the_chain(self):
        calls = []

        def call(name):
            calls.append(name)
            return {"error": {"code": -32603, "message": "Forbidden: requires agent role"}}

        call_across_names(call, ("a", "b"))
        self.assertEqual(calls, ["a"])


class TestTolerantToolCall(unittest.TestCase):
    def test_wraps_name_args_style_callers(self):
        seen = {}

        def call(name, args):
            seen["tuple"] = (name, args)
            return {"ok": name, "args": args}

        out = tolerant_tool_call(call, "bridge.work_queue", {"limit": 5})
        # ফেক-কল সব বানানে জীবিত সাড়া দেয় → যুগ-ক্রমের প্রথম বানানই জয়ী।
        self.assertEqual(out["ok"], "bridge.work_queue")
        self.assertEqual(seen["tuple"], ("bridge.work_queue", {"limit": 5}))

    def test_wrapped_caller_falls_through_dead_first_spelling(self):
        def call(name, _args):
            if name == "bridge.work_queue":
                return DEAD_DOT_TEXT
            return '{"workOrders": []}'

        out = tolerant_tool_call(call, "bridge.work_queue", {})
        self.assertEqual(out, '{"workOrders": []}')


if __name__ == "__main__":
    unittest.main()
