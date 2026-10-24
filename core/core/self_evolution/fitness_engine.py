"""
Manages the fitness evaluation and lifecycle of dynamic AI skills.

This module defines the `FitnessEngine` responsible for tracking skill execution
metrics, calculating performance scores, and automatically deprecating
or 'soft pruning' underperforming skills. It integrates with skill registries,
databases, and the file system to manage skill status and deployment,
ensuring quality control and evolutionary adaptation within the SupremeAI ecosystem.

🛡️ PHASE 3: AutomatedFitnessEngine — Precision fitness scoring with zero fake fallbacks.
"""

import json
import os
import shutil
import threading
from typing import Any

from core.logging_config import logger

# Conditional imports to avoid circular dependency issues
# These are used inside methods but defined here for cleaner structure
try:
    from core.database.supabase_client import db
except ImportError:
    db = None  # type: ignore[assignment]

try:
    from core.skill_manager import SkillManager, get_skill_manager
except ImportError:
    SkillManager = None  # type: ignore[assignment]
    get_skill_manager = None  # type: ignore[assignment]


class FitnessEngineError(ValueError):
    """🛡️ Enterprise Vault: Fitness calculation failure exception"""

    pass


class AutomatedFitnessEngine:
    """
    🧬 PHASE 3: Precision fitness scoring engine with mathematical safety guards.

    Eliminates silent ZeroDivisionError and fake fallback (0.5) patterns.
    Enforces latency penalty layers and upstream Supabase propagation.
    """

    def __init__(self, target_success_rate: float = 0.95):
        self.target_success_rate = target_success_rate

    def calculate_fitness_score(
        self, success_count: int, failure_count: int, execution_time_ms: float
    ) -> float:
        """
        🛡️ Auditor Fix: ZeroDivisionError swallowing eliminated.
        Mathematical safety guard and performance penalty factor injected.

        Returns 0.0 for untested proposals instead of blind 0.5 fallback.
        Applies latency penalty for slow code (>500ms).
        """
        total_runs = success_count + failure_count
        if total_runs == 0:
            # Untested or new proposal: assign baseline zero-state instead of blind 0.5
            return 0.0

        try:
            raw_success_rate = success_count / total_runs

            # Performance penalty: slower code (>2000ms) reduces fitness score
            latency_penalty = (
                max(0.0, min(0.5, (execution_time_ms - 500) / 3000))
                if execution_time_ms > 500
                else 0.0
            )
            fitness_score = raw_success_rate - latency_penalty

            return max(0.0, min(1.0, fitness_score))
        except Exception as e:
            logger.error(f"🚨 [FITNESS_CALCULATION_CRASH]: Precision mapping failed: {e}")
            raise FitnessEngineError(f"Mathematical leak in fitness matrix: {e}") from e

    def evaluate_proposal(self, proposal_id: str, context: dict[str, Any]) -> bool:
        """
        Proposal live evaluation gateway with upstream Supabase propagation.
        """
        try:
            stats = context.get("runtime_stats", {})
            score = self.calculate_fitness_score(
                success_count=stats.get("success_count", 0),
                failure_count=stats.get("failure_count", 0),
                execution_time_ms=stats.get("execution_time_ms", 0.0),
            )

            # Database fitness matrix sync
            if db is not None:
                db.client.table("skill_fitness").upsert(
                    {
                        "proposal_id": proposal_id,
                        "fitness_score": score,
                        "is_viable": score >= self.target_success_rate,
                    }
                ).execute()

            return score >= self.target_success_rate
        except Exception as e:
            logger.error(
                f"🚨 [PROPOSAL_EVALUATION_LEAK]: Failed to safely evaluate proposal {proposal_id}: {e}"
            )
            raise


