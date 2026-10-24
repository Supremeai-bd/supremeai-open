"""
SupremeAI — Skill Recommendation Engine (Upgraded)
===================================================

ML/heuristic-based smart recommendation engine that:
- Tracks skill usage patterns
- Uses collaborative filtering (user-based + item-based)
- Falls back to heuristic scoring when ML data is insufficient
- Recommends skills based on project context
- Caches recommendations
- Returns ranked skill list with relevance scores
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, cast

from brain.model_router import ModelRouter
from core.cache import get_cache
from core.config_cache import config_cache
from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from database.supabase_client import db

# ── Constants ────────────────────────────────────────────────────────────────
RECOMMENDATION_CACHE_TTL = 900  # 15 minutes
MIN_USAGE_FOR_ML = 50  # Minimum usage count for ML recommendations
MAX_RECOMMENDATIONS = 20


def _get_skill_name(skill_id: str) -> str:
    # বাংলা মন্তব্য: স্কিল আইডি থেকে পড়ার যোগ্য নাম তৈরি করা হয়।
    return skill_id.replace("_", " ").title()


class RecommendationStrategy(StrEnum):
    COLLABORATIVE_USER = "collaborative_user"
    COLLABORATIVE_ITEM = "collaborative_item"
    HEURISTIC = "heuristic"
    CONTEXTUAL = "contextual"
    POPULARITY = "popularity"


@dataclass(frozen=True)
class SkillRecommendation:
    """Immutable skill recommendation result."""

    skill_id: str
    skill_name: str
    relevance_score: float  # 0.0 - 1.0
    confidence: float
    strategy_used: RecommendationStrategy
    reason: str
    estimated_impact: str


class CollaborativeFilter:
    """
    User-based and item-based collaborative filtering for skill recommendations.
    Uses usage co-occurrence patterns to find similar skills/users.
    """

    def __init__(self, usage_matrix: dict[str, dict[str, int]] | None = None) -> None:
        self.usage_matrix = usage_matrix or defaultdict(dict)
        self.cache = get_cache()

    def build_usage_matrix(self, usage_logs: list[dict[str, Any]]) -> None:
        """Build user-skill and skill-skill co-occurrence matrices."""
        # User-skill matrix: {user_id: {skill_id: count}}
        for log in usage_logs:
            user_id = log.get("user_id", "anonymous")
            skill_id = log.get("skill_id", "")
            count = log.get("usage_count", 1)
            self.usage_matrix[user_id][skill_id] = (
                self.usage_matrix[user_id].get(skill_id, 0) + count
            )

    def user_similarity(self, user_a: str, user_b: str) -> float:
        """Calculate cosine similarity between two users based on skill usage."""
        skills_a = self.usage_matrix.get(user_a, {})
        skills_b = self.usage_matrix.get(user_b, {})

        if not skills_a or not skills_b:
            return 0.0

        # Get all unique skills
        all_skills = set(skills_a) | set(skills_b)

        # Calculate dot product and magnitudes
        dot = sum(skills_a.get(skill, 0) * skills_b.get(skill, 0) for skill in all_skills)
        mag_a = sum(v**2 for v in skills_a.values()) ** 0.5
        mag_b = sum(v**2 for v in skills_b.values()) ** 0.5

        if mag_a == 0 or mag_b == 0:
            return 0.0

        return dot / (mag_a * mag_b)

    def skill_similarity(self, skill_a: str, skill_b: str) -> float:
        """Calculate Jaccard similarity between two skills based on co-usage."""
        users_a = {user for user, skills in self.usage_matrix.items() if skill_a in skills}
        users_b = {user for user, skills in self.usage_matrix.items() if skill_b in skills}

        if not users_a or not users_b:
            return 0.0

        intersection = len(users_a & users_b)
        union = len(users_a | users_b)

        return intersection / union if union > 0 else 0.0

    def recommend_by_user(
        self, user_id: str, top_k: int = MAX_RECOMMENDATIONS
    ) -> list[SkillRecommendation]:
        """Recommend skills based on similar users' preferences."""
        if user_id not in self.usage_matrix:
            return []

        # Find similar users
        similarities = [
            (other_user, self.user_similarity(user_id, other_user))
            for other_user in self.usage_matrix
            if other_user != user_id
        ]
        similarities.sort(key=lambda x: x[1], reverse=True)
        top_users = [u for u, s in similarities[:5] if s > 0.1]

        # Aggregate recommendations from similar users
        candidate_scores: dict[str, float] = defaultdict(float)
        user_skills = set(self.usage_matrix.get(user_id, {}))

        for similar_user in top_users:
            for skill_id, count in self.usage_matrix.get(similar_user, {}).items():
                if skill_id not in user_skills:
                    candidate_scores[skill_id] += count * similarities[0][1]

        # Convert to recommendations
        recommendations = [
            SkillRecommendation(
                skill_id=skill_id,
                skill_name=_get_skill_name(skill_id),
                relevance_score=min(score, 1.0),
                confidence=0.8,
                strategy_used=RecommendationStrategy.COLLABORATIVE_USER,
                reason="Similar users frequently use this skill",
                estimated_impact="medium",
            )
            for skill_id, score in sorted(
                candidate_scores.items(), key=lambda x: x[1], reverse=True
            )[:top_k]
        ]

        return recommendations


