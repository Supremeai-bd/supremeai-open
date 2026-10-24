"""This module provides the `GenerationMonitor` class, a crucial component within the SupremeAI project for ensuring the quality, reliability, and consistency of AI-generated content. It offers a suite of tools to monitor various aspects of AI output, including token confidence, the identification and flagging of factual claims for verification, enforcement of source attribution, and detection of potential contradictions within conversational contexts, thereby acting as a vital quality assurance layer.

Key Components:
- `GenerationMonitor`: Manages various quality assurance checks for AI-generated text, including confidence, factual claims, attribution, and consistency.
- `track_token_confidence()`: Evaluates the confidence level of individual tokens and flags those below a predefined threshold.
- `flag_factual_claims()`: Identifies potential factual statements within a given text using regular expressions.
- `require_source_attribution()`: Checks if identified factual claims in a text are accompanied by explicit source attributions.
- `check_consistency()`: Compares new text against recent conversation history to detect potential contradictions or inconsistencies.
- `track_agent_call()`: Logs details of agent calls for monitoring and debugging purposes.

Dependencies:
- `re`: For regular expression operations used in text analysis."""

import re

from core.logging_config import logger


class GenerationMonitor:
    def __init__(self):
        self.confidence_threshold = 0.7

    def track_token_confidence(self, token: str, probability: float) -> dict:
        if probability < self.confidence_threshold:
            return {
                "is_low_confidence": True,
                "token": token,
                "probability": probability,
                "suggestion": "Flag for review",
            }
        return {"is_low_confidence": False}

    def flag_factual_claims(self, text: str) -> list:
        fact_patterns = [
            r"\b(is|are|was|were)\s+\w+",
            r"\b(has|have|had)\s+\w+",
            r"\d+\s+(percent|%|million|billion)",
        ]
        claims = []
        for pattern in fact_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                claims.append(
                    {
                        "claim": match.group(),
                        "position": match.span(),
                        "needs_verification": True,
                    }
                )
        return claims

    def require_source_attribution(self, text: str) -> dict:
        claims = self.flag_factual_claims(text)
        unattributed = []
        for claim in claims:
            surrounding_text = text[max(0, claim["position"][0] - 100) : claim["position"][1] + 100]
            if not re.search(r"\[Source:\s*\w+\]", surrounding_text):
                unattributed.append(claim)
        return {
            "unattributed_claims": unattributed,
            "must_add_sources": len(unattributed) > 0,
        }

    def check_consistency(self, new_text: str, conversation_history: list) -> dict:
        has_contradictions = False
        contradictions = []
        for prev in conversation_history[-5:]:
            if (
                "not" in new_text.lower()
                and "not" not in prev.lower()
                and len(set(new_text.split()) & set(prev.split())) > 5
            ):
                has_contradictions = True
                contradictions.append(f"Potential contradiction between: '{new_text}' and '{prev}'")
        return {
            "has_contradictions": has_contradictions,
            "contradictions": contradictions,
        }

    def track_agent_call(self, **kwargs):
        logger.info("--- AGENT CALL ---")
        for key, value in kwargs.items():
            logger.info(f"{key}: {value}")
        logger.info("--------------------")
