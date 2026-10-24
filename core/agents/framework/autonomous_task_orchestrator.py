from typing import Any

from admin.god import AdminGodLayer
from brain.autonomous_agent import AutonomousAgent
from brain.model_router import ModelRouter
from brain.reasoning_orchestrator import ReasoningOrchestrator
from core.config import settings
from core.intent import IntentClassifier
from core.logging_config import logger
from tools.security_tools.vpn_switcher import VPNRotator


class AutonomousTaskOrchestrator:
    """Autonomous Task Orchestrator with VPN rotation, intent routing and episodic memory."""

    def __init__(
        self,
        admin: AdminGodLayer | None = None,
        model_router: ModelRouter | None = None,
        intent_clf: IntentClassifier | None = None,
        admin_god: AdminGodLayer | None = None,
    ):
        self.admin = admin or admin_god
        self.model_router = model_router or ModelRouter()
        self.intent_clf = intent_clf or IntentClassifier()
        self.reasoning_orchestrator = ReasoningOrchestrator()
        self.autonomous_agent = AutonomousAgent()
        self.vpn_rotator = VPNRotator()

    def _maybe_rotate_vpn(self, task_type: str) -> None:
        try:
            if not getattr(settings, "vpn_endpoints", None):
                return
            sensitive = ["completion", "voice", "realtime", "browser"]
            if task_type in sensitive:
                rotation = self.vpn_rotator.rotate()
                endpoint = rotation.get("endpoint")
                if endpoint:
                    logger.info(f"VPN rotated for {task_type} -> {endpoint}")
        except Exception as exc:
            logger.warning(f"VPN rotation skipped: {exc}")

    def run_autonomous(self, task_description: str, context: str | None = None) -> dict[str, Any]:
        self._maybe_rotate_vpn("general")
        run = self.autonomous_agent.run(task_description=task_description, context=context)
        try:
            self.reasoning_orchestrator.episodic_memory.store_episode(
                event_type="autonomous_run",
                context=task_description,
                outcome="success" if run.get("run", {}).get("success") else "failed",
                importance=1.0 if run.get("run", {}).get("success") else 0.2,
            )
        except Exception as exc:
            logger.exception(f"Failed to store episodic memory: {exc}")
        return run

    def route_reasoning(self, task_description: str, context: str | None = None) -> dict[str, Any]:
        self._maybe_rotate_vpn("general")
        return self.reasoning_orchestrator.route(task_description=task_description, context=context)

    def execute_task(self, task: str, task_type: str = "general") -> dict[str, Any]:
        self._maybe_rotate_vpn(task_type)
        try:
            if self.admin:
                self.admin.enforce("execute")
        except PermissionError as exc:
            return {"success": False, "result": f"Blocked: {exc}", "cost": 0.0}

        intent = self.intent_clf.classify(task)
        effective_type = task_type
        if intent.task_type != "general" and task_type == "general":
            effective_type = intent.task_type.value

        raw = self.model_router.route_and_generate(
            prompt=task,
            task_type=effective_type,
            max_cost=0.01,
        )

        if not raw.get("success"):
            return {
                "success": False,
                "result": raw.get("error", "Unknown upstream error"),
                "cost": raw.get("cost", 0.0),
                "provider": raw.get("provider"),
            }

        return {
            "success": True,
            "completed": True,
            "current_step": "completed",
            "result": raw.get("text", ""),
            "cost": raw.get("cost", 0.0),
            "provider": raw.get("provider"),
        }


# Backward compatibility alias
SupremeOrchestrator = AutonomousTaskOrchestrator
