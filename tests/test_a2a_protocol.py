import json
import pytest
from pathlib import Path
from scripts.agents.a2a_messaging_bus import A2ABus, A2ATaskAdapter

def test_agent_card_structure():
    card_path = Path(__file__).resolve().parents[1] / "gateway" / "well-known" / "agent-card.json"
    assert card_path.exists(), "Agent card must exist at gateway/well-known/agent-card.json"
    
    with open(card_path, "r", encoding="utf-8") as f:
        card = json.load(f)
        
    assert card.get("name")
    assert card.get("description")
    assert card.get("protocolVersion") == "1.0.0"
    assert "supportedInterfaces" in card
    assert len(card["supportedInterfaces"]) > 0
    assert "capabilities" in card
    assert "skills" in card
    assert len(card["skills"]) > 0

def test_a2a_task_adapter_send_and_get(tmp_path):
    bus_dir = tmp_path / "inbox"
    task_dir = tmp_path / "tasks"
    bus = A2ABus(inbox_dir=bus_dir)
    adapter = A2ATaskAdapter(bus=bus, task_dir=task_dir)

    # Test SendMessage via direct API
    req = {
        "taskId": "task-test-123",
        "contextId": "ctx-456",
        "targetLane": "solver",
        "message": {
            "role": "ROLE_USER",
            "parts": [{"text": "Inspect gateway routing"}]
        }
    }
    res = adapter.send_message(req)
    assert res["task"]["id"] == "task-test-123"
    assert res["task"]["status"] == "TASK_STATE_WORKING"

    # Verify task can be retrieved
    task_res = adapter.get_task("task-test-123")
    assert task_res is not None
    assert task_res["task"]["id"] == "task-test-123"
    assert len(task_res["task"]["history"]) == 1

    # Verify bus message was enqueued in solver lane
    messages = bus.receive("solver")
    assert len(messages) == 1
    assert messages[0]["body"]["taskId"] == "task-test-123"

def test_a2a_task_adapter_cancel(tmp_path):
    bus_dir = tmp_path / "inbox"
    task_dir = tmp_path / "tasks"
    adapter = A2ATaskAdapter(bus=A2ABus(inbox_dir=bus_dir), task_dir=task_dir)

    adapter.send_message({"taskId": "task-cancel-me", "message": {"parts": [{"text": "hi"}]}})
    cancel_res = adapter.cancel_task("task-cancel-me")
    assert cancel_res["task"]["status"] == "TASK_STATE_CANCELED"

    get_res = adapter.get_task("task-cancel-me")
    assert get_res["task"]["status"] == "TASK_STATE_CANCELED"

def test_a2a_jsonrpc_handling(tmp_path):
    bus_dir = tmp_path / "inbox"
    task_dir = tmp_path / "tasks"
    adapter = A2ATaskAdapter(bus=A2ABus(inbox_dir=bus_dir), task_dir=task_dir)

    # SendMessage JSON-RPC
    rpc_req = {
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "SendMessage",
        "params": {
            "taskId": "task-rpc-1",
            "message": {"role": "ROLE_USER", "parts": [{"text": "Execute check"}]}
        }
    }
    rpc_res = adapter.handle_jsonrpc(rpc_req)
    assert rpc_res["jsonrpc"] == "2.0"
    assert rpc_res["id"] == "req-1"
    assert rpc_res["result"]["task"]["id"] == "task-rpc-1"

    # GetTask JSON-RPC
    rpc_get = {
        "jsonrpc": "2.0",
        "id": "req-2",
        "method": "GetTask",
        "params": {"taskId": "task-rpc-1"}
    }
    rpc_get_res = adapter.handle_jsonrpc(rpc_get)
    assert rpc_get_res["result"]["task"]["id"] == "task-rpc-1"

    # Invalid Method
    bad_req = {
        "jsonrpc": "2.0",
        "id": "req-3",
        "method": "NonExistentMethod",
        "params": {}
    }
    bad_res = adapter.handle_jsonrpc(bad_req)
    assert "error" in bad_res
    assert bad_res["error"]["code"] == -32601
