"""Performance and Self-Healing Enhancement Module for SupremeAI 2.0
Enhances system performance, resilience, and autonomous healing capabilities.

বাংলা: সুপ্রিমএআই ২.০ এর পারফরম্যান্স এবং সেলফ-হিলিং ক্ষমতা উন্নত করে।
"""

import asyncio
import hashlib
import json
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from brain.model_registry import ModelRegistry
from core.config import settings
from core.health.self_healer import RemediationPipeline, SelfHealerService
from core.logging_config import logger
from core.resilience.circuit_breaker import CircuitBreaker


@dataclass
class PerformanceMetrics:
    """Stores performance metrics for system monitoring.

    বাংলা: সিস্টেম মনিটরিং জন্য পারফরম্যান্স মেট্রিক্স সংরক্ষণ করে।
    """

    request_count: int = 0
    error_count: int = 0
    avg_response_time: float = 0.0
    peak_memory_usage: float = 0.0
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class FailureHistoryEntry:
    """Represents a past failure for learning purposes.

    বাংলা: শেখার জন্য অতীতের কোনো একটি ফেইলিউরকে প্রতিনিধিত্ব করে।
    """

    timestamp: datetime
    error_type: str
    error_message: str
    context: dict[str, Any]
    resolution: str
    resolved: bool = False


