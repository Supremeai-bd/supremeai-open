import json
import uuid
from typing import Any

from core.logging_config import logger


class AIFederationProtocol:
    """
    Standard protocol for AI-to-AI communication.
    Enables skill sharing, task delegation, and result federation.
    (Closes Gap #87)
    """

    def __init__(self, node_id: str | None = None):
        self.node_id = node_id or f"node-{uuid.uuid4().hex[:8]}"
        self.registry: dict[str, dict[str, Any]] = {}
        self.task_history: list[dict[str, Any]] = []
        logger.info(f"Initialized AIFederationProtocol node: {self.node_id}")

    def register_skill(
        self, skill_name: str, provider_node: str, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        skill_id = f"skill-{uuid.uuid4().hex[:8]}"
        entry = {
            "skill_id": skill_id,
            "skill_name": skill_name,
            "provider_node": provider_node,
            "metadata": metadata,
            "status": "available",
        }
        self.registry[skill_id] = entry
        logger.info(f"Registered skill {skill_name} from {provider_node}")
        return {"status": "success", "skill_id": skill_id}

    def discover_skills(self, query: str) -> list[dict[str, Any]]:
        q = query.lower()
        matches = []
        for skill in self.registry.values():
            text = json.dumps(skill).lower()
            if q in text or q in skill.get("skill_name", "").lower():
                matches.append(skill)
        return matches

    async def delegate_task(self, target_node: str, task: dict[str, Any]) -> dict[str, Any]:
        task_id = task.get("task_id") or f"task-{uuid.uuid4().hex[:8]}"
        task.setdefault("task_id", task_id)
        task.setdefault("delegated_from", self.node_id)
        task.setdefault("delegated_to", target_node)
        task.setdefault("status", "pending")
        logger.info(f"Delegating task {task_id} to {target_node}")
        self.task_history.append(task)
        return {
            "status": "dispatched",
            "task_id": task_id,
            "target_node": target_node,
            "task": task,
        }

    def report_result(self, task_id: str, result: dict[str, Any]) -> dict[str, Any]:
        for task in self.task_history:
            if task.get("task_id") == task_id:
                task["status"] = "completed"
                task["result"] = result
                logger.info(f"Task {task_id} completed by {task.get('delegated_to')}")
                return {"status": "success", "task_id": task_id}
        return {"status": "not_found", "task_id": task_id}

    def get_federation_status(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "skills_registered": len(self.registry),
            "tasks_total": len(self.task_history),
            "tasks_completed": sum(1 for t in self.task_history if t.get("status") == "completed"),
            "tasks_pending": sum(1 for t in self.task_history if t.get("status") == "pending"),
            "peers": list({s.get("provider_node") for s in self.registry.values()}),
        }
