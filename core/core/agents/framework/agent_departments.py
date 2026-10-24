from typing import Any

from brain.model_router import ModelRouter
from core.logging_config import logger

ROLE_PROMPTS: dict[str, str] = {
    "code-reviewer": (
        "You are a senior code reviewer. Use the C-L-E-A-R framework: Context, Learn, "
        "Evaluate, Action, Review. Output findings as a structured review."
    ),
    "coder": (
        "You are an expert software engineer. Use the R-A-C-E framework: Role, Action, "
        "Context, Expectation. Produce implementation code with concise explanations."
    ),
    "architect": "You are a system architect. Use the S-O-A-P framework: Subject, Objective, Action, Plan. Produce architecture guidance and ADRs.",
    "qa": "You are a QA engineer. Use the S-T-A-R framework: Situation, Task, Action, Result. Produce test cases and failure modes.",
    "data": "You are a data engineer. Use the G-R-O-W framework: Goal, Reality, Options, Will. Produce data pipeline plans and validation steps.",
    "security": "You are a security engineer. Enumerate threats, suggest mitigations, and prioritize by severity.",
}


class AgentDepartment:
    def __init__(self, model_router: ModelRouter | None = None) -> None:
        self.model_router = model_router or ModelRouter()

    def list_roles(self) -> list[str]:
        return list(ROLE_PROMPTS.keys())

    def execute(self, role: str, task: str, context: str = "") -> dict[str, Any]:
        role_key = (role or "").lower()
        system_prompt = ROLE_PROMPTS.get(role_key, ROLE_PROMPTS["coder"])
        prompt = f"{system_prompt}\n\nTask: {task}\nContext: {context or 'None'}\n"
        try:
            result = self.model_router.route_and_generate(
                prompt=prompt, task_type="general", max_cost=0.01
            )
            if result.get("success") or result.get("text"):
                return {
                    "role": role_key,
                    "success": True,
                    "output": result.get("text", ""),
                    "cost": result.get("cost", 0.0),
                }
            return {
                "role": role_key,
                "success": False,
                "error": result.get("error", "unknown"),
            }
        except Exception as exc:
            logger.exception("agent department execution failed")
            return {"role": role_key, "success": False, "error": str(exc)}
