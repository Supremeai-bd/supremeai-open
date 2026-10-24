"""⚠️ ARCHIVED / SUPERSEDED — DO NOT WIRE (preserve for sentiment-scoring pattern).

বাংলা সারসংক্ষেপ: এই ফাইলটি একটি উন্নত wired alternative দ্বারা superseded।
কেবল `FeedbackAnalyzer`-এর keyword-sentiment-scoring pattern হিসেবে সংরক্ষিত।

কেন superseded (deep value-analysis findings):
  1. উন্নত wired alternative বিদ্যমান: `core/tier8/self_improvement_agent.py::
     SelfImprovementAgent(BaseSkill)` — LLM-driven refactor proposals, dry-run CI/CD
     validation, BaseSkill-based singleton। এটি `core/tier8/tier8_integration.py::
     init_tier8()` দ্বারা wired (startup/agents.py:84, যখন ENABLE_TIER8=true)।
  2. এই adaptive_engine version-এর "improvements" (model_selection_adjustments,
     prompt_optimizations, caching_adjustments, context_improvements) Redis-এ লেখা
     হয় কিন্তু কেউ পড়ে না (write-only, কোনো downstream consumer নেই)।
     model_router/prompt_handler/cache_manager/context_manager কোনোটিই এই keys পড়ে না।
  3. একটি import broken: `from core.adaptive_engine.learning_loop import ExperienceDatabase`
     — `core/adaptive_engine/` directory নেই (top-level `adaptive_engine/` আছে), এবং
     `learning_loop.py`-তে `ExperienceDatabase` নেই (সেটি `adaptive_engine/experience_db.py`
     এ আছে)। সঠিক fix হবে: `from adaptive_engine.experience_db import ExperienceDatabase`।
  4. `FeedbackAnalyzer` keyword-based sentiment scoring (primitive কিন্তু functional) —
     এটিই একমাত্র সংরক্ষণযোগ্য অংশ।

যদি ভবিষ্যতে revive করতে হয়:
  - broken import ঠিক করুন: `from adaptive_engine.experience_db import ExperienceDatabase`
  - Redis "improvement" keys-এর জন্য downstream consumers যোগ করুন (model_router এই
    keys পড়ে behavior adjust করবে)।
  - অথবা tier8 version-এর সাথে একত্রিত করুন।

Wired alternative (ব্যবহার করুন): core/tier8/codebase_refactor_proposer.py::CodebaseRefactorProposer
"""

"""
SupremeAI 2.0 Self-Improving Agent
===================================
Agent that continuously improves system performance based on feedback
and experience learning.
"""

import json
from dataclasses import dataclass
from datetime import datetime

# FIX (import): canonical location is adaptive_engine.experience_db
from adaptive_engine.experience_db import ExperienceDatabase
from core.cache import get_redis_client
from monitoring.logging import get_logger


@dataclass
class ImprovementMetric:
    """Metrics for measuring system improvement."""

    accuracy: float
    response_time: float
    user_satisfaction: float
    cost_efficiency: float
    timestamp: datetime


