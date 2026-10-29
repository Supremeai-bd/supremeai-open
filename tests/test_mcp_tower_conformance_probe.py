import pytest
from scripts.ci.mcp_tower_conformance_probe import (
    build_initialize_payload,
    analyze_capabilities,
    run_self_test
)

def test_mcp_tower_conformance_probe_self_test():
    assert run_self_test() == 0

def test_initialize_payload_contract():
    p1 = build_initialize_payload("2025-06-18")
    assert p1["jsonrpc"] == "2.0"
    assert p1["id"] == "probe-2025-06-18"
    assert p1["params"]["protocolVersion"] == "2025-06-18"
    assert p1["params"]["clientInfo"]["name"] == "supremeai-conformance-probe"

def test_capability_analysis_matrix():
    raw_caps = {
        "tools": {"listChanged": True},
        "resources": {"listChanged": True},
        "prompts": {"listChanged": True}
    }
    analysis = analyze_capabilities(raw_caps)
    assert analysis["tools"] is True
    assert analysis["resources"] is True
    assert analysis["prompts"] is True
    assert analysis["tasks"] is False
    assert analysis["elicitation"] is False
    assert analysis["sampling"] is False
    assert analysis["logging"] is False
    assert analysis["completions"] is False

    expanded = {
        "tools": {},
        "tasks": {"listChanged": True},
        "elicitation": {}
    }
    analysis2 = analyze_capabilities(expanded)
    assert analysis2["tasks"] is True
    assert analysis2["elicitation"] is True
    assert analysis2["resources"] is False
