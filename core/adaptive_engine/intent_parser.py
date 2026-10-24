import json
from dataclasses import dataclass, field
from typing import Any

from brain.model_router import ModelRouter
from core.logging_config import logger


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