class SelfImprovingAgent:
    """Agent that continuously improves system performance based on feedback."""

    def __init__(self, experience_db: ExperienceDatabase):
        self.experience_db = experience_db
        self.redis_client = get_redis_client()
        self.feedback_analyzer = FeedbackAnalyzer()
        self.performance_history: list[ImprovementMetric] = []
        self.improvement_strategies = []
        self.logger = get_logger(__name__)

    async def process_feedback(
        self, user_id: str, request: str, response: str, feedback: str, rating: float | None = None
    ) -> bool:
        """Process user feedback and apply improvements."""
        try:
            # Analyze feedback
            feedback_analysis = await self.feedback_analyzer.analyze(feedback, rating)

            # Record experience for future learning
            experience = {
                "user_id": user_id,
                "request": request,
                "response": response,
                "feedback": feedback,
                "rating": rating,
                "feedback_analysis": feedback_analysis,
                "timestamp": datetime.now().isoformat(),
                "session_id": f"session_{user_id}_{int(datetime.now().timestamp())}",
            }

            # Store in experience database
            # Note: This would use the actual experience_db.record_experience method
            # For now, we'll store in Redis as a placeholder
            exp_key = f"experience:{experience['session_id']}"
            self.redis_client.setex(exp_key, 86400 * 30, json.dumps(experience))

            # Apply improvements based on feedback
            await self.apply_improvement(feedback_analysis, experience)

            # Update performance metrics
            await self.update_performance_metrics(experience, feedback_analysis)

            return True
        except Exception as e:
            self.logger.error(f"Error processing feedback: {e}")
            return False

    async def apply_improvement(self, feedback_analysis: dict, experience: dict):
        """Apply system improvements based on feedback analysis."""
        if feedback_analysis.get("sentiment") == "negative" or (
            experience.get("rating") and experience["rating"] < 3.0
        ):
            # Identify areas for improvement
            areas_to_improve = self.identify_improvement_areas(experience)

            # Generate improvement suggestions
            suggestions = await self.generate_improvement_suggestions(
                experience, areas_to_improve, feedback_analysis
            )

            # Apply improvements
            for suggestion in suggestions:
                await self.implement_suggestion(suggestion)

        # Apply proactive improvements based on patterns
        await self.apply_proactive_improvements()

    def identify_improvement_areas(self, experience: dict) -> list[str]:
        """Identify specific areas that need improvement."""
        areas = []

        # Check for common issues
        if "error" in (experience.get("response") or "").lower():
            areas.append("error_handling")
        if (
            len(experience.get("response") or "") < 50
            and "error" not in (experience.get("response") or "").lower()
        ):
            areas.append("response_completeness")
        if (experience.get("feedback") or "").lower().find("slow") != -1:
            areas.append("performance")
        if (experience.get("feedback") or "").lower().find("irrelevant") != -1:
            areas.append("relevance")
        if (experience.get("feedback") or "").lower().find("understand") == -1 and len(
            experience.get("request") or ""
        ) > 50:
            areas.append("comprehension")

        return areas if areas else ["general_improvement"]

    async def generate_improvement_suggestions(
        self, experience: dict, areas: list[str], feedback_analysis: dict
    ) -> list[dict]:
        """Generate improvement suggestions based on experience and identified areas."""
        suggestions = []

        for area in areas:
            if area == "error_handling":
                suggestions.append(
                    {
                        "type": "model_selection",
                        "description": "Switch to more reliable model for error-prone queries",
                        "priority": "high",
                        "implementation": {
                            "target": "llm_router",
                            "change": "increase reliability weighting for stable models",
                        },
                    }
                )
            elif area == "response_completeness":
                suggestions.append(
                    {
                        "type": "prompt_optimization",
                        "description": "Enhance prompt to generate more comprehensive responses",
                        "priority": "medium",
                        "implementation": {
                            "target": "prompt_templates",
                            "change": "add instruction for detailed responses",
                        },
                    }
                )
            elif area == "performance":
                suggestions.append(
                    {
                        "type": "caching_strategy",
                        "description": "Improve caching for similar queries",
                        "priority": "high",
                        "implementation": {
                            "target": "caching_layer",
                            "change": "implement semantic caching for common queries",
                        },
                    }
                )
            elif area == "relevance":
                suggestions.append(
                    {
                        "type": "context_management",
                        "description": "Better utilize conversation context",
                        "priority": "medium",
                        "implementation": {
                            "target": "context_system",
                            "change": "improve context retrieval and utilization",
                        },
                    }
                )

        return suggestions

    async def implement_suggestion(self, suggestion: dict):
        """Implement a specific improvement suggestion."""
        suggestion_type = suggestion.get("type")
        implementation = suggestion.get("implementation", {})

        if suggestion_type == "model_selection":
            await self.adjust_model_selection_logic(implementation)
        elif suggestion_type == "prompt_optimization":
            await self.optimize_prompts(implementation)
        elif suggestion_type == "caching_strategy":
            await self.adjust_caching_strategy(implementation)
        elif suggestion_type == "context_management":
            await self.improve_context_utilization(implementation)

    async def adjust_model_selection_logic(self, implementation: dict):
        """Adjust model selection based on improvement needs."""
        # Store adjustment in Redis for persistence
        key = "model_selection_adjustments"
        adjustments = self.redis_client.get(key)
        if adjustments:
            adjustments = json.loads(adjustments)
        else:
            adjustments = {}

        # Apply adjustment (example: increase reliability weighting)
        adjustments["reliability_weight"] = adjustments.get("reliability_weight", 0.4) + 0.1
        # Cap at 0.8 to prevent over-adjustment
        adjustments["reliability_weight"] = min(adjustments["reliability_weight"], 0.8)

        self.redis_client.setex(key, 86400, json.dumps(adjustments))

    async def optimize_prompts(self, implementation: dict):
        """Optimize prompts based on improvement needs."""
        # Store prompt optimizations in Redis
        key = "prompt_optimizations"
        optimizations = self.redis_client.get(key)
        if optimizations:
            optimizations = json.loads(optimizations)
        else:
            optimizations = {}

        # Example: Add instruction for detailed responses
        optimizations["detail_instruction"] = (
            "Always provide detailed, comprehensive responses with examples when possible."
        )

        self.redis_client.setex(key, 86400, json.dumps(optimizations))

    async def adjust_caching_strategy(self, implementation: dict):
        """Adjust caching strategy based on improvement needs."""
        # Store caching adjustments in Redis
        key = "caching_adjustments"
        adjustments = self.redis_client.get(key)
        if adjustments:
            adjustments = json.loads(adjustments)
        else:
            adjustments = {}

        # Example: Increase cache TTL for common queries
        adjustments["common_query_ttl"] = 1800  # 30 minutes
        adjustments["semantic_caching_enabled"] = True

        self.redis_client.setex(key, 86400, json.dumps(adjustments))

    async def improve_context_utilization(self, implementation: dict):
        """Improve context utilization based on improvement needs."""
        # Store context improvements in Redis
        key = "context_improvements"
        improvements = self.redis_client.get(key)
        if improvements:
            improvements = json.loads(improvements)
        else:
            improvements = {}

        # Example: Increase context window utilization
        improvements["context_window_utilization"] = 0.8  # Use 80% of context window
        improvements["context_relevance_threshold"] = 0.7  # Minimum relevance score

        self.redis_client.setex(key, 86400, json.dumps(improvements))

    async def update_performance_metrics(self, experience: dict, feedback_analysis: dict):
        """Update system performance metrics based on experience."""
        # Calculate metrics from experience
        accuracy = feedback_analysis.get("accuracy_score", 0.5)
        response_time = float(experience.get("response_time", 1.0))
        user_satisfaction = feedback_analysis.get("satisfaction_score", 0.5)
        cost_efficiency = float(experience.get("cost_efficiency", 1.0))

        metric = ImprovementMetric(
            accuracy=accuracy,
            response_time=response_time,
            user_satisfaction=user_satisfaction,
            cost_efficiency=cost_efficiency,
            timestamp=datetime.now(),
        )

        self.performance_history.append(metric)

        # Keep only recent metrics (last 100)
        if len(self.performance_history) > 100:
            self.performance_history = self.performance_history[-100:]

        # Store metrics in Redis for monitoring
        metrics_key = "performance_metrics"
        recent_metrics = [m.__dict__ for m in self.performance_history[-10:]]  # Last 10 metrics
        self.redis_client.setex(metrics_key, 3600, json.dumps(recent_metrics))

    async def apply_proactive_improvements(self):
        """Apply proactive improvements based on patterns in experience data."""
        # Look for patterns in recent experiences
        recent_experiences = self.get_recent_experiences(50)  # Last 50 experiences

        if len(recent_experiences) >= 10:
            # Analyze patterns
            avg_rating = sum(float(exp.get("rating", 0)) for exp in recent_experiences) / len(
                recent_experiences
            )

            if avg_rating < 3.5:  # Low average rating
                # Trigger system-wide improvement process
                await self.trigger_system_wide_improvement()

    def get_recent_experiences(self, count: int) -> list[dict]:
        """Get recent experiences from experience database."""
        # This would typically query the experience database
        # For now, return empty list - would be implemented based on the actual experience_db structure
        keys = self.redis_client.keys("experience:*")
        experiences = []
        for key in keys[-count:]:  # Get last 'count' experiences
            exp_data = self.redis_client.get(key)
            if exp_data:
                try:
                    exp = json.loads(exp_data)
                    experiences.append(exp)
                except json.JSONDecodeError:
                    continue
        return experiences

    async def trigger_system_wide_improvement(self):
        """Trigger system-wide improvement based on poor performance."""
        self.logger.info("Triggering system-wide improvement due to low performance metrics")

        # Store improvement trigger in Redis
        key = "system_improvement_trigger"
        trigger_data = {
            "triggered_at": datetime.now().isoformat(),
            "reason": "low_average_rating",
            "action_taken": "increased_learning_rate",
        }
        self.redis_client.setex(key, 3600, json.dumps(trigger_data))


