from fastapi.testclient import TestClient
from core.services.brain.main import app, DECISION_CACHE

client = TestClient(app)

def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "supremeai-tiny-brain"
    assert data["status"] == "online"
    assert data["memory_profile"] == "512MB-optimized"

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "cache_size" in data

def test_route_task_caching():
    DECISION_CACHE.clear()
    payload = {
        "task": "summarize simple text",
        "complexity": "low",
        "preferred_provider": "auto",
        "context_length": 100
    }
    # First call - not cached
    res1 = client.post("/v1/brain/route", json=payload)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["cached"] is False
    assert "google/gemma" in data1["recommended_model"]

    # Second call - cached
    res2 = client.post("/v1/brain/route", json=payload)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["cached"] is True

def test_evaluate_options():
    payload = {
        "prompt": "We need to fix a critical database connection bug immediately",
        "options": [
            "fix database connection issue",
            "redesign frontend button css",
            "update documentation readme"
        ]
    }
    res = client.post("/v1/brain/evaluate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["selected_option"] == "fix database connection issue"
    assert data["confidence"] > 0.5
