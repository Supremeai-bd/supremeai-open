#!/usr/bin/env python3
"""R87 / #3620 Phase A — genai_export adapter contract tests (offline, stdlib).

Covers: default-off gate, invoke_agent root span, execute_tool + MCP
refinements, token lift to gen_ai.usage.*, redaction-before-export, custom
(cost/links/skill_bundle) attributes, deterministic span ids, OTLP shape.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import genai_export as gx
from agent_trace import AgentTrace, TraceEvent


def _sample_trace() -> AgentTrace:
    return AgentTrace(
        task_id="bridge-20261031-r87-otel-genai-obs-glm24",
        role="solver",
        agent_name="GLM Agent 24 (Job 486817)",
        model="glm-4.6",
        provider="zai",
        decision="implement the export adapter",
        guardrail_result="approved",
        tests_evidence=["pytest tests/test_genai_export.py"],
        links={"issue": "3620", "pr": "3624"},
        cost_usd=0.42,
        skill_bundle_hash="abc123",
        outcome="success",
        events=[
            TraceEvent(event_type="run_start", name="solver-dispatch"),
            TraceEvent(event_type="tool_call", name="bridge.work_queue",
                       detail={"input_tokens": 1200, "output_tokens": 340,
                               "api_key": "sk-SUPERSECRET"}),
            TraceEvent(event_type="verification", name="pytest",
                       status="ok", detail={"tests": 8}),
            TraceEvent(event_type="outcome", name="pr-submitted", status="ok"),
        ],
    )


def _all_attrs(span: dict) -> dict:
    return {a["key"]: a["value"] for a in span.get("attributes", [])}


class TestDefaultOff(unittest.TestCase):
    def test_export_disabled_by_default(self):
        import os
        saved = os.environ.pop(gx.EXPORT_ENV, None)
        try:
            result = gx.export_trace(_sample_trace())
            self.assertFalse(result["exported"])
            self.assertIn("not enabled", result["reason"])
        finally:
            if saved is not None:
                os.environ[gx.EXPORT_ENV] = saved

    def test_http_sink_requires_endpoint(self):
        import os
        os.environ[gx.EXPORT_ENV] = "1"
        os.environ[gx.ENDPOINT_ENV] = ""
        os.environ["SUPREMEAI_OTEL_SINK"] = "http"
        try:
            result = gx.export_trace(_sample_trace())
            self.assertFalse(result["exported"])
        finally:
            os.environ.pop(gx.EXPORT_ENV, None)
            os.environ.pop(gx.ENDPOINT_ENV, None)
            os.environ.pop("SUPREMEAI_OTEL_SINK", None)


class TestSpanStructure(unittest.TestCase):
    def setUp(self):
        self.doc = gx.trace_to_resource_spans(_sample_trace())
        self.spans = self.doc["resourceSpans"][0]["scopeSpans"][0]["spans"]

    def test_otlp_shape(self):
        self.assertEqual(len(self.doc["resourceSpans"]), 1)
        scope = self.doc["resourceSpans"][0]["scopeSpans"][0]
        self.assertEqual(scope["scope"]["name"], gx.SCOPE_NAME)
        self.assertGreaterEqual(len(self.spans), 5)  # root + 4 events

    def test_root_invoke_agent_span(self):
        root = self.spans[0]
        self.assertEqual(root["name"], "invoke_agent")
        attrs = _all_attrs(root)
        self.assertEqual(attrs["gen_ai.operation.name"]["stringValue"], "invoke_agent")
        self.assertEqual(attrs["gen_ai.request.model"]["stringValue"], "glm-4.6")
        self.assertEqual(attrs["gen_ai.provider.name"]["stringValue"], "zai")
        self.assertEqual(attrs["supremeai.task_id"]["stringValue"],
                         "bridge-20261031-r87-otel-genai-obs-glm24")
        self.assertEqual(root["status"]["code"], gx._STATUS_OK)  # outcome=success

    def test_tool_call_execute_tool_with_mcp_refinements(self):
        tool_spans = [s for s in self.spans if s["name"].startswith("execute_tool")]
        self.assertEqual(len(tool_spans), 1)
        attrs = _all_attrs(tool_spans[0])
        self.assertEqual(attrs["gen_ai.tool.name"]["stringValue"], "bridge.work_queue")
        self.assertEqual(attrs["mcp.request.method"]["stringValue"], "tools/call")
        self.assertEqual(attrs["mcp.tool.name"]["stringValue"], "bridge.work_queue")
        self.assertEqual(tool_spans[0]["parentSpanId"], self.spans[0]["spanId"])

    def test_token_lift_to_genai_usage(self):
        tool_spans = [s for s in self.spans if s["name"].startswith("execute_tool")]
        attrs = _all_attrs(tool_spans[0])
        self.assertEqual(attrs["gen_ai.usage.input_tokens"]["intValue"], "1200")
        self.assertEqual(attrs["gen_ai.usage.output_tokens"]["intValue"], "340")

    def test_non_genai_event_type_gets_no_invented_genai_keys(self):
        verif = [s for s in self.spans if s["name"].startswith("verification")]
        self.assertEqual(len(verif), 1)
        attrs = _all_attrs(verif[0])
        self.assertFalse(any(k.startswith("gen_ai.") for k in attrs))
        self.assertIn("supremeai.detail.tests", attrs)

    def test_cost_is_custom_key_not_genai(self):
        attrs = _all_attrs(self.spans[0])
        self.assertEqual(attrs["supremeai.cost_usd"]["doubleValue"], 0.42)
        self.assertNotIn("gen_ai.usage.cost", attrs)

    def test_no_content_capture_attributes_anywhere(self):
        blob = json.dumps(self.doc)
        for forbidden in ("gen_ai.system_instructions", "gen_ai.input.messages",
                          "gen_ai.output.messages"):
            self.assertNotIn(forbidden, blob)


class TestRedactionBeforeExport(unittest.TestCase):
    def test_sensitive_detail_value_never_plaintext(self):
        doc = gx.trace_to_resource_spans(_sample_trace())
        blob = json.dumps(doc)
        self.assertNotIn("sk-SUPERSECRET", blob)
        self.assertIn("redacted", blob)


class TestDeterminism(unittest.TestCase):
    def test_span_ids_stable_across_calls(self):
        a = gx.trace_to_resource_spans(_sample_trace())
        b = gx.trace_to_resource_spans(_sample_trace())
        sa = [s["spanId"] for s in a["resourceSpans"][0]["scopeSpans"][0]["spans"]]
        sb = [s["spanId"] for s in b["resourceSpans"][0]["scopeSpans"][0]["spans"]]
        self.assertEqual(sa, sb)

    def test_partial_outcome_is_unset_not_error(self):
        t = _sample_trace()
        t.outcome = "partial"
        doc = gx.trace_to_resource_spans(t)
        root = doc["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        self.assertEqual(root["status"]["code"], gx._STATUS_UNSET)


class TestRawDictPath(unittest.TestCase):
    def test_raw_dict_input_also_redacted(self):
        raw = {"task_id": "t1", "role": "solver", "agent_name": "a",
               "outcome": "success",
               "events": [{"event_type": "tool_call", "name": "n",
                           "status": "ok", "detail": {"password": "hunter2"}}]}
        doc = gx.trace_to_resource_spans(raw)
        self.assertNotIn("hunter2", json.dumps(doc))


class TestAgentTraceTokenCountAllowlist(unittest.TestCase):
    """Zero-Recurrence guard (R87/#3620 root-cause fix in agent_trace.py):
    token-count int values must survive redaction; secrets must not."""

    def test_int_token_counts_survive_to_dict(self):
        t = AgentTrace(task_id="t", role="r", agent_name="a",
                       events=[TraceEvent(event_type="tool_call", name="n",
                                          detail={"input_tokens": 1200,
                                                  "output_tokens": 340})])
        detail = t.to_dict()["events"][0]["detail"]
        self.assertEqual(detail["input_tokens"], 1200)
        self.assertEqual(detail["output_tokens"], 340)

    def test_string_under_token_key_still_redacted(self):
        t = AgentTrace(task_id="t", role="r", agent_name="a",
                       events=[TraceEvent(event_type="tool_call", name="n",
                                          detail={"input_tokens": "sk-leak"})])
        detail = t.to_dict()["events"][0]["detail"]
        self.assertTrue(str(detail["input_tokens"]).startswith("<redacted:"))

    def test_real_secrets_still_redacted(self):
        t = AgentTrace(task_id="t", role="r", agent_name="a",
                       events=[TraceEvent(event_type="tool_call", name="n",
                                          detail={"api_key": "sk-SUPERSECRET",
                                                  "authorization": "Bearer x",
                                                  "session_token": "sess-123"})])
        detail = t.to_dict()["events"][0]["detail"]
        self.assertNotIn("sk-SUPERSECRET", json.dumps(detail))
        self.assertNotIn("Bearer x", json.dumps(detail))
        self.assertNotIn("sess-123", json.dumps(detail))


if __name__ == "__main__":
    unittest.main()