class FeedbackAnalyzer:
    """Analyzes user feedback for improvement opportunities."""

    def __init__(self):
        self.positive_keywords = [
            "good",
            "great",
            "excellent",
            "perfect",
            "love",
            "amazing",
            "helpful",
            "accurate",
            "fast",
        ]
        self.negative_keywords = [
            "bad",
            "terrible",
            "hate",
            "disappointed",
            "slow",
            "wrong",
            "confusing",
            "useless",
            "poor",
        ]
        self.neutral_keywords = ["okay", "fine", "average", "decent", "acceptable"]
        self.logger = get_logger(__name__)

    async def analyze(self, feedback: str, rating: float | None = None) -> dict:
        """Analyze user feedback for sentiment and improvement opportunities."""
        feedback_lower = feedback.lower() if feedback else ""

        # Count positive and negative keywords
        positive_count = sum(1 for word in self.positive_keywords if word in feedback_lower)
        negative_count = sum(1 for word in self.negative_keywords if word in feedback_lower)
        neutral_count = sum(1 for word in self.neutral_keywords if word in feedback_lower)

        # Determine sentiment
        if positive_count > negative_count:
            sentiment = "positive"
        elif negative_count > positive_count:
            sentiment = "negative"
        else:
            sentiment = "neutral"

        # Calculate scores
        word_count = len(feedback_lower.split()) if feedback_lower else 1
        positive_score = positive_count / max(word_count, 1)
        negative_score = negative_count / max(word_count, 1)
        neutral_score = neutral_count / max(word_count, 1)

        # Calculate satisfaction score (combine rating and sentiment)
        if rating is not None:
            # Use explicit rating if provided
            satisfaction_score = rating / 5.0  # Normalize 1-5 rating to 0-1
        else:
            # Estimate from sentiment
            if sentiment == "positive":
                satisfaction_score = 0.8
            elif sentiment == "negative":
                satisfaction_score = 0.2
            else:
                satisfaction_score = 0.5

        # Estimate accuracy from feedback
        accuracy_indicators = ["correct", "right", "accurate", "precise", "exact"]
        accuracy_count = sum(1 for word in accuracy_indicators if word in feedback_lower)
        accuracy_score = min(accuracy_count / max(word_count, 1) * 5, 1.0)  # Cap at 1.0

        return {
            "sentiment": sentiment,
            "positive_score": positive_score,
            "negative_score": negative_score,
            "neutral_score": neutral_score,
            "satisfaction_score": satisfaction_score,
            "accuracy_score": accuracy_score,
            "keyword_counts": {
                "positive": positive_count,
                "negative": negative_count,
                "neutral": neutral_count,
            },
        }


# Global instance of the self-improving agent
# This would be initialized with the experience database in the main application
self_improving_agent = None
