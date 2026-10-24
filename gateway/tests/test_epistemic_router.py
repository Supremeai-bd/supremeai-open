"""gateway/tests/test_epistemic_router.py - Unit tests for Epistemic Router & Duo Pairing.

Tests cover:
1. Swiss-Watch Duo Pairing Health (/api/v1/epistemic/health)
2. Tool Schema Pruning (/api/v1/tools/prune)
3. Memory Gate (/api/v1/memory/gate)
4. Model Horizon Listing & Intercept (/api/v1/model-horizon, /api/v1/model-horizon/intercept)
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient
from gateway.service.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_duo_pairing_joint_health(client):
    res = client.get("/api/v1/epistemic/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "duo_pairing" in data
    duo = data["duo_pairing"]
    assert duo["chronofact_model_horizon"]["status"] == "healthy"
    assert duo["chronofact_tool_pruner"]["status"] == "healthy"
    assert duo["chronofact_memory_gate"]["status"] == "healthy"
    assert duo["spine_stream_sanitizer"]["status"] == "healthy"
    assert data["invariants"]["memory_cosine_threshold"] == 0.72


def test_tool_prune_endpoint(client):
    tools = [
        {"name": "fetch_css_styles", "description": "Fetches CSS stylesheet rules and colors", "tokens": 150},
        {"name": "query_database_sql", "description": "Executes SQL statements on Postgres", "tokens": 150},
    ]
    res = client.post(
        "/api/v1/tools/prune",
        json={"query": "change the button background color with CSS styles", "tools": tools, "threshold": 0.05},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data["retained"]) == 1
    assert data["retained"][0]["name"] == "fetch_css_styles"
    assert data["reduction_pct"] > 0


def test_memory_gate_endpoint(client):
    entries = [
        {"id": "m1", "domain": "frontend", "content": "The UI theme is dark cosmic indigo."},
        {"id": "m2", "domain": "database", "content": "Database uses PostgreSQL with pgvector."},
    ]
    res = client.post(
        "/api/v1/memory/gate",
        json={"query": "theme dark color palette", "entries": entries, "threshold": 0.05},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data["retained"]) >= 1
    assert data["retained"][0]["id"] == "m1"


def test_model_horizon_list(client):
    res = client.get("/api/v1/model-horizon")
    assert res.status_code == 200
    data = res.json()
    assert "models" in data
    assert len(data["models"]) > 0


def test_model_horizon_intercept_retired(client):
    res = client.post(
        "/api/v1/model-horizon/intercept",
        json={"model_id": "anthropic/claude-3-5-sonnet"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["kind"] == "retired"
    assert data["successor"] is not None
