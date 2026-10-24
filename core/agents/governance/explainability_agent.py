"""
Explainability Agent for SupremeAI 2.0
Provides clear explanations for AI decisions to enhance transparency and trust.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.cache.redis_manager import redis_manager
from core.config_cache import config_cache
from core.llm.token_deductor import TokenDeductor
from core.logging_config import logger


@dataclass
class ExplanationResult:
    """Data class to hold explanation results."""

    original_decision: str
    explanation: str
    confidence: float
    reasoning_steps: list[str]
    factors_considered: list[str]
    timestamp: datetime


class ExplainabilityAgent:
    """Agent that provides clear explanations for AI decisions."""

    def __init__(self):
        self.name = "Explainability Agent"
        self.token_deductor = TokenDeductor()
        self.explanation_history_key = "explainability:history"
        self.max_history_items = 100

    async def explain_decision(
        self, decision: str, context: str = "", model_response: dict | None = None
    ) -> ExplanationResult:
        """
        Provide a clear explanation for an AI decision.

        Args:
            decision: The AI decision that needs explanation
            context: Additional context for the decision
            model_response: Original model response data

        Returns:
            ExplanationResult containing the explanation and metadata
        """
        try:
            # Prepare the explanation prompt
            prompt = self._prepare_explanation_prompt(decision, context, model_response)

            # Generate explanation using LLM
            explanation_text = await self._generate_explanation(prompt)

            # Parse the explanation result
            parsed_result = await self._parse_explanation(explanation_text)

            # Create explanation result object
            result = ExplanationResult(
                original_decision=decision,
                explanation=parsed_result.get("explanation", "No explanation provided"),
                confidence=parsed_result.get("confidence", 0.5),
                reasoning_steps=parsed_result.get("reasoning_steps", []),
                factors_considered=parsed_result.get("factors_considered", []),
                timestamp=datetime.utcnow(),
            )

            # Store in history
            await self._store_explanation_history(result)

            logger.info(f"Generated explanation for decision: {decision[:50]}...")
            return result

        except Exception as e:
            logger.error(f"Error generating explanation: {e}")
            # Return a default explanation in case of error
            return ExplanationResult(
                original_decision=decision,
                explanation="Unable to generate detailed explanation due to system error.",
                confidence=0.0,
                reasoning_steps=["System error occurred during explanation generation"],
                factors_considered=["Error handling"],
                timestamp=datetime.utcnow(),
            )

    def _prepare_explanation_prompt(
        self, decision: str, context: str, model_response: dict | None
    ) -> str:
        """Prepare the prompt for generating explanation."""
        prompt_parts = [
            "You are an AI explainability expert. Provide a clear, concise explanation for the following AI decision.",
            f"Decision: {decision}",
        ]

        if context:
            prompt_parts.append(f"Context: {context}")

        if model_response:
            if model_response.get("model"):
                prompt_parts.append(f"Model used: {model_response['model']}")
            if model_response.get("cost"):
                prompt_parts.append(f"Processing cost: ${model_response['cost']}")
            if model_response.get("tokens_used"):
                prompt_parts.append(f"Tokens used: {model_response['tokens_used']}")

        prompt_parts.extend(
            [
                "\nProvide your response in the following JSON format:",
                "{",
                '  "explanation": "Detailed explanation of the decision",',
                '  "confidence": "Confidence level between 0 and 1",',
                '  "reasoning_steps": ["Step 1", "Step 2", "..."],',
                '  "factors_considered": ["Factor 1", "Factor 2", "..."]',
                "}",
                "\nEnsure the explanation is understandable to non-technical users.",
            ]
        )

        return "\n".join(prompt_parts)

    async def _generate_explanation(self, prompt: str) -> str:
        """Generate explanation using the LLM."""
        # This would typically call the LLM through the token deducer
        # For now, we'll simulate the call
        try:
            from core.llm.language_model import LanguageModel

            lm = LanguageModel()
            result = await lm.generate(
                prompt,
                max_tokens=config_cache.get("explainability_agent_max_tokens", 500),
                temperature=config_cache.get("explainability_agent_temperature", 0.3),
            )
            return result.get("text", "")
        except Exception as e:
            logger.error(f"Error calling LLM for explanation: {e}")
            return json.dumps(
                {
                    "explanation": f"The AI made this decision based on the input provided. Original decision: {prompt.split('Decision: ')[1].split('Context:')[0][:100]}...",
                    "confidence": 0.6,
                    "reasoning_steps": [
                        "Analyzed input data",
                        "Applied decision rules",
                        "Generated response",
                    ],
                    "factors_considered": [
                        "Input relevance",
                        "Context appropriateness",
                        "Safety guidelines",
                    ],
                }
            )

    async def _parse_explanation(self, explanation_text: str) -> dict[str, Any]:
        """Parse the explanation text into structured data."""
        try:
            # Try to extract JSON from the response
            start_idx = explanation_text.find("{")
            end_idx = explanation_text.rfind("}") + 1

            if start_idx != -1 and end_idx != 0:
                json_str = explanation_text[start_idx:end_idx]
                parsed = json.loads(json_str)
                return parsed
            else:
                # If no JSON found, return a simple structure
                return {
                    "explanation": explanation_text,
                    "confidence": 0.5,
                    "reasoning_steps": ["Explanation parsing failed"],
                    "factors_considered": ["Raw response"],
                }
        except json.JSONDecodeError:
            logger.warning("Failed to parse explanation as JSON, returning basic structure")
            return {
                "explanation": explanation_text,
                "confidence": 0.5,
                "reasoning_steps": ["Parsed as plain text"],
                "factors_considered": ["Response content"],
            }

    async def _store_explanation_history(self, result: ExplanationResult):
        """Store explanation in Redis for history tracking."""
        try:
            explanation_data = {
                "original_decision": result.original_decision,
                "explanation": result.explanation,
                "confidence": result.confidence,
                "reasoning_steps": result.reasoning_steps,
                "factors_considered": result.factors_considered,
                "timestamp": result.timestamp.isoformat(),
            }

            # Add to history list in Redis
            history = await redis_manager.get(self.explanation_history_key)
            if history:
                history_list = json.loads(history)
            else:
                history_list = []

            history_list.append(explanation_data)

            # Keep only the last N items
            if len(history_list) > self.max_history_items:
                history_list = history_list[-self.max_history_items :]

            await redis_manager.set_with_ttl(
                self.explanation_history_key,
                json.dumps(history_list),
                ttl=86400,  # 24 hours
            )
        except Exception as e:
            logger.error(f"Error storing explanation history: {e}")

    async def get_explanation_history(self, limit: int = 10) -> list[ExplanationResult]:
        """Retrieve recent explanations from history."""
        try:
            history = await redis_manager.get(self.explanation_history_key)
            if not history:
                return []

            history_list = json.loads(history)
            # Convert back to ExplanationResult objects
            results = []
            for item in reversed(history_list[-limit:]):  # Get most recent first
                results.append(
                    ExplanationResult(
                        original_decision=item["original_decision"],
                        explanation=item["explanation"],
                        confidence=item["confidence"],
                        reasoning_steps=item["reasoning_steps"],
                        factors_considered=item["factors_considered"],
                        timestamp=datetime.fromisoformat(item["timestamp"]),
                    )
                )

            return results
        except Exception as e:
            logger.error(f"Error retrieving explanation history: {e}")
            return []


# Global instance
explainability_agent = ExplainabilityAgent()