class HeuristicScorer:
    """
    Heuristic-based scoring when ML data is insufficient.
    Uses project context, skill metadata, and popularity signals.
    """

    def __init__(self, llm_router: ModelRouter | None = None) -> None:
        self.llm_router = llm_router or ModelRouter()
        self.cache = get_cache()

    async def score(
        self,
        skill_id: str,
        project_context: dict[str, Any],
        usage_stats: dict[str, int],
    ) -> SkillRecommendation:
        """Score a skill based on heuristic signals."""
        score = 0.0
        reasons = []

        # Project context match
        tech_stack = project_context.get("tech_stack", [])
        skill_metadata = project_context.get("available_skills", {}).get(skill_id, {})

        # Match tech stack
        for tech in tech_stack:
            if skill_metadata.get("tags") and tech in skill_metadata.get("tags", []):
                score += 0.3
                reasons.append(f"Matches your {tech} stack")

        # Usage popularity
        global_usage = usage_stats.get(skill_id, 0)
        if global_usage > 100:
            score += 0.2
            reasons.append("Popular across teams")
        elif global_usage > 10:
            score += 0.1
            reasons.append("Moderately used")

        # Freshness factor
        last_updated = skill_metadata.get("last_updated")
        if last_updated:
            try:
                updated = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
                now = datetime.now(UTC)
                days_old = (now - updated).days
                if days_old < 30:
                    score += 0.15
                    reasons.append("Recently updated")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                import logging

                logging.getLogger(__name__).exception(f"Silenced error: {e}")

        # Use LLM for semantic matching if available
        try:
            project_desc = project_context.get("description", "")
            skill_desc = skill_metadata.get("description", "")
            if project_desc and skill_desc:
                semantic_score = await self._semantic_similarity(project_desc, skill_desc)
                score += semantic_score * 0.2
                if semantic_score > 0.5:
                    reasons.append("Semantically relevant to your goals")
        except Exception as e:
            logger.debug(f"LLM semantic similarity failed: {e}")

        return SkillRecommendation(
            skill_id=skill_id,
            skill_name=skill_metadata.get("name", skill_id),
            relevance_score=min(score, 1.0),
            confidence=0.6,
            strategy_used=RecommendationStrategy.HEURISTIC,
            reason="; ".join(reasons[:2]) or "General recommendation",
            estimated_impact="low" if score < 0.3 else "medium",
        )

    @with_error_bus("_semantic_similarity")
    async def _semantic_similarity(self, text_a: str, text_b: str) -> float:
        """Get semantic similarity score using LLM embeddings."""
        cache_key = f"semantic:{hashlib.sha256((text_a + text_b).encode()).hexdigest()[:16]}"

        cached = await self.cache.get(cache_key)
        if cached:
            return float(cached)

        prompt = (
            "Return a single float between 0.0 and 1.0 representing the semantic similarity "
            "between the following two texts. No explanation, no formatting.\n\n"
            f"Text A: {text_a[:200]}\nText B: {text_b[:200]}"
        )

        try:
            result = await self.llm_router.async_route_and_generate(
                prompt=prompt,
                task_type="embedding",
                max_tokens=config_cache.get("skill_recommender_max_tokens", 50),
                temperature=config_cache.get("skill_recommender_temperature", 0.0),
            )
            score = float(result.get("text", "0.0"))
            await self.cache.set(cache_key, score, ttl=RECOMMENDATION_CACHE_TTL)
            return score
        except Exception:
            return 0.0

    def _get_skill_name(self, skill_id: str) -> str:
        """Extract readable skill name from ID."""
        return skill_id.replace("_", " ").title()


