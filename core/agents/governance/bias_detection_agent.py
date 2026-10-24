"""
Bias Detection Agent for SupremeAI 2.0
Identifies and mitigates algorithmic biases in AI decisions and outputs.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.cache.redis_manager import redis_manager
from core.config_cache import config_cache
from core.llm.token_deductor import TokenDeductor
from core.logging_config import logger


@dataclass
class BiasDetectionResult:
    """Data class to hold bias detection results."""

    content_analyzed: str
    bias_types_detected: list[str]
    severity_score: float  # 0.0 to 1.0
    affected_groups: list[str]
    suggested_mitigations: list[str]
    confidence: float
    timestamp: datetime


class BiasDetectionAgent:
    """Agent that identifies and mitigates algorithmic biases."""

    def __init__(self):
        self.name = "Bias Detection Agent"
        self.token_deductor = TokenDeductor()
        self.bias_detection_key = "bias_detection:results"
        self.max_results = 100

        # Define common bias types and keywords
        self.bias_keywords = {
            "gender_bias": [
                r"\b(male|female|man|woman|boy|girl|he|she|him|her|his|hers)\b",
                r"\b(guys|ladies|gentlemen|ma'am|sir)\b",
                r"\b(gender|sex|masculine|feminine)\b",
            ],
            "racial_ethnic_bias": [
                r"\b(black|white|asian|hispanic|latino|latina|african|european|american|indian|chinese|japanese)\b",
                r"\b(race|ethnicity|minority|majority|diversity|inclusion)\b",
            ],
            "age_bias": [
                r"\b(old|young|elderly|senior|junior|child|adult|teen|millennial|boomer)\b",
                r"\b(age|generation|born in)\b",
            ],
            "socioeconomic_bias": [
                r"\b(rich|poor|wealthy|affluent|low-income|upper-class|working-class)\b",
                r"\b(income|class|money|financial|economic)\b",
            ],
            "geographic_bias": [
                r"\b(urban|rural|city|countryside|metropolitan|remote)\b",
                r"\b(location|region|area|district|neighborhood)\b",
            ],
            "ability_bias": [
                r"\b(disabled|abled|handicap|wheelchair|blind|deaf|able-bodied)\b",
                r"\b(disability|accessibility|accommodation)\b",
            ],
        }

        self.mitigation_strategies = {
            "gender_bias": [
                "Use gender-neutral language where possible",
                "Ensure equal representation in examples",
                "Review for stereotypical associations",
            ],
            "racial_ethnic_bias": [
                "Avoid generalizations about ethnic groups",
                "Include diverse perspectives in training data",
                "Audit for disparate impact",
            ],
            "age_bias": [
                "Avoid ageist language or assumptions",
                "Represent all age groups fairly",
                "Challenge age-based stereotypes",
            ],
            "socioeconomic_bias": [
                "Avoid assumptions based on economic status",
                "Consider diverse economic backgrounds",
                "Ensure equitable access to services",
            ],
            "geographic_bias": [
                "Consider diverse geographic contexts",
                "Avoid urban-centric perspectives",
                "Account for rural/remote needs",
            ],
            "ability_bias": [
                "Use respectful language about disabilities",
                "Follow disability-first language guidelines",
                "Ensure accessibility considerations",
            ],
        }

    async def detect_bias(
        self, content: str, context: str = "", sensitive_topics: list[str] | None = None
    ) -> BiasDetectionResult:
        """
        Detect potential biases in the given content.

        Args:
            content: Content to analyze for bias
            context: Additional context for analysis
            sensitive_topics: Specific topics to focus on

        Returns:
            BiasDetectionResult containing bias analysis
        """
        try:
            detected_bias_types = []
            affected_groups = []
            total_matches = 0

            # Perform keyword-based bias detection
            for bias_type, patterns in self.bias_keywords.items():
                matches_found = 0
                for pattern in patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    matches_found += len(matches)

                    if matches:
                        # Extract affected groups from matches
                        for match in matches:
                            if match.lower() not in affected_groups:
                                affected_groups.append(match.lower())

                if matches_found > 0:
                    detected_bias_types.append(bias_type)
                    total_matches += matches_found

            # Calculate severity score based on matches and content length
            content_length = len(content.split())
            severity_score = min(total_matches / max(content_length / 100, 1), 1.0)

            # If no keyword matches but content seems sensitive, use LLM for deeper analysis
            if not detected_bias_types and content_length > 10:
                llm_result = await self._analyze_with_llm(content, context)
                detected_bias_types.extend(llm_result["bias_types"])
                affected_groups.extend(llm_result["affected_groups"])
                severity_score = max(severity_score, llm_result["severity"])

            # Get suggested mitigations
            suggested_mitigations = []
            for bias_type in detected_bias_types:
                if bias_type in self.mitigation_strategies:
                    suggested_mitigations.extend(self.mitigation_strategies[bias_type])

            # Create result object
            result = BiasDetectionResult(
                content_analyzed=content[:200] + "..." if len(content) > 200 else content,
                bias_types_detected=detected_bias_types,
                severity_score=round(severity_score, 2),
                affected_groups=list(set(affected_groups)),
                suggested_mitigations=list(set(suggested_mitigations)),
                confidence=0.8 if detected_bias_types else 0.3,
                timestamp=datetime.utcnow(),
            )

            # Store result in history
            await self._store_bias_result(result)

            logger.info(f"Bias detection completed. Types found: {detected_bias_types}")
            return result

        except Exception as e:
            logger.error(f"Error in bias detection: {e}")
            # Return a neutral result in case of error
            return BiasDetectionResult(
                content_analyzed=content[:200] + "..." if len(content) > 200 else content,
                bias_types_detected=[],
                severity_score=0.0,
                affected_groups=[],
                suggested_mitigations=["Error occurred during bias analysis"],
                confidence=0.0,
                timestamp=datetime.utcnow(),
            )

    async def _analyze_with_llm(self, content: str, context: str) -> dict[str, Any]:
        """Use LLM for deeper bias analysis."""
        try:
            prompt = f"""
            Analyze the following content for potential biases. Consider the context provided.

            Content: {content}

            Context: {context}

            Identify specific types of bias that might be present (gender, racial, age, socioeconomic, geographic, ability).
            Also identify which groups might be affected by these biases.
            Rate the severity on a scale of 0 to 1.

            Respond in the following JSON format:
            {{
              "bias_types": ["type1", "type2"],
              "affected_groups": ["group1", "group2"],
              "severity": 0.5
            }}
            """

            from core.llm.language_model import LanguageModel

            lm = LanguageModel()
            result = await lm.generate(
                prompt,
                max_tokens=config_cache.get("bias_detection_agent_max_tokens", 300),
                temperature=config_cache.get("bias_detection_agent_temperature", 0.2),
            )

            response_text = result.get("text", "")

            # Extract JSON from response
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}") + 1

            if start_idx != -1 and end_idx != 0:
                json_str = response_text[start_idx:end_idx]
                parsed = json.loads(json_str)
                return parsed
            else:
                return {"bias_types": [], "affected_groups": [], "severity": 0.0}
        except Exception as e:
            logger.error(f"Error in LLM bias analysis: {e}")
            return {"bias_types": [], "affected_groups": [], "severity": 0.0}

    async def _store_bias_result(self, result: BiasDetectionResult):
        """Store bias detection result in Redis."""
        try:
            result_data = {
                "content_analyzed": result.content_analyzed,
                "bias_types_detected": result.bias_types_detected,
                "severity_score": result.severity_score,
                "affected_groups": result.affected_groups,
                "suggested_mitigations": result.suggested_mitigations,
                "confidence": result.confidence,
                "timestamp": result.timestamp.isoformat(),
            }

            # Retrieve existing results
            existing_results = await redis_manager.get(self.bias_detection_key)
            if existing_results:
                results_list = json.loads(existing_results)
            else:
                results_list = []

            # Add new result
            results_list.append(result_data)

            # Keep only the last N results
            if len(results_list) > self.max_results:
                results_list = results_list[-self.max_results :]

            # Store back to Redis
            await redis_manager.set_with_ttl(
                self.bias_detection_key,
                json.dumps(results_list),
                ttl=86400,  # 24 hours
            )
        except Exception as e:
            logger.error(f"Error storing bias detection result: {e}")

    async def get_bias_history(self, limit: int = 10) -> list[BiasDetectionResult]:
        """Retrieve recent bias detection results from history."""
        try:
            history = await redis_manager.get(self.bias_detection_key)
            if not history:
                return []

            history_list = json.loads(history)
            results = []

            # Convert back to BiasDetectionResult objects
            for item in reversed(history_list[-limit:]):  # Most recent first
                results.append(
                    BiasDetectionResult(
                        content_analyzed=item["content_analyzed"],
                        bias_types_detected=item["bias_types_detected"],
                        severity_score=item["severity_score"],
                        affected_groups=item["affected_groups"],
                        suggested_mitigations=item["suggested_mitigations"],
                        confidence=item["confidence"],
                        timestamp=datetime.fromisoformat(item["timestamp"]),
                    )
                )

            return results
        except Exception as e:
            logger.error(f"Error retrieving bias detection history: {e}")
            return []

    async def assess_mitigation_effectiveness(
        self, original_content: str, mitigated_content: str
    ) -> dict[str, Any]:
        """
        Assess how effective the mitigation was by comparing before/after.

        Args:
            original_content: Content before mitigation
            mitigated_content: Content after mitigation

        Returns:
            Dictionary with effectiveness assessment
        """
        original_result = await self.detect_bias(original_content)
        mitigated_result = await self.detect_bias(mitigated_content)

        improvement = original_result.severity_score - mitigated_result.severity_score
        effectiveness_score = max(
            0.0,
            min(
                1.0,
                improvement / original_result.severity_score
                if original_result.severity_score > 0
                else 0,
            ),
        )

        return {
            "original_severity": original_result.severity_score,
            "mitigated_severity": mitigated_result.severity_score,
            "improvement": improvement,
            "effectiveness_score": round(effectiveness_score, 2),
            "bias_reduction_percentage": round(
                (improvement / original_result.severity_score) * 100
                if original_result.severity_score > 0
                else 0,
                2,
            ),
            "remaining_bias_types": mitigated_result.bias_types_detected,
        }


# Global instance
bias_detection_agent = BiasDetectionAgent()