class PerformanceOptimizer:
    """Main performance optimizer class implementing the core philosophy.

    বাংলা: মূল filosophy প্রয়োগকারী প্রধান পারফরম্যান্স অপ্টিমাইজার ক্লাস।
    """

    def __init__(self):
        """Initialize the performance optimizer with self-healing capabilities.

        বাংলা: সেলফ-হিলিং ক্ষমতার সহ性能 অপ্টিমাইজার ইনিশিয়ালাইজ করে।
        """
        self.metrics: dict[str, PerformanceMetrics] = {}
        self.failure_history: list[FailureHistoryEntry] = []
        self.model_stats: dict[str, dict[str, float]] = {}
        self.dynamic_circuit_breakers: dict[str, CircuitBreaker] = {}
        self.model_registry = ModelRegistry()
        self.self_healer = None
        self.reminder_pipeline = None

        # 🔒 বাংলা: Race Condition Guard — একাধিক async task একসাথে shared state পরিবর্তন করতে পারে।
        # asyncio.Lock ব্যবহার করে atomic update নিশ্চিত করা হলো।
        self._state_lock: asyncio.Lock = asyncio.Lock()

        # Initialize self-healing components
        try:
            from utils.firestore_helpers import get_firestore_db

            db = get_firestore_db()
            if db:
                self.self_healer = SelfHealerService(db)
                self.reminder_pipeline = RemediationPipeline(db)
        except ImportError:
            logger.warning("Firestore not available, self-healing features limited")

        logger.info("✅ PerformanceOptimizer initialized with self-healing capabilities")

    def get_circuit_breaker(self, name: str) -> CircuitBreaker:
        """Get or create a dynamic circuit breaker for a specific operation.

        Args:
             name: The name/identifier for the circuit breaker.

         Returns:
             CircuitBreaker instance for the specified operation.

         Raises:
             None. Creates a new circuit breaker if one doesn't exist.

         বাংলা: একটি নির্দিষ্ট অপারেশনের জন্য ডাইনামিক সার্কিট ব্রেকার পাওয়া বা তৈরি করে।
        """
        if name not in self.dynamic_circuit_breakers:
            self.dynamic_circuit_breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=settings.circuit_breaker_failure_threshold,
                recovery_timeout=settings.circuit_breaker_cooldown_period,
            )
        return self.dynamic_circuit_breakers[name]

    def _prune_expired_metrics(self, max_age_hours: int = 2) -> None:
        """TTL-ভিত্তিক ক্লিনআপ: ২ ঘণ্টার বেশি পুরোনো মেট্রিক্স এন্ট্রি মুছে ফেলা হয়।

        MAX_METRICS_ENTRIES (500) সীমা ছাড়ালে LRU (সবচেয়ে পুরোনো) এন্ট্রি ইভিক্ট করা হয়।
        """
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        expired_keys = [k for k, v in self.metrics.items() if v.last_updated < cutoff]
        for k in expired_keys:
            del self.metrics[k]

        # Hard-cap: সীমা ছাড়ালে LRU ইভিকশন
        MAX_METRICS_ENTRIES = 500
        if len(self.metrics) > MAX_METRICS_ENTRIES:
            sorted_keys = sorted(self.metrics, key=lambda k: self.metrics[k].last_updated)
            for k in sorted_keys[: len(self.metrics) - MAX_METRICS_ENTRIES]:
                del self.metrics[k]

    def _prune_inactive_model_stats(self) -> None:
        """যেসব মডেল সম্প্রতি metrics-এ সক্রিয় নেই, তাদের model_stats এন্ট্রি মুছে ফেলা হয়।"""
        active_models = set(self.metrics.keys())
        inactive = [m for m in list(self.model_stats) if m not in active_models]
        for m in inactive:
            del self.model_stats[m]

    async def track_performance(
        self, operation: str, execution_time: float, success: bool = True
    ) -> None:
        """Track performance metrics for an operation.

        বাংলা: Race condition এড়াতে asyncio.Lock দিয়ে atomic state update নিশ্চিত করে।
        """
        self._prune_expired_metrics()
        self._prune_inactive_model_stats()  # 🚀 model_stats মেমোরি ক্লিনআপ

        async with self._state_lock:  # 🔒 বাংলা: concurrent update থেকে shared state রক্ষা
            if operation not in self.metrics:
                self.metrics[operation] = PerformanceMetrics()

            metrics = self.metrics[operation]
            metrics.request_count += 1

            if not success:
                metrics.error_count += 1

            # Calculate moving average for response time
            total_time = metrics.avg_response_time * (metrics.request_count - 1) + execution_time
            metrics.avg_response_time = total_time / metrics.request_count

            # Update last updated time
            metrics.last_updated = datetime.now()

        # Log performance warnings (লক-এর বাইরে — I/O operation, lock ধরে রাখা উচিত নয়)
        if metrics.error_count > 0 and metrics.request_count > 0:
            error_rate = metrics.error_count / metrics.request_count
            if error_rate > 0.1:  # More than 10% errors
                logger.warning(f"⚠️ High error rate for {operation}: {error_rate:.2%}")

    async def optimize_model_selection(self, task_type: str, context: str = "") -> str:
        """Intelligently select the best model based on task type and context.

        Args:
            task_type: The type of task (reasoning, coding, general, etc.).
            context: Additional context for model selection.

        Returns:
            The selected model identifier string.

        Raises:
            None. Falls back to default model if no optimal model is found.

        বাংলা: টাস্ক টাইপ এবং কনটেক্সটের উপর ভিত্তি করে স্মার্টলি সেরা মডেল সিলেক্ট করে।
        """
        # Get models by tier and task requirements
        all_models = self.model_registry.MODELS

        # Filter models based on task type
        if task_type == "reasoning":
            suitable_models = [
                model_id
                for model_id, model_info in all_models.items()
                if "reasoning" in model_info.get("strengths", [])
            ]
        elif task_type == "coding":
            suitable_models = [
                model_id
                for model_id, model_info in all_models.items()
                if "coding" in model_info.get("strengths", [])
            ]
        else:
            # Default to general purpose models
            suitable_models = [
                model_id
                for model_id, model_info in all_models.items()
                if model_info.get("tier", 5) <= 2  # Tier 1 and 2 models
            ]

        if not suitable_models:
            # Fallback to any available model
            suitable_models = list(all_models.keys())

        # Select model based on availability and cost
        best_model = None
        best_score = float("-inf")

        for model_id in suitable_models:
            model_info = all_models[model_id]

            # Calculate score based on various factors
            score = 0

            # Tier weighting (higher tier = better quality)
            score += (10 - model_info.get("tier", 5)) * 10

            # Cost consideration (lower cost = higher score if quality is similar)
            cost_factor = 1 / (model_info.get("cost_input_per_million", 999999) + 1)
            score += cost_factor * 5

            # Context length consideration
            if model_info.get("context_length", 0) >= 100000:
                score += 5  # Bonus for large context

            # Check if API key is available
            provider = model_info.get("provider", "")
            api_key = self._get_api_key_for_provider(provider)
            if not api_key:
                score -= 100  # Heavy penalty for unavailable models

            if score > best_score:
                best_score = score
                best_model = model_id

        if best_model:
            # FINAL-TEST FIX (2026-09-13): brain registry aliases ("gemini-3.1-pro",
            # "gpt-5.4-pro", ...) are NOT litellm-resolvable model strings, so the
            # optimizer's pick used to fail at the head of every fallback chain and
            # burn a network round-trip. Translate to the real, key-backed model
            # for the provider instead.
            resolved = self._resolve_registry_model(best_model, task_type)
            logger.info(
                f"Selected optimal model '{best_model}' -> '{resolved}' for task '{task_type}'"
            )
            return resolved
        else:
            # Fallback to default model
            logger.warning("No optimal model found, falling back to default")
            return "gemini/gemini-2.5-flash"

    def _resolve_registry_model(self, model_id: str, task_type: str) -> str:
        """Translate a brain-registry model alias into a litellm-resolvable id.

        FINAL-TEST FIX (2026-09-13): only providers with a configured key are
        translated to a callable model; everything else falls back to the
        settings-driven default for the task type so the gateway chain starts
        with something that can actually answer.
        """
        info = self.model_registry.get_model(model_id) or {}
        provider = str(info.get("provider", "")).lower()
        try:
            has_key = bool(self._get_api_key_for_provider(provider))
        except Exception:
            has_key = False

        if provider == "google" and has_key:
            gem = str(getattr(settings, "gemini_model_name", "gemini/gemini-2.5-flash"))
            return gem if "/" in gem else f"gemini/{gem}"
        if provider == "openai" and has_key:
            return "openai/gpt-4o-mini"
        if provider == "huggingface" and has_key:
            swarm = getattr(settings, "MODEL_SWARM", {})
            return str(swarm.get(task_type) or swarm.get("general") or model_id)
        # No usable key for the chosen provider -> task-model default from settings.
        defaults = getattr(settings, "task_models", {})
        resolved = defaults.get(task_type) or defaults.get("general")
        return str(resolved) if resolved else "gemini/gemini-2.5-flash"

    def _get_api_key_for_provider(self, provider: str) -> str:
        """Get API key for a specific provider from settings.

        Args:
            provider: The provider name (anthropic, openai, google, etc.).

        Returns:
            API key string or empty string if not found.

        বাংলা: নির্দিষ্ট একটি প্রোভাইডারের জন্য সেটিংস থেকে API key পায়।
        """
        provider_keys = {
            "anthropic": settings.openrouter_api_key,
            "openai": settings.openai_api_key,
            "google": settings.gemini_api_key,
            "deepseek": settings.deepseek_api_key,
            "groq": settings.groq_api_key,
            "openrouter": settings.openrouter_api_key,
            "huggingface": settings.hf_api_key,
            "nvidia": settings.nvidia_api_key,
        }
        return provider_keys.get(provider, "")

    async def handle_failure(
        self, error_type: str, error_message: str, context: dict[str, Any]
    ) -> None:
        """Handle system failures with self-healing capabilities.

        Args:
            error_type: The type/category of the error.
            error_message: Detailed error message or description.
            context: Dictionary containing error context (tenant_id, dependency_tree, etc.)

        Returns:
            None

        Raises:
            None. Failures are logged and submitted for remediation if self-healer is available.

        বাংলা: সেলফ-হিলিং ক্ষমতা দিয়ে সিস্টেম ফেইলিওর হ্যান্ডল করে।
        """
        # Record failure in history
        # বাংলা: FailureHistoryEntry-এ সকল required field পূরণ করা হলো (mypy fix)
        failure_entry = FailureHistoryEntry(
            timestamp=datetime.now(),
            error_type=error_type,
            error_message=error_message,
            context=context,
            resolution="pending",  # প্রাথমিক অবস্থায় resolution 'pending' — self-healer পরে আপডেট করবে
        )
        self.failure_history.append(failure_entry)

        # Keep only recent failures to prevent memory bloat
        if len(self.failure_history) > 100:
            self.failure_history = self.failure_history[-100:]

        logger.error(f"Failure recorded: {error_type} - {error_message}")

        # Trigger self-healing if possible
        if self.self_healer and self.reminder_pipeline:
            try:
                # Analyze the error and propose a fix
                error_signature = self._generate_error_signature(error_type, error_message, context)

                # Create a proposed fix based on error pattern
                proposed_fix = await self._generate_fix_proposal(error_type, error_message, context)

                # Submit the fix for remediation
                impact_score = self._calculate_impact_score(error_type)

                fix_id = await self.reminder_pipeline.submit(
                    tenant_id=context.get("tenant_id", "system"),
                    error_pattern=error_signature,
                    proposed_fix=proposed_fix,
                    impact_score=impact_score,
                    dependency_tree=context.get("dependency_tree", ["system"]),
                )

                logger.info(f"Submitted auto-fix for error '{error_type}', fix ID: {fix_id}")

            except Exception as e:
                logger.error(f"Failed to submit auto-fix: {e}")

    def _generate_error_signature(
        self, error_type: str, error_message: str, context: dict[str, Any]
    ) -> str:
        """Generate a unique signature for the error pattern.

        Args:
            error_type: Type of the error.
            error_message: Error message.
            context: Error context dictionary.

        Returns:
            SHA-256 hash (first 16 chars) of the error signature.

        বাংলা: এরর প্যাটার্নের জন্য একটি ইউনিক সিগনachar জেনারেট করে।
        """
        error_data = {
            "type": error_type,
            "message": error_message,
            "context_keys": sorted(context.keys()) if context else [],
        }
        error_json = json.dumps(error_data, sort_keys=True, default=str)
        return hashlib.sha256(error_json.encode()).hexdigest()[:16]

    async def _generate_fix_proposal(
        self, error_type: str, error_message: str, context: dict[str, Any]
    ) -> str:
        """Generate a potential fix for the error.

        Args:
            error_type: Type of the error.
            error_message: Error message.
            context: Error context.

        Returns:
            A string containing the proposed fix and implementation suggestion.

        বাংলা: এররের জন্য একটি সম্ভাব্য ফিক্স প্রপোজাল তৈরি করে।
        """
        # For demonstration, creating a simple fix proposal
        # In a real system, this would use more sophisticated AI reasoning
        fix_proposals = {
            "LLM_GATEWAY_TIMEOUT": "Increase timeout settings in config",
            "CIRCUIT_BREAKER_OPEN": "Wait for circuit to recover or investigate root cause",
            "RATE_LIMIT_EXCEEDED": "Implement retry logic with exponential backoff",
            "INVALID_API_KEY": "Verify API key configuration in environment",
            "CONNECTION_ERROR": "Check network connectivity and service availability",
        }

        proposal = fix_proposals.get(
            error_type, f"Manual investigation required for: {error_message}"
        )

        return f"""
# Auto-generated fix proposal for: {error_type}
# Context: {context}

{proposal}

# Implementation suggestion:
# 1. Analyze the error pattern
# 2. Implement appropriate error handling
# 3. Consider circuit breaker adjustments
# 4. Verify configuration settings
"""

    def _calculate_impact_score(self, error_type: str) -> float:
        """Calculate impact score for the error (0.0 to 1.0).

        Args:
            error_type: The type of error.

        Returns:
            Float between 0.0 and 1.0 indicating impact severity.

        বাংলা: এররের জন্য ইমপ্যাক্ট স্কোর ক্যালকুলেট করে (০.০ থেকে ১.০ পর্যন্ত)।
        """
        high_impact_errors = [
            "LLM_GATEWAY_TIMEOUT",
            "CONNECTION_ERROR",
            "INVALID_API_KEY",
            "DATABASE_CONNECTION_FAILED",
            "AUTHENTICATION_FAILED",
        ]

        if error_type in high_impact_errors:
            return 0.8
        elif "PERFORMANCE" in error_type.upper():
            return 0.6
        else:
            return 0.3

    async def adaptive_load_balancing(
        self, task_type: str, workload: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Distribute workload intelligently based on current system capacity.

        Args:
            task_type: Type of tasks being distributed.
            workload: List of work items to process.

        Returns:
            List of processed results.

        বাংলা: বর্তমান সিস্টেম ক্যাপাসিটির উপর ভিত্তি করে বুদ্ধিমানে ওয়ার্কলোড ডিস্ট্রিবিউট করে।
        """
        # Track current system load
        active_tasks = len(
            [
                m
                for m in self.metrics.values()
                if m.last_updated > datetime.now() - timedelta(seconds=30)
            ]
        )

        # Adjust processing strategy based on load
        if active_tasks > 10:  # High load
            logger.warning("High system load detected, optimizing task distribution")
            # Reduce concurrent processing
            chunk_size = max(1, len(workload) // 5)  # Process in smaller chunks
        else:
            chunk_size = max(1, len(workload) // 2)  # Process in larger chunks

        # Distribute tasks in chunks
        processed_workload = []
        for i in range(0, len(workload), chunk_size):
            chunk = workload[i : i + chunk_size]
            processed_chunk = await self._process_workload_chunk(task_type, chunk)
            processed_workload.extend(processed_chunk)

            # Small delay between chunks to prevent overwhelming
            if active_tasks > 5:
                await asyncio.sleep(0.1)

        return processed_workload

    async def _process_workload_chunk(
        self, task_type: str, chunk: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Process a chunk of workload with appropriate error handling.

        Args:
            task_type: Type of tasks in the chunk.
            chunk: List of work items to process.

        Returns:
            List of results for the chunk.

        বাংলা: সাম্প্রতিক এরর হ্যান্ডলিং সহ ওয়ার্কলোড চাঙ্ক প্রসেস করে।
        """
        results = []

        for item in chunk:
            try:
                # Select optimal model for this specific task
                model = await self.optimize_model_selection(task_type)

                # Execute the task - for now we'll skip the direct LLM call to avoid circular import
                start_time = time.time()

                # Instead of calling LLM directly, we'll return a simulated result
                # This avoids importing llm_gateway which causes circular import
                result = {
                    "success": True,
                    "text": f"Simulated result for task: {item.get('prompt', 'default prompt')}",
                    "model": model,
                    "cost": 0.0,
                }

                execution_time = time.time() - start_time
                await self.track_performance(f"task_{task_type}", execution_time, success=True)
                results.append(result)

            except Exception as e:
                execution_time = time.time() - start_time
                await self.track_performance(f"task_{task_type}", execution_time, success=False)

                # Handle the failure with self-healing
                await self.handle_failure(
                    error_type="TASK_EXECUTION_ERROR",
                    error_message=str(e),
                    context={"task_type": task_type, "item": item, "error": str(e)},
                )

                # Return error result
                results.append(
                    {
                        "success": False,
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                    }
                )

        return results

    async def _execute_task_with_model(self, item: dict[str, Any], model: str) -> dict[str, Any]:
        """Execute a single task with the specified model.

        Args:
            item: Task item to execute.
            model: Model identifier to use.

        Returns:
            Result dictionary with success status and output.

        বাংলা: নির্দিষ্ট মডেল দিয়ে একটি単一 টাস্ক এক্সিকিউট করে।
        """
        # This method will be implemented to work with the LLM gateway
        # but we'll avoid direct import to prevent circular dependencies
        # For now, we return a simulated response
        return {
            "success": True,
            "text": f"Processed with model {model}: {item.get('prompt', 'default')}",
            "model": model,
            "cost": 0.0,
        }


# Global instance of the performance optimizer
performance_optimizer = PerformanceOptimizer()


def get_performance_optimizer() -> PerformanceOptimizer:
    """Get the global performance optimizer instance.

    Returns:
        PerformanceOptimizer: The global instance of the performance optimizer.

    বাংলা: গ্লোবাল পারফরম্যান্স অপ্টিমাইজার ইনস্ট্যান্স রিটার্ন করে।
    """
    return performance_optimizer