class ContextAnalyzer:
    """
    Analyzes project context to inform skill recommendations.
    Extracts tech stack, project goals, and current skill usage.
    """

    @staticmethod
    def extract_tech_stack(project_files: list[str]) -> list[str]:
        """Extract technology stack from project file list."""
        tech_stack = []
        file_patterns = {
            "fastapi": ["main.py", "api/", "requirements.txt"],
            "react": ["package.json", "src/", "components/"],
            "python": [".py"],
            "typescript": [".ts", ".tsx"],
            "postgresql": ["postgres", "sqlalchemy", "alembic"],
            "redis": ["redis", "cache", "upstash"],
            "docker": ["Dockerfile", "docker-compose"],
            "kubernetes": ["k8s", "helm", "deployment"],
        }

        for pattern, indicators in file_patterns.items():
            for indicator in indicators:
                if any(indicator in f for f in project_files):
                    tech_stack.append(pattern)
                    break

        return tech_stack

    @staticmethod
    def extract_project_goals(readme_content: str | None) -> list[str]:
        """Extract project goals from README or description."""
        if not readme_content:
            return []

        goals = []
        goal_patterns = [
            (r"goal:", "goal"),
            (r"objective:", "objective"),
            (r"feature:", "feature"),
            (r"implement", "implementation"),
        ]

        import re

        for pattern, _ in goal_patterns:
            matches = re.findall(rf"{pattern}\s*([^\n]+)", readme_content, re.IGNORECASE)
            goals.extend([m.strip()[:100] for m in matches[:3]])

        return goals


