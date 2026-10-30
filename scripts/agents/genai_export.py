#!/usr/bin/env python3
"""GenAI semantic-conventions export adapter (R87 — #3620 Phase A).

বাংলা: এই অ্যাডাপ্টার #3187-এর in-house `AGENT_TRACE_SCHEMA` (agent_trace.py)
রেকর্ডকে OpenTelemetry **GenAI semantic conventions**-এর শব্দভাণ্ডারে এক্সপোর্ট
করে — স্টোর প্রতিস্থাপন নয়, শুধু ইন্টারঅপ (R87 radar verdict: `adapt`)।

Mapping (honest, 1:1 where the standard defines one):
  AgentTrace                        -> invoke_agent span  (parent, one per trace)
  TraceEvent(event_type="tool_call")-> execute_tool {name} span + MCP refinements
                                       (mcp.request.method="tools/call",
                                        mcp.tool.name=<tool>)  [R87 §1]
  TraceEvent(verification/guardrail/handoff) -> plain INTERNAL spans,
                                       SupremeAI-local names — the GenAI
                                       vocabulary defines no convention for
                                       them yet (no invented gen_ai.* keys).
  trace.model/provider              -> gen_ai.request.model / gen_ai.provider.name
  events[].detail.input_tokens/output_tokens -> gen_ai.usage.input_tokens /
                                                gen_ai.usage.output_tokens
  cost_usd                          -> supremeai.cost_usd (custom key — the
                                       standard has no cost attribute yet)

Never emitted (by contract): gen_ai.system_instructions, gen_ai.input.messages,
gen_ai.output.messages — content capture stays off; agent_trace's redaction
(_redact_value) has already run before this adapter sees the record, because
the adapter consumes `AgentTrace.to_dict()` output only.

Export is OFF by default (SUPREMEAI_OTEL_EXPORT unset/0) — zero network, zero
spans. Sinks: "stdout" (default) or "http" POST of OTLP/JSON to
SUPREMEAI_OTEL_ENDPOINT. stdlib-only (urllib) — no OTel SDK dependency.

Usage:
  python scripts/agents/genai_export.py --trace t.json            # stdout sink
  SUPREMEAI_OTEL_EXPORT=1 SUPREMEAI_OTEL_ENDPOINT=https://... \
      python scripts/agents/genai_export.py --trace t.json        # OTLP/HTTP
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_trace import AgentTrace, TraceEvent  # same-dir sibling import

EXPORT_ENV = "SUPREMEAI_OTEL_EXPORT"
ENDPOINT_ENV = "SUPREMEAI_OTEL_ENDPOINT"
SCOPE_NAME = "supremeai.genai_export"
SCOPE_VERSION = 1

# OTLP StatusCode: 0=UNSET, 1=OK, 2=ERROR
_STATUS_OK, _STATUS_ERROR, _STATUS_UNSET = 1, 2, 0
_OUTCOME_STATUS = {"success": _STATUS_OK, "failure": _STATUS_ERROR,
                   "rejected": _STATUS_ERROR, "partial": _STATUS_UNSET}
_TOKEN_ALIASES = {"input_tokens": "gen_ai.usage.input_tokens",
                  "prompt_tokens": "gen_ai.usage.input_tokens",
                  "output_tokens": "gen_ai.usage.output_tokens",
                  "completion_tokens": "gen_ai.usage.output_tokens"}


def _span_id(trace_dict: dict[str, Any], name: str, seq: int) -> str:
    """Deterministic 8-byte span id — replay-stable, no RNG (audit-friendly)."""
    seed = f"{trace_dict.get('task_id')}|{trace_dict.get('agent_name')}|{name}|{seq}"
    return hashlib.sha256(seed.encode("utf-8", "replace")).hexdigest()[:16]


def _attr(k: str, v: Any) -> dict[str, Any]:
    """OTLP KeyValue — JSON-friendly typing only (str/int/float/bool/list)."""
    if isinstance(v, bool):
        return {"key": k, "value": {"boolValue": v}}
    if isinstance(v, int):
        return {"key": k, "value": {"intValue": str(v)}}
    if isinstance(v, float):
        return {"key": k, "value": {"doubleValue": v}}
    return {"key": k, "value": {"stringValue": str(v)}}


def _detail_attrs(detail: dict[str, Any]) -> list[dict[str, Any]]:
    """TraceEvent.detail -> span attributes; token fields lift to gen_ai.usage.*."""
    attrs: list[dict[str, Any]] = []
    for k, v in (detail or {}).items():
        key = _TOKEN_ALIASES.get(str(k), f"supremeai.detail.{k}")
        if isinstance(v, (str, int, float, bool)):
            attrs.append(_attr(key, v))
    return attrs


def trace_to_resource_spans(trace: AgentTrace | dict[str, Any]) -> dict[str, Any]:
    """Redacted trace -> OTLP/JSON resourceSpans document (GenAI vocabulary)."""
    d = trace.to_dict() if isinstance(trace, AgentTrace) else dict(trace)
    # Redaction is guaranteed upstream by to_dict(); enforce for raw dicts too.
    from agent_trace import _redact_value  # local import: single chokepoint
    d = _redact_value(d)

    spans: list[dict[str, Any]] = []
    parent_id = _span_id(d, "invoke_agent", 0)

    root_attrs = [
        _attr("gen_ai.operation.name", "invoke_agent"),
        _attr("supremeai.task_id", d.get("task_id", "")),
        _attr("supremeai.role", d.get("role", "")),
        _attr("supremeai.agent_name", d.get("agent_name", "")),
        _attr("supremeai.outcome", d.get("outcome", "partial")),
    ]
    if d.get("model"):
        root_attrs.append(_attr("gen_ai.request.model", d["model"]))
    if d.get("provider"):
        root_attrs.append(_attr("gen_ai.provider.name", d["provider"]))
    if d.get("cost_usd") is not None:
        root_attrs.append(_attr("supremeai.cost_usd", float(d["cost_usd"])))
    if d.get("skill_bundle_hash"):
        root_attrs.append(_attr("supremeai.skill_bundle_hash", d["skill_bundle_hash"]))
    for k, v in (d.get("links") or {}).items():
        root_attrs.append(_attr(f"supremeai.link.{k}", v))

    spans.append({
        "traceId": hashlib.sha256(
            json.dumps({k: d.get(k) for k in ("task_id", "agent_name", "role")},
                       sort_keys=True, ensure_ascii=False, default=str)
            .encode("utf-8", "replace")).hexdigest()[:32],
        "spanId": parent_id,
        "parentSpanId": "",
        "name": "invoke_agent",
        "kind": "SPAN_KIND_INTERNAL",
        "status": {"code": _OUTCOME_STATUS.get(d.get("outcome"), _STATUS_UNSET)},
        "attributes": root_attrs,
    })

    seq = 1
    for ev in d.get("events", []):
        etype, name = str(ev.get("event_type", "")), str(ev.get("name", ""))
        span = {
            "traceId": spans[0]["traceId"],
            "spanId": _span_id(d, f"{etype}:{name}", seq),
            "parentSpanId": parent_id,
            "kind": "SPAN_KIND_INTERNAL",
            "attributes": [
                _attr("supremeai.event.type", etype),
                _attr("supremeai.event.status", ev.get("status", "ok")),
            ],
            "status": {"code": _STATUS_OK if ev.get("status", "ok") == "ok" else _STATUS_ERROR},
        }
        if etype == "tool_call":
            # R87 §1: execute_tool refinement + MCP tool-call conventions
            span["name"] = f"execute_tool {name}"
            span["attributes"] += [
                _attr("gen_ai.operation.name", "execute_tool"),
                _attr("gen_ai.tool.name", name),
                _attr("mcp.request.method", "tools/call"),
                _attr("mcp.tool.name", name),
            ]
        else:
            # No gen_ai.* invention for non-GenAI event types — local naming only.
            span["name"] = f"{etype} {name}".strip()
        span["attributes"] += _detail_attrs(ev.get("detail") or {})
        spans.append(span)
        seq += 1

    return {
        "resourceSpans": [{
            "resource": {"attributes": [
                _attr("service.name", "supremeai-agents"),
                _attr("service.namespace", "supremeai"),
                _attr("supremeai.trace_schema_version", d.get("schema_version", 1)),
            ]},
            "scopeSpans": [{
                "scope": {"name": SCOPE_NAME, "version": str(SCOPE_VERSION)},
                "spans": spans,
            }],
        }]
    }


def _post_otlp(doc: dict[str, Any], endpoint: str) -> dict[str, Any]:
    data = json.dumps(doc, ensure_ascii=False, default=str).encode("utf-8")
    req = urllib.request.Request(
        endpoint, data=data, method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:  # endpoint is operator-configured
        return {"exported": True, "sink": "http", "status": resp.status,
                "endpoint": endpoint, "spans": _count_spans(doc)}


def _count_spans(doc: dict[str, Any]) -> int:
    return sum(len(ss.get("spans", []))
               for rs in doc.get("resourceSpans", [])
               for ss in rs.get("scopeSpans", []))


def export_trace(trace: AgentTrace | dict[str, Any]) -> dict[str, Any]:
    """Env-gated export — default OFF (zero network, zero side effects)."""
    if os.environ.get(EXPORT_ENV, "0").lower() not in ("1", "true", "yes"):
        return {"exported": False, "reason": f"{EXPORT_ENV} not enabled", "spans": 0}
    doc = trace_to_resource_spans(trace)
    sink = os.environ.get("SUPREMEAI_OTEL_SINK", "stdout").lower()
    if sink == "http":
        endpoint = os.environ.get(ENDPOINT_ENV, "")
        if not endpoint:
            return {"exported": False, "reason": f"{ENDPOINT_ENV} missing", "spans": 0}
        return _post_otlp(doc, endpoint)
    return {"exported": True, "sink": "stdout", "spans": _count_spans(doc),
            "document": doc}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export AGENT_TRACE_SCHEMA records to OTel GenAI semconv (R87)")
    parser.add_argument("--trace", required=True, help="trace JSON file (agent_trace format)")
    parser.add_argument("--force", action="store_true",
                        help="emit to stdout regardless of SUPREMEAI_OTEL_EXPORT (local inspection)")
    args = parser.parse_args(argv)

    from pathlib import Path
    data = json.loads(Path(args.trace).read_text(encoding="utf-8"))
    trace = AgentTrace(
        task_id=str(data["task_id"]), role=data["role"], agent_name=data["agent_name"],
        task_type=data.get("task_type"), model=data.get("model"),
        provider=data.get("provider"), decision=data.get("decision"),
        decision_ledger=data.get("decision_ledger"),
        guardrail_result=data.get("guardrail_result"),
        tests_evidence=data.get("tests_evidence", []),
        links=data.get("links", {}), cost_usd=data.get("cost_usd"),
        latency_seconds=data.get("latency_seconds"),
        outcome=data.get("outcome", "partial"),
        skill_bundle_hash=data.get("skill_bundle_hash"),
        events=[TraceEvent(**e) for e in data.get("events", [])],
    )
    result = export_trace(trace)
    if args.force and not result.get("exported"):
        doc = trace_to_resource_spans(trace)
        print(json.dumps(doc, ensure_ascii=False, indent=2, default=str))
        return 0
    if result.get("sink") == "stdout" and result.get("exported"):
        print(json.dumps(result.pop("document"), ensure_ascii=False, indent=2, default=str))
        return 0
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
