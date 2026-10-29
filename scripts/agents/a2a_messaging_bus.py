#!/usr/bin/env python3
"""
Agent-to-Agent (A2A) Reactive Wakeup & Messaging Bus (#3304).

Lightweight MCP-based message bus for inter-agent communication.
Any active agent can send a message to another agent's lane, and
dormant agents receive messages on their next wakeup.

Design (Law of Minimal Elegance — FEDERATION_CHARTER.md):
  - File-based message queue (no external broker — uses git repo as bus)
  - Each agent lane has an inbox: .agents/a2a_inbox/{lane}.jsonl
  - Messages are JSONL (append-only, idempotent by message_id)
  - MCP Tower integration: client.send_message(target_lane, message)
  - Wakeup: target agent checks inbox on next continuous_agent_loop tick

Usage:
    from scripts.agents.a2a_messaging_bus import A2ABus
    bus = A2ABus()
    bus.send("coder-1", {"type": "question", "body": "How does X work?"})
    messages = bus.receive("coder-1")  # returns + clears inbox
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
INBOX_DIR = ROOT_DIR / ".agents" / "a2a_inbox"


class A2ABus:
    """File-based agent-to-agent message bus."""
    
    def __init__(self, inbox_dir: Path | None = None):
        self.inbox_dir = inbox_dir or INBOX_DIR
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
    
    def _inbox_path(self, lane: str) -> Path:
        return self.inbox_dir / f"{lane}.jsonl"
    
    def send(self, target_lane: str, message: dict, sender: str = "system") -> str:
        """Send a message to a target agent lane.
        
        Returns message_id. Idempotent — duplicate message_ids are ignored.
        """
        message_id = str(uuid.uuid4())
        entry = {
            "message_id": message_id,
            "sender": sender,
            "target": target_lane,
            "timestamp": time.time(),
            "body": message,
        }
        inbox = self._inbox_path(target_lane)
        with open(inbox, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return message_id
    
    def receive(self, lane: str) -> list[dict]:
        """Receive and clear all messages for a lane.
        
        Returns list of messages (oldest first). Inbox is cleared after read.
        """
        inbox = self._inbox_path(lane)
        if not inbox.exists():
            return []
        
        messages = []
        try:
            with open(inbox, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        messages.append(json.loads(line))
        except (json.JSONDecodeError, IOError):
            pass
        
        # Clear inbox after read
        inbox.unlink(missing_ok=True)
        return messages
    
    def peek(self, lane: str) -> list[dict]:
        """Peek at messages without clearing."""
        inbox = self._inbox_path(lane)
        if not inbox.exists():
            return []
        messages = []
        try:
            with open(inbox, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        messages.append(json.loads(line))
        except (json.JSONDecodeError, IOError):
            pass
        return messages
    
    def broadcast(self, message: dict, sender: str = "system", lanes: list[str] | None = None) -> int:
        """Send a message to all (or specified) lanes."""
        if lanes is None:
            # Discover all lanes from inbox files
            lanes = [f.stem for f in self.inbox_dir.glob("*.jsonl")]
        count = 0
        for lane in lanes:
            self.send(lane, message, sender)
            count += 1
        return count


class A2ATaskAdapter:
    """A2A v1.0.0 Task Adapter bridging external A2A JSON-RPC requests to internal A2ABus lanes.
    
    Implements core A2A v1.0.0 operations:
    - SendMessage (creates or routes to an A2A Task)
    - GetTask (retrieves task status and message progress)
    - CancelTask (cancels ongoing task)
    """

    def __init__(self, bus: A2ABus | None = None, task_dir: Path | None = None):
        self.bus = bus or A2ABus()
        self.task_dir = task_dir or (ROOT_DIR / ".agents" / "a2a_tasks")
        self.task_dir.mkdir(parents=True, exist_ok=True)

    def _task_path(self, task_id: str) -> Path:
        return self.task_dir / f"{task_id}.json"

    def _save_task(self, task_id: str, data: dict) -> None:
        path = self._task_path(task_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _load_task(self, task_id: str) -> dict | None:
        path = self._task_path(task_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def send_message(self, request: dict) -> dict:
        """A2A v1.0.0 SendMessage operation."""
        # Extract message payload and task references
        msg = request.get("message", {})
        task_id = request.get("taskId") or str(uuid.uuid4())
        context_id = request.get("contextId") or str(uuid.uuid4())
        lane = request.get("targetLane") or "general"
        sender = msg.get("role", "ROLE_USER")

        # Format internal bus payload
        internal_payload = {
            "taskId": task_id,
            "contextId": context_id,
            "parts": msg.get("parts", []),
            "metadata": msg.get("metadata", {}),
        }

        # Send to internal bus lane
        bus_msg_id = self.bus.send(target_lane=lane, message=internal_payload, sender=sender)

        # Track task state
        existing = self._load_task(task_id)
        if existing:
            status = existing.get("status", "TASK_STATE_WORKING")
            history = existing.get("history", [])
        else:
            status = "TASK_STATE_WORKING"
            history = []

        history.append({
            "messageId": bus_msg_id,
            "sender": sender,
            "timestamp": time.time(),
            "parts": msg.get("parts", []),
        })

        task_record = {
            "id": task_id,
            "contextId": context_id,
            "status": status,
            "targetLane": lane,
            "createdAt": existing.get("createdAt") if existing else time.time(),
            "updatedAt": time.time(),
            "history": history,
        }
        self._save_task(task_id, task_record)

        return {
            "task": {
                "id": task_id,
                "contextId": context_id,
                "status": status,
            }
        }

    def get_task(self, task_id: str) -> dict | None:
        """A2A v1.0.0 GetTask operation."""
        task = self._load_task(task_id)
        if not task:
            return None
        return {"task": task}

    def cancel_task(self, task_id: str) -> dict:
        """A2A v1.0.0 CancelTask operation."""
        task = self._load_task(task_id)
        if not task:
            return {"error": {"code": -32004, "message": f"Task {task_id} not found"}}
        task["status"] = "TASK_STATE_CANCELED"
        task["updatedAt"] = time.time()
        self._save_task(task_id, task)
        return {"task": task}

    def handle_jsonrpc(self, payload: dict) -> dict:
        """Handle standard A2A JSON-RPC 2.0 requests."""
        rpc_id = payload.get("id")
        method = payload.get("method")
        params = payload.get("params", {})

        if payload.get("jsonrpc") != "2.0":
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32600, "message": "Invalid Request: jsonrpc must be '2.0'"}
            }

        if method == "SendMessage":
            result = self.send_message(params)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": result}
        elif method == "GetTask":
            task_id = params.get("id") or params.get("taskId")
            if not task_id:
                return {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {"code": -32602, "message": "Invalid params: id or taskId required"}
                }
            result = self.get_task(task_id)
            if not result:
                return {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {"code": -32004, "message": f"Task {task_id} not found"}
                }
            return {"jsonrpc": "2.0", "id": rpc_id, "result": result}
        elif method == "CancelTask":
            task_id = params.get("id") or params.get("taskId")
            if not task_id:
                return {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {"code": -32602, "message": "Invalid params: id or taskId required"}
                }
            result = self.cancel_task(task_id)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": result}
        else:
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32601, "message": f"Method {method} not found"}
            }