class SkillRecommender:
    """
    Production-ready skill recommendation engine.
    Combines multiple strategies with graceful fallbacks.
    """

    def __init__(
        self,
        filter_engine: CollaborativeFilter | None = None,
        scorer: HeuristicScorer | None = None,
    ) -> None:
        self.filter = filter_engine or CollaborativeFilter()
        self.scorer = scorer or HeuristicScorer()
        self.cache = get_cache()
        self.context_analyzer = ContextAnalyzer()
        # বাংলা মন্তব্য: পূর্বের টেস্টগুলির জন্য লোকাল হিস্টোরি ডিকশনারি ইনিশিয়ালাইজ করা হলো।
        self._local_history: dict[str, list[dict[str, Any]]] = {}
        logger.info("SkillRecommender initialized")

    def _get_user_history(self, user_id: str) -> list[dict[str, Any]]:
        # বাংলা মন্তব্য: ডাটাবেজ থেকে ব্যবহারকারীর হিস্টোরি নিয়ে আসার চেষ্টা করা হয়, ব্যর্থ হলে লোকাল হিস্টোরি ফেরত দেওয়া হয়।
        if db.client:
            try:
                res = (
                    db.client.table("task_history")
                    .select("*")
                    .eq("user_id", user_id)
                    .order("created_at", desc=True)
                    .limit(50)
                    .execute()
                )
                return cast(list[dict[str, Any]], res.data) if res.data else []
            except Exception as exc:
                logger.debug(f"History fetch from DB failed: {exc}")
        return self._local_history.get(user_id, [])

    def _record_task(self, user_id: str, task: dict[str, Any]) -> None:
        # বাংলা মন্তব্য: ব্যবহারকারীর নতুন টাস্ক ডাটাবেজে রেকর্ড করা হয়, ব্যর্থ হলে লোকাল হিস্টোরিতে সংরক্ষণ করা হয়।
        entry = {"user_id": user_id, "task": task}
        if db.client:
            try:
                db.client.table("task_history").insert(entry).execute()
                return
            except Exception as exc:
                logger.debug(f"History insert failed: {exc}")

        # Fallback if DB client is none or insert failed
        self._local_history.setdefault(user_id, []).append(entry)

    def _embedding(self, text: str) -> list[float]:
        # বাংলা মন্তব্য: ইনপুট টেক্সট এর জন্য একটি ৬৪ দৈর্ঘ্যের ভেক্টর জেনারেট করা হয়।
        text = re.sub(r"\s+", " ", text.lower()).strip()
        vec = [0.0] * 64
        h = hashlib.sha512(text.encode()).hexdigest()
        for i in range(64):
            byte_val = int(h[i * 2 : i * 2 + 2], 16)
            vec[i] = (byte_val / 255.0) * 2 - 1
        return vec

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        # বাংলা মন্তব্য: দুটি ভেক্টরের মধ্যকার কোসাইন সিমিলারিটি হিসাব করা হয়।
        num = sum(x * y for x, y in zip(a, b, strict=False))
        den = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5)
        return num / den if den > 0 else 0.0

    def record_and_recommend(
        self, user_id: str, task_description: str, top_k: int = 5
    ) -> dict[str, Any]:
        # বাংলা মন্তব্য: ব্যবহারকারীর টাস্ক রেকর্ড করে সেই অনুযায়ী স্কিল রেকমেন্ডেশন প্রদান করা হয়।
        self._record_task(user_id, {"description": task_description, "type": "user_query"})
        self._record_task(user_id, {"description": task_description, "type": "search"})
        recs = self.recommend(user_id, task_description, top_k=top_k)
        return {
            "user_id": user_id,
            "task": task_description,
            "recommendations": recs,
            "count": len(recs),
        }

    def recommend(
        self,
        user_id: str | None = None,
        project_context: dict[str, Any] | str | None = None,
        usage_logs: list[dict[str, Any]] | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]] | Any:
        # বাংলা মন্তব্য: যদি `project_context` একটি স্ট্রিং হয়, তবে এটি লেগাসি সিঙ্ক মোডে রান করবে।
        if isinstance(project_context, str):
            return self._recommend_legacy(user_id, project_context, top_k)

        # বাংলা মন্তব্য: অন্যথায় এটি অ্যাসিনক্রোনাসলি নতুন লজিক রান করাবে।
        return self.recommend_async(user_id, project_context, usage_logs, top_k)

    def _recommend_legacy(
        self, user_id: str, current_task: str, top_k: int = 5
    ) -> list[dict[str, Any]]:
        # বাংলা মন্তব্য: এটি পূর্বে ব্যবহৃত pgvector কোসাইন সিমিলারিটি ভিত্তিক স্কিল রেকমেন্ডেশন লজিক।
        history = self._get_user_history(user_id)
        current_vec = self._embedding(current_task)
        scored: list[dict[str, Any]] = []
        seen_skills: dict[str, dict[str, Any]] = {}
        for entry in history:
            task_text = entry.get("task", {}).get("description", "") or entry.get("task", {}).get(
                "text", ""
            )
            skill_id = entry.get("task", {}).get("skill_id")
            if not skill_id:
                continue
            vec = self._embedding(task_text)
            sim = self._cosine_similarity(current_vec, vec)
            if skill_id not in seen_skills or seen_skills[skill_id]["score"] < sim:
                seen_skills[skill_id] = {
                    "skill_id": skill_id,
                    "score": sim,
                    "task_text": task_text,
                }
        scored = sorted(seen_skills.values(), key=lambda x: x["score"], reverse=True)[:top_k]
        enriched: list[dict[str, Any]] = []
        if db.client:
            for item in scored:
                try:
                    res = (
                        db.service_client.table("tools_registry")
                        .select("*")
                        .eq("id", item["skill_id"])
                        .execute()
                    )
                    if res.data:
                        enriched.append({**res.data[0], "match_score": round(item["score"], 3)})
                except Exception as e:
                    try:
                        import loguru

                        loguru.logger.error(f"Tool execution error: {e}")
                    except Exception as e:
                        logger.warning(f"Exception suppressed: {e}")
                    pass
        if not enriched:
            enriched = [
                {
                    "id": s["skill_id"],
                    "name": s["skill_id"],
                    "match_score": round(s["score"], 3),
                    "category": "inferred",
                }
                for s in scored
            ]
        return enriched

    async def recommend_async(
        self,
        user_id: str | None = None,
        project_context: dict[str, Any] | None = None,
        usage_logs: list[dict[str, Any]] | None = None,
        top_k: int = MAX_RECOMMENDATIONS,
    ) -> list[dict[str, Any]]:
        """
        Generate skill recommendations using multiple strategies.

        Args:
            user_id: Target user ID.
            project_context: Project description and tech stack.
            usage_logs: Historical usage data.
            top_k: Number of recommendations to return.

        Returns:
            List of ranked skill recommendations.
        """
        cache_key = f"recommend:{user_id or 'anon'}:{hashlib.sha256(str(project_context).encode()).hexdigest()[:12]}"

        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        all_recommendations: list[SkillRecommendation] = []

        # Build usage matrix if logs provided
        if usage_logs:
            self.filter.build_usage_matrix(usage_logs)

        # Strategy 1: Collaborative filtering (if sufficient data)
        total_usage = sum(sum(skills.values()) for skills in self.filter.usage_matrix.values())
        if total_usage >= MIN_USAGE_FOR_ML and user_id:
            collab_recs = self.filter.recommend_by_user(user_id, top_k)
            all_recommendations.extend(collab_recs)

        # Strategy 2: Heuristic scoring
        if project_context and usage_logs:
            usage_stats: dict[str, int] = defaultdict(int)
            for log in usage_logs:
                usage_stats[log.get("skill_id", "")] = usage_stats.get(
                    log.get("skill_id", ""), 0
                ) + log.get("usage_count", 1)

            available_skills = project_context.get("available_skills", {}).keys() or list(
                usage_stats.keys()
            )

            for skill_id in available_skills:
                rec = await self.scorer.score(skill_id, project_context, usage_stats)
                all_recommendations.append(rec)

        # Strategy 3: Popularity fallback
        if len(all_recommendations) < top_k:
            usage_stats = defaultdict(int)
            if usage_logs:
                for log in usage_logs:
                    usage_stats[log.get("skill_id", "")] += log.get("usage_count", 1)

            for skill_id, count in sorted(usage_stats.items(), key=lambda x: x[1], reverse=True)[
                :5
            ]:
                all_recommendations.append(
                    SkillRecommendation(
                        skill_id=skill_id,
                        skill_name=skill_id.replace("_", " ").title(),
                        relevance_score=min(count / 100, 1.0),
                        confidence=0.4,
                        strategy_used=RecommendationStrategy.POPULARITY,
                        reason="Popular across all users",
                        estimated_impact="low",
                    )
                )

        # Rank and deduplicate
        seen = set()
        final = []
        for rec in sorted(
            all_recommendations,
            key=lambda r: (r.relevance_score, r.confidence),
            reverse=True,
        ):
            if rec.skill_id not in seen:
                seen.add(rec.skill_id)
                final.append(rec)

        # Cache and return
        result = [
            {
                "skill_id": r.skill_id,
                "skill_name": r.skill_name,
                "relevance_score": r.relevance_score,
                "confidence": r.confidence,
                "strategy_used": r.strategy_used.value,
                "reason": r.reason,
                "estimated_impact": r.estimated_impact,
            }
            for r in final[:top_k]
        ]

        await self.cache.set(cache_key, result, ttl=RECOMMENDATION_CACHE_TTL)
        return result


# Singleton instance
_recommender_instance: SkillRecommender | None = None


def get_skill_recommender() -> SkillRecommender:
    """Get or create the singleton SkillRecommender instance."""
    global _recommender_instance
    if _recommender_instance is None:
        _recommender_instance = SkillRecommender()
    return _recommender_instance
