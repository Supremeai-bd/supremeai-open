import uuid
from typing import Any

from core.logging_config import logger


class ConversationManager:
    def __init__(self):
        self.sessions: dict[str, dict[str, Any]] = {}
        logger.info("Initialized ConversationManager")

    def create_session(self) -> str:
        session_id = uuid.uuid4().hex
        self.sessions[session_id] = {
            "history": [],
            "summary": "Start of conversation.",
            "entities": {},
        }
        return session_id

    def add_message(self, session_id: str, role: str, content: str, max_history: int = 10) -> int:
        if session_id not in self.sessions:
            raise ValueError(f"Invalid session {session_id}")
        if len(content) > 4000:
            content = content[:4000] + "...[truncated]"
        session = self.sessions[session_id]
        session["history"].append({"role": role, "content": content})
        idx = len(session["history"]) - 1
        if len(session["history"]) > max_history:
            old_msg = session["history"].pop(0)
            prev = session.get("summary", "")
            session["summary"] = f"{prev} [{old_msg['role']}: {old_msg['content'][:60]}...]".strip()
            if len(session["summary"]) > 2000:
                session["summary"] = session["summary"][:2000]
            idx -= 1
        if role == "user":
            for word in content.split():
                if len(word) > 3 and word.lower() not in {
                    "this",
                    "that",
                    "with",
                    "have",
                }:
                    session["entities"][word.lower()] = session["entities"].get(word.lower(), 0) + 1
        return max(0, idx)

    def create_conversation(self, user_id: str = "default") -> str:
        sid = self.create_session()
        self.sessions[sid]["user_id"] = user_id
        return sid

    def update_message(self, session_id: str, index_or_id: int | None = 0, content: str = ""):
        idx = 0 if index_or_id is None else index_or_id
        if session_id in self.sessions and 0 <= idx < len(self.sessions[session_id]["history"]):
            self.sessions[session_id]["history"][idx]["content"] = content

    def delete_message(self, session_id: str, index: int):
        if session_id in self.sessions and 0 <= index < len(self.sessions[session_id]["history"]):
            self.sessions[session_id]["history"].pop(index)

    def get_history(self, session_id: str) -> list[dict[str, str]]:
        if session_id not in self.sessions:
            return []
        return self.sessions[session_id]["history"]

    def get_context(self, session_id: str) -> list[dict[str, str]]:
        if session_id not in self.sessions:
            return []
        session = self.sessions[session_id]
        context: list[dict[str, str]] = []
        if session.get("summary"):
            context.append({"role": "system", "content": f"Previous context: {session['summary']}"})
        context.extend(session["history"])
        return context
