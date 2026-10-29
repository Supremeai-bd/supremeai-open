import pytest
from scripts.ci.mcp_registry_publisher import (
    build_server_json,
    validate_server_json_schema,
    run_self_test
)

def test_mcp_registry_publisher_self_test():
    assert run_self_test() == 0

def test_server_json_conformance():
    server = build_server_json()
    assert server["$schema"] == "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
    assert server["name"] == "org.supremeai/control-tower"
    assert len(server["description"]) <= 100
    assert server["version"] == "1.0.0"
    assert len(server["remotes"]) > 0
    assert server["remotes"][0]["type"] == "streamable-http"

    errs = validate_server_json_schema(server)
    assert len(errs) == 0

def test_server_json_validation_rejections():
    broken = build_server_json()
    del broken["name"]
    errs = validate_server_json_schema(broken)
    assert any("name" in e for e in errs)

    bad_prefix = build_server_json()
    bad_prefix["name"] = "unprefixed-name"
    errs = validate_server_json_schema(bad_prefix)
    assert any("domain-prefixed" in e for e in errs)
