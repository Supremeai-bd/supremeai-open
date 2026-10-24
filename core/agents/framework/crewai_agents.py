from collections.abc import Sequence
from typing import Optional

from brain.model_router import ModelRouter
from core.logging_config import logger


class CrewTask:
    def __init__(self, description: str, agent: Optional["CrewAgent"] = None, context: str = ""):
        self.description = description
        self.agent = agent
        self.context = context
        self.output: str = ""


class CrewAgent:
    def __init__(
        self,
        role: str,
        model_router: ModelRouter | None = None,
        goal: str = "",
        backstory: str = "",
    ):
        self.role = role
        self.goal = goal
        self.backstory = backstory
        self.model_router = model_router or ModelRouter()

    def execute(self, description: str, context: str = "") -> str:
        prompt = (
            f"You are a {self.role} agent.\n"
            f"Goal: {self.goal}\n"
            f"Backstory: {self.backstory}\n"
            f"Task: {description}\n"
            f"Context: {context}\n"
            "Provide a concise, actionable output."
        )
        try:
            raw = self.model_router.route_and_generate(
                prompt=prompt,
                task_type="general",
                max_cost=0.005,
            )
            if raw.get("success") or raw.get("text"):
                return raw.get("text", "")
            return f"Error: {raw.get('error', 'unknown')}"
        except Exception as exc:
            logger.error(f"CrewAgent '{self.role}' failed: {exc}")
            return f"Error: {exc}"


class SupremeCrew:
    def __init__(self, agents: Sequence[CrewAgent], tasks: Sequence[CrewTask]):
        self.agents = {agent.role: agent for agent in agents}
        self.tasks = list(tasks)

    def kickoff(self) -> str:
        outputs = []
        for task in self.tasks:
            agent = task.agent
            if agent is None:
                continue
            result = agent.execute(task.description, task.context)
            task.output = result
            outputs.append(result)
        return "\n".join(outputs)
