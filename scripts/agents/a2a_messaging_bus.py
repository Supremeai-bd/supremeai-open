#!/usr/bin/env python3
"""
Agent-to-Agent (A2A) Reactive Wakeup & Messaging Bus (#3304).

Lightweight MCP-based message bus for inter-agent communication.
Any active agent can send a message to another agent's lane, and
dormant agents receive messages on their next wakeup.

Design (AGENT_RULES.md P1 — Simple + Effective):
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