class FitnessEngine:
    """
    Fitness Score Engine to calculate performance of dynamic skills,
    and automatically deprecate / soft prune low-performing ones.
    """

    def __init__(
        self,
        metrics_path: str | None = None,
        registry_path: str | None = None,
        skills_dir: str | None = None,
        deprecated_dir: str | None = None,
        db: Any | None = None,
    ):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.metrics_path = metrics_path or os.path.join(
            base_dir, "backend", "data", "skills_fitness_metrics.json"
        )
        self.skills_dir = skills_dir or os.path.join(base_dir, "skills", "dynamic")
        self.deprecated_dir = deprecated_dir or os.path.join(base_dir, "skills", "deprecated")
        self.db = db

        # রেস কন্ডিশন এবং ফাইল করাপশন এড়াতে থ্রেড লক ব্যবহার করা হচ্ছে
        self._lock = threading.Lock()

        # Initialize SkillManager singleton - uses conditional import at top to avoid circular dependency
        if get_skill_manager is not None:
            self.registry = get_skill_manager()
        elif SkillManager is not None:
            self.registry = SkillManager()
        else:
            self.registry = None
            logger.warning("SkillManager not available during FitnessEngine init - using None")

        self.metrics = self._load_metrics()

    def _load_metrics(self) -> dict[str, Any]:
        if os.path.exists(self.metrics_path):
            try:
                with open(self.metrics_path, encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode fitness metrics JSON: {e}")
            except OSError as e:
                logger.error(f"OS Error while reading fitness metrics: {e}")
            except Exception as e:
                logger.exception(f"Unexpected error loading metrics: {e}")
        return {}

    def _save_metrics(self):
        try:
            os.makedirs(os.path.dirname(self.metrics_path), exist_ok=True)
            with open(self.metrics_path, "w", encoding="utf-8") as f:
                json.dump(self.metrics, f, indent=4)
        except OSError as e:
            logger.error(f"OS Error while saving fitness metrics: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error saving fitness metrics: {e}")

        if self.db is not None:
            try:
                self.db.collection("system_metrics").document("fitness_metrics").set(
                    {"metrics": self.metrics}
                )
            except Exception as e:
                logger.error(f"Failed to sync fitness metrics to DB: {e}")

    def track_execution(
        self, skill_name: str, success: bool, latency: float, token_cost: float = 0.0
    ):
        """Record telemetry metrics for a skill execution."""
        with self._lock:
            if skill_name not in self.metrics:
                self.metrics[skill_name] = {
                    "success_count": 0,
                    "failure_count": 0,
                    "total_latency": 0.0,
                    "token_cost": 0.0,
                    "reuse_count": 0,
                }

            entry = self.metrics[skill_name]
            if success:
                entry["success_count"] += 1
            else:
                entry["failure_count"] += 1

            entry["total_latency"] += latency
            entry["token_cost"] += token_cost
            entry["reuse_count"] += 1

            self._save_metrics()

    def calculate_fitness(self, skill_name: str) -> float:
        """
        Calculate a normalized score between 0.0 and 1.0.
        If skill has no executions, default to 1.0.

        Formula:
        - Success Rate = success_count / total_runs
        - Latency Penalty = min(1.0, average_latency / 10.0)
        - Fitness = (Success Rate * 0.7) + ((1.0 - Latency Penalty) * 0.3)
        """
        with self._lock:
            if skill_name not in self.metrics:
                return 1.0

            entry = self.metrics[skill_name]
            total_runs = entry["success_count"] + entry["failure_count"]
            if total_runs == 0:
                return 1.0

            success_rate = entry["success_count"] / total_runs
            avg_latency = entry["total_latency"] / total_runs

        latency_penalty = min(1.0, avg_latency / 10.0)
        score = (success_rate * 0.7) + ((1.0 - latency_penalty) * 0.3)
        return float(score)

    def evaluate_and_prune(
        self, skill_name: str, threshold: float = 0.5, min_runs: int = 5
    ) -> bool:
        """
        Evaluate the skill and soft prune it if its score is below threshold after min_runs.
        Returns True if pruned/deprecated, False otherwise.
        """
        with self._lock:
            if skill_name not in self.metrics:
                return False

            entry = self.metrics[skill_name]
            total_runs = entry["success_count"] + entry["failure_count"]

        if total_runs < min_runs:
            return False

        score = self.calculate_fitness(skill_name)
        if score >= threshold:
            return False

        logger.warning(
            f"⚠️ Skill '{skill_name}' failed fitness evaluation! Score: {score:.2f} (Threshold: {threshold}). Initiating soft pruning..."
        )

        # 1. Update Registry status to DEPRECATED
        try:
            skill_data = self.registry._skills.get(skill_name)
            if skill_data and hasattr(skill_data, "status"):
                skill_data.status = "DEPRECATED"
        except Exception as e:
            logger.exception(f"Failed to update registry status: {e}")

        # 2. Update Firestore Status
        if self.db is not None:
            try:
                self.db.collection("supreme_dynamic_skills").document(skill_name).update(
                    {"status": "DEPRECATED"}
                )
            except Exception as e:
                logger.exception(f"Failed to update Firestore status for skill '{skill_name}': {e}")

        # 3. Soft Prune: Move files from skills/dynamic/<skill_name> to skills/deprecated/<skill_name>
        src_dir = os.path.join(self.skills_dir, skill_name)
        dest_dir = os.path.join(self.deprecated_dir, skill_name)

        if os.path.exists(src_dir):
            try:
                os.makedirs(os.path.dirname(dest_dir), exist_ok=True)
                if os.path.exists(dest_dir):
                    shutil.rmtree(dest_dir)
                shutil.move(src_dir, dest_dir)
                logger.info(f"📁 Soft pruned skill files moved to deprecated zone: {dest_dir}")
            except OSError as e:
                logger.error(f"OS Error while moving files to deprecated zone: {e}")
            except Exception as e:
                logger.exception(f"Failed to move files to deprecated zone: {e}")

        return True

    def evaluate_pending(self) -> None:
        """Evaluate all skills currently tracked in metrics and prune those below threshold."""
        # lock এর বাইরে কি লিস্ট কপি করে নেওয়া হচ্ছে
        with self._lock:
            skills_to_evaluate = list(self.metrics.keys())

        for skill_name in skills_to_evaluate:
            self.evaluate_and_prune(skill_name)
