from __future__ import annotations

from typing import Any


class CodingAgent:
    def __init__(self, model_router: Any) -> None:
        self.role = "coding-expert"
        self.backstory = "Senior engineer focused on correctness and maintainability."
        self.model_router = model_router

    def execute(self, description: str, context: str = "") -> dict[str, Any]:
        prompt = f"R-A-C-E Framework\nRole: {self.role}\nAction: {description}\nContext: {context}\nExpectation: Return implementation with tests."
        try:
            raw = self.model_router.route_and_generate(
                prompt=prompt, task_type="coding", max_cost=0.01
            )
            if raw.get("success") or raw.get("text"):
                return {
                    "role": self.role,
                    "success": True,
                    "output": raw.get("text", ""),
                    "provider": raw.get("provider"),
                    "cost": raw.get("cost", 0.0),
                }
            return {
                "role": self.role,
                "success": False,
                "error": raw.get("error", "unknown"),
            }
        except Exception as exc:  # pylint: disable=broad-except
            return {"role": self.role, "success": False, "error": str(exc)}


class ReviewAgent:
    def __init__(self, model_router: Any) -> None:
        self.role = "code-reviewer"
        self.backstory = "Reviewer enforcing quality, security, and performance."
        self.model_router = model_router

    def execute(self, description: str, context: str = "") -> dict[str, Any]:
        prompt_template = (
            "C-L-E-A-R Framework\n"
            "Role: {role}\n"
            "Context: {context}\n"
            "Action: {description}\n"
            "Expectation: Review findings with severity and suggested fixes."
        )
        prompt_params = {
            "role": self.role,
            "description": description,
            "context": context,
        }
        try:
            raw = self.model_router.route_and_generate(
                prompt_template=prompt_template,
                prompt_params=prompt_params,
                task_type="code",
                max_cost=0.01,
            )
            if raw.get("success") or raw.get("text"):
                return {
                    "role": self.role,
                    "success": True,
                    "output": raw.get("text", ""),
                    "provider": raw.get("provider"),
                    "cost": raw.get("cost", 0.0),
                    "prompt_version": raw.get("prompt_version"),
                }
            return {
                "role": self.role,
                "success": False,
                "error": raw.get("error", "unknown"),
            }
        except Exception as exc:  # pylint: disable=broad-except
            return {"role": self.role, "success": False, "error": str(exc)}


class QAAgent:
    def __init__(self, model_router: Any) -> None:
        self.role = "qa-engineer"
        self.backstory = "QA specialist ensuring coverage and edge cases."
        self.model_router = model_router

    def execute(self, description: str, context: str = "") -> dict[str, Any]:
        prompt = (
            "S-T-A-R Framework\n"
            f"Situation: Existing application code.\n"
            f"Task: {description}\n"
            f"Action: Design tests and analyze risk.\n"
            f"Result: Test cases and report.\n"
            f"Context: {context}"
        )
        try:
            raw = self.model_router.route_and_generate(
                prompt=prompt, task_type="testing", max_cost=0.01
            )
            if raw.get("success") or raw.get("text"):
                return {
                    "role": self.role,
                    "success": True,
                    "output": raw.get("text", ""),
                    "provider": raw.get("provider"),
                    "cost": raw.get("cost", 0.0),
                }
            return {
                "role": self.role,
                "success": False,
                "error": raw.get("error", "unknown"),
            }
        except Exception as exc:  # pylint: disable=broad-except
            return {"role": self.role, "success": False, "error": str(exc)}


class AgentDepartment:
    def __init__(self, model_router: Any) -> None:
        self.model_router = model_router
        self.agents = {
            "coding": CodingAgent(model_router),
            "review": ReviewAgent(model_router),
            "qa": QAAgent(model_router),
        }

    def run(self, department: str, task: str, context: str = "") -> dict[str, Any]:
        agent = self.agents.get(department)
        if not agent:
            return {"success": False, "error": f"Unknown department: {department}"}
        return agent.execute(description=task, context=context)
