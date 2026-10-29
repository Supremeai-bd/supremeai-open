"""Tower URL resolution contract — #2317 (R60 lane, #2300 option A).

The documented agent setup carries the /mcp endpoint suffix
(dispatch-mandate export form; repo-root mcp.json). connect() appends
MCP_SSE_PATH itself, so every resolver return path must yield the base
origin — pre-fix the /mcp suffix survived and the join produced the dead
path GET /mcp/sse (live 404) while GET /sse answers 200. tower_db_bridge
declared it follows the client resolution contract but kept a private
duplicate with the same gap; option A retires the duplicate in favor of
the shared helper so the drift cannot regrow.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "agents"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ops" / "operations"))

import mcp_tower_client  # noqa: E402

ORIGIN = "https://supremeai-mcp-tower.onrender.com"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("MCP_TOWER_URL", raising=False)
    monkeypatch.delenv("MCP_SERVER_URL", raising=False)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # the documented dispatch-mandate form — the bug case (#2300)
        ("https://supremeai-mcp-tower.onrender.com/mcp", ORIGIN),
        # legacy forms and combinations, all order-tolerant
        ("https://supremeai-mcp-tower.onrender.com/sse", ORIGIN),
        ("https://supremeai-mcp-tower.onrender.com/mcp/sse", ORIGIN),
        (ORIGIN, ORIGIN),
        (ORIGIN + "/", ORIGIN),
        # exact-suffix matching: a path that merely CONTAINS /mcp is untouched
        ("https://example.com/mcp-server", "https://example.com/mcp-server"),
        ("https://example.com/mcp/sse-extra", "https://example.com/mcp/sse-extra"),
    ],
)
def test_strip_endpoint_suffixes(raw, expected):
    assert mcp_tower_client.strip_endpoint_suffixes(raw) == expected


def test_env_documented_form_resolves_to_origin(monkeypatch):
    monkeypatch.setenv("MCP_TOWER_URL", ORIGIN + "/mcp")
    assert mcp_tower_client.resolve_mcp_server_url() == ORIGIN


def test_env_sse_form_resolves_to_origin(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_URL", ORIGIN + "/sse")
    assert mcp_tower_client.resolve_mcp_server_url() == ORIGIN


@pytest.mark.skipif(
    not (REPO_ROOT / "mcp.json").exists(), reason="repo mcp.json absent"
)
def test_mcp_json_vector_resolves_to_origin(monkeypatch):
    # the tracked mcp.json carries url ".../mcp" — the second #2300 vector;
    # pinning it here keeps the fallback contract honest if the file drifts
    cfg = json.loads((REPO_ROOT / "mcp.json").read_text(encoding="utf-8"))
    assert cfg["mcpServers"]["supremeai-control-tower"]["url"].endswith("/mcp")
    assert mcp_tower_client.resolve_mcp_server_url() == ORIGIN


def test_client_join_contract_under_documented_env(monkeypatch):
    # the actual failure surface: server_url + sse_path must be the live endpoint
    monkeypatch.setenv("MCP_TOWER_URL", ORIGIN + "/mcp")
    client = mcp_tower_client.McpTowerClient(
        server_url=mcp_tower_client.resolve_mcp_server_url()
    )
    assert client.server_url + client.sse_path == ORIGIN + "/sse"


def test_tower_db_bridge_shares_the_helper(monkeypatch):
    # option A: the bridge's private duplicate is retired in favor of the
    # shared helper — the drift that produced this bug cannot regrow
    import tower_db_bridge

    assert (
        tower_db_bridge.strip_endpoint_suffixes
        is mcp_tower_client.strip_endpoint_suffixes
    )
    monkeypatch.setenv("MCP_TOWER_URL", ORIGIN + "/mcp")
    assert tower_db_bridge._resolve_tower_url() == ORIGIN
