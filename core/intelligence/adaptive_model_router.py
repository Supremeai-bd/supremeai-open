"""SupremeAI Autonomous Intelligent Model Router & Adaptive Decision Engine.

বাংলা: স্বয়ংক্রিয় মডেল রাউটার ও অ্যাডাপ্টিভ ডিসিশন ইঞ্জিন।
ইনকামিং ইউজারের রিকোয়েস্টের ক্যাটাগরি, কোয়ালিটি হিস্ট্রি, লেটেন্সি,
খরচ এবং এপসিলন এক্সপ্লোরেশন নীতি মেনে সর্বোত্তম মডেল নির্ধারণ করে।
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ModelProfile:
    model_id: str
    model_name: str
    category_scores: Dict[str, float] = field(default_factory=dict)  # category -> quality 0-100
    avg_latency_ms: Dict[str, int] = field(default_factory=dict)     # category -> latency ms
    avg_cost_per_1k: float = 0.002
    total_tasks: int = 0
    active: bool = True


@dataclass
class RoutingDecision:
    selected_model: str
    routing_reason: str
    exploration: bool
    confidence_score: float
    fallback_chain: List[str]


class AdaptiveModelRouter:
    """Multi-Armed Bandit / Epsilon-Greedy Adaptive Model Router."""

    def __init__(
        self,
        weight_quality: float = 0.5,
        weight_latency: float = 0.2,
        weight_cost: float = 0.2,
        exploration_rate: float = 0.1,  # 10% exploration
        decay_factor: float = 0.95,
        fallback_chain: Optional[List[str]] = None,
    ):
        self.w_quality = weight_quality
        self.w_latency = weight_latency
        self.w_cost = weight_cost
        self.epsilon = exploration_rate
        self.decay = decay_factor
        self.fallback_chain = fallback_chain or ["qwen2.5_coder", "gemini_flash", "local_tiny_brain"]
        self.models: Dict[str, ModelProfile] = {}

    def register_model(self, profile: ModelProfile) -> None:
        """Register or update model profile in memory registry."""
        self.models[profile.model_id] = profile

    def calculate_score(self, model: ModelProfile, category: str) -> float:
        """Calculate composite fitness score for a model on a specific category."""
        quality = model.category_scores.get(category, 70.0)  # default prior: 70
        latency = model.avg_latency_ms.get(category, 800)
        cost = model.avg_cost_per_1k

        # Normalize metrics (0 to 1 scale)
        norm_quality = min(max(quality / 100.0, 0.0), 1.0)
        norm_speed = 1.0 - min(latency / 3000.0, 1.0)  # faster latency gives higher score
        norm_cost = 1.0 - min(cost / 0.02, 1.0)        # lower cost gives higher score

        total_score = (
            (norm_quality * self.w_quality)
            + (norm_speed * self.w_latency)
            + (norm_cost * self.w_cost)
        )
        return total_score

    def route_task(self, category: str, confidence_score: float = 90.0) -> RoutingDecision:
        """Select optimal model for the incoming task category."""
        active_candidates = [m for m in self.models.values() if m.active]
        if not active_candidates:
            # Fallback to default
            return RoutingDecision(
                selected_model=self.fallback_chain[0] if self.fallback_chain else "default",
                routing_reason="No registered models active; default fallback triggered.",
                exploration=False,
                confidence_score=confidence_score,
                fallback_chain=self.fallback_chain,
            )

        # Epsilon-Greedy: explore underused or alternative models 10% of the time
        if random.random() < self.epsilon and len(active_candidates) > 1:
            chosen = random.choice(active_candidates)
            return RoutingDecision(
                selected_model=chosen.model_id,
                routing_reason=f"Exploration phase (epsilon={self.epsilon}): testing model variety.",
                exploration=True,
                confidence_score=confidence_score,
                fallback_chain=[m.model_id for m in active_candidates if m.model_id != chosen.model_id],
            )

        # Exploitation phase: pick the model with highest composite score
        scored_models = []
        for m in active_candidates:
            score = self.calculate_score(m, category)
            scored_models.append((score, m))

        scored_models.sort(key=lambda x: x[0], reverse=True)
        best_score, best_model = scored_models[0]

        reason = (
            f"Highest composite score ({best_score:.3f}) for category '{category}' "
            f"(historical quality={best_model.category_scores.get(category, 70.0):.1f}%)."
        )

        subsequent_fallbacks = [m.model_id for _, m in scored_models[1:]] + self.fallback_chain

        return RoutingDecision(
            selected_model=best_model.model_id,
            routing_reason=reason,
            exploration=False,
            confidence_score=confidence_score,
            fallback_chain=subsequent_fallbacks,
        )

    def update_feedback(
        self,
        model_id: str,
        category: str,
        measured_quality: float,
        measured_latency_ms: int,
    ) -> None:
        """Update model profile with feedback loop (Exponential Moving Average / Recency Decay)."""
        if model_id not in self.models:
            return

        model = self.models[model_id]
        current_q = model.category_scores.get(category, 70.0)
        current_lat = model.avg_latency_ms.get(category, 800)

        # Recency-weighted update
        updated_q = (current_q * self.decay) + (measured_quality * (1.0 - self.decay))
        updated_lat = int((current_lat * self.decay) + (measured_latency_ms * (1.0 - self.decay)))

        model.category_scores[category] = round(updated_q, 2)
        model.avg_latency_ms[category] = updated_lat
        model.total_tasks += 1

        logger.info(
            f"Updated model {model_id} on category '{category}': quality={updated_q:.2f}, latency={updated_lat}ms"
        )
