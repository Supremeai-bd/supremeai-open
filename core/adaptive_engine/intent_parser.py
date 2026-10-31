from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.logging_config import logger

if TYPE_CHECKING:
    # ModelRouter is only a type annotation here (the constructor accepts any
    # router object with a route_and_generate method, and offline tests inject
    # a stub). Importing it eagerly chains model_router ->
    # performance_enhancer -> model_registry -> config_service -> sqlalchemy,
    # which breaks offline stdlib-only consumers (test collection ERROR).
    from core.brain.model_router import ModelRouter


@dataclass
class MetaCognitiveAssessment:
    core_intent: str = "general_task"
    underlying_goal: str = ""
    is_ambiguous: bool = False
    clarification_question: str | None = None
    can_solve_locally: bool = True
    confidence_score: float = 1.0
    boundary_limitations: list[str] = field(default_factory=list)
    is_destructive_or_sensitive: bool = False
    delegation_target: str = "self"
    why_delegated: str = "Can be resolved directly within local context"
    specialist_task_contract: dict[str, Any] = field(default_factory=dict)
    synthesis_guidance: str = ""


@dataclass
class AppSpecification:
    app_type: str = "general"
    secondary_intents: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    tech_stack: dict[str, str] = field(default_factory=dict)
    pages: list[str] = field(default_factory=list)
    integrations: list[str] = field(default_factory=list)
    deployment_target: str | None = None
    clarification_question: str | None = None


class IntentParser:
    def __init__(self, model_router: ModelRouter):
        self.model_router = model_router

    def parse_meta_cognition(
        self, task: str, history: list[dict[str, str]] | None = None
    ) -> MetaCognitiveAssessment:
        task_lower = (task or "").lower().strip()
        if any(w in task_lower for w in ("drop database", "delete production", "purge all secrets", "rm -rf /", "bypass auth", "disable security")):
            return MetaCognitiveAssessment(
                core_intent="destructive_or_security_operation",
                underlying_goal="Execute a potentially irreversible operation",
                is_ambiguous=False,
                clarification_question="This operation is destructive/sensitive. Do you explicitly authorize this change?",
                can_solve_locally=False,
                confidence_score=1.0,
                boundary_limitations=["Destructive operations require explicit human admin approval"],
                is_destructive_or_sensitive=True,
                delegation_target="human_admin",
                why_delegated="Destructive action prohibited without explicit human authorization",
                specialist_task_contract={"action": "confirm_destructive_operation", "risk_level": "CRITICAL"},
                synthesis_guidance="Do not execute until the human provides explicit confirmation.",
            )
        if any(w in task_lower for w in ("train", "finetune", "fine-tune", "lora", "gpu", "heavy compute")):
            return MetaCognitiveAssessment(
                core_intent="heavy_compute_training",
                underlying_goal="Execute model training or heavy compute task",
                is_ambiguous=False,
                can_solve_locally=False,
                boundary_limitations=["Local container lacks GPU / PyTorch execution runtime"],
                delegation_target="kaggle_gpu",
                why_delegated="Task requires GPU resources available on Kaggle cluster",
                specialist_task_contract={"task_type": "model_fine_tuning", "task": task},
                synthesis_guidance="Poll job status until completed and load adapter checkpoint.",
            )
        if any(w in task_lower for w in ("prove", "mathematical proof", "deep reasoning", "formal logic")):
            return MetaCognitiveAssessment(
                core_intent="complex_reasoning",
                underlying_goal="Solve complex logic or mathematical problem",
                is_ambiguous=False,
                can_solve_locally=False,
                boundary_limitations=["Requires multi-step deep reasoning chain"],
                delegation_target="reasoning_model",
                why_delegated="Task benefits from specialized reasoning model",
                specialist_task_contract={"task": task, "prompt": task},
                synthesis_guidance="Verify logical steps before accepting conclusion.",
            )
        if any(w in task_lower for w in ("screenshot", "browser", "dom", "click", "ui test")):
            return MetaCognitiveAssessment(
                core_intent="browser_interaction",
                underlying_goal="Interact with or inspect a live webpage in browser",
                is_ambiguous=False,
                can_solve_locally=False,
                boundary_limitations=["Requires browser viewport and DOM interaction tools"],
                delegation_target="browser_subagent",
                why_delegated="Requires browser execution capabilities",
                specialist_task_contract={"task": task},
                synthesis_guidance="Capture final screenshot and verify DOM state.",
            )
        return MetaCognitiveAssessment(
            core_intent="direct_local_task",
            underlying_goal=task,
            is_ambiguous=len(task.strip()) < 10,
            clarification_question="Could you provide more context on the expected outcome?" if len(task.strip()) < 10 else None,
            can_solve_locally=True,
            delegation_target="self",
            why_delegated="Standard local coding task within agent contract",
            specialist_task_contract={"task": task},
            synthesis_guidance="Verify with unit tests and linter before reporting outcome.",
        )

    def parse_intent(
        self, task: str, history: list[dict[str, str]] | None = None
    ) -> AppSpecification:
        # Construct the context prompt
        context_str = ""
        if history:
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                context_str += f"{role.capitalize()}: {content}\n"

        prompt = f"""You are an Intent Parser for an Adaptive AI System.
Your job is to parse the user's intent into a structured JSON application specification.
If the request is a follow-up, merge it with the existing context.
If the user's request is ambiguous or missing crucial details, ask a clarification question by setting the "clarification_question" field.

History/Context:
{context_str}

New User Instruction: "{task}"

Return ONLY a JSON object (no markdown blocks, no text around it) with the following structure:
{{
  "app_type": "type of app (e.g. content_platform, ecommerce, blog, portfolio)",
  "features": ["list", "of", "features"],
  "tech_stack": {{"frontend": "react/vue/html...", "backend": "fastapi/express...", "database": "postgresql/mongodb..."}},
  "pages": ["page1", "page2"],
  "integrations": ["list of external APIs/services"],
  "deployment_target": "platform name if specified, otherwise null",
  "clarification_question": "optional question to clarify if intent is highly ambiguous, otherwise null"
}}
"""
        response = self.model_router.route_and_generate(prompt, task_type="general", max_cost=0.01)
        text = response.get("text", "{}").strip()

        # Clean markdown code block wraps if LLM returns them
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
            return AppSpecification(
                app_type=data.get("app_type", "general"),
                secondary_intents=data.get("secondary_intents", []),
                features=data.get("features", []),
                tech_stack=data.get("tech_stack", {}),
                pages=data.get("pages", []),
                integrations=data.get("integrations", []),
                deployment_target=data.get("deployment_target"),
                clarification_question=data.get("clarification_question"),
            )
        except Exception as e:
            logger.error(f"Failed to parse JSON specification from: {text}. Error: {e}")
            # Fallback to basic spec
            return AppSpecification(
                app_type="general",
                clarification_question="Can you describe your project in more detail?",
            )

    def extract_goal(self, prompt: str) -> dict[str, Any]:
        return {"goal": "general", "confidence": 0.5}

    @classmethod
    async def extract_context(cls, pref: Any) -> dict[str, Any]:
        """Extract structured context from a preference update payload."""
        if hasattr(pref, "dict"):
            data = pref.dict(exclude_none=True)
        elif isinstance(pref, dict):
            data = pref
        else:
            data = {}
        return {
            "source": "user_preferences",
            "modified_fields": list(data.keys()),
            "theme_preference": data.get("theme"),
            "model_preference": data.get("default_model"),
        }
