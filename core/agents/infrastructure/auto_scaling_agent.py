"""
Auto-Scaling Agent for SupremeAI 2.0
Dynamically adjusts resources based on demand to optimize performance and costs.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psutil  # This may need to be installed separately

from core.cache.redis_manager import redis_manager
from core.errors.error_bus import with_error_bus
from core.llm.token_deductor import TokenDeductor
from core.logging_config import logger
from core.utils.background_tasks import track_task
from monitoring.metrics_collector import MetricsCollector


@dataclass
class ScalingRecommendation:
    """Data class to hold scaling recommendations."""

    current_resources: dict[str, float]
    recommended_resources: dict[str, float]
    reason: str
    confidence: float
    timestamp: datetime
    cost_impact: float  # Estimated cost impact of scaling action


@dataclass
class ResourceMetrics:
    """Data class to hold resource metrics."""

    cpu_usage: float  # Percentage
    memory_usage: float  # Percentage
    disk_usage: float  # Percentage
    network_io: float  # MB/s
    active_connections: int
    requests_per_second: float
    average_response_time: float  # ms
    error_rate: float  # Percentage
    timestamp: datetime


class AutoScalingAgent:
    """Agent that dynamically adjusts resources based on demand."""

    def __init__(self):
        self.name = "Auto-Scaling Agent"
        self.token_deductor = TokenDeductor()
        self.metrics_collector = MetricsCollector() if "MetricsCollector" in globals() else None
        self.scaling_history_key = "autoscaling:history"
        self.current_metrics_key = "autoscaling:current_metrics"
        self.scaling_policies_key = "autoscaling:policies"
        self.target_metrics = {
            "cpu_target": 70.0,  # Target CPU utilization percentage
            "memory_target": 75.0,  # Target memory utilization percentage
            "response_time_target": 500.0,  # Target response time in ms
            "error_rate_max": 5.0,  # Maximum acceptable error rate percentage
            "rps_target": 100.0,  # Target requests per second per instance
        }

        # Scaling thresholds
        self.scale_up_thresholds = {
            "cpu": 80.0,
            "memory": 85.0,
            "response_time": 1000.0,
            "rps": 150.0,
        }

        self.scale_down_thresholds = {"cpu": 30.0, "memory": 40.0, "rps": 30.0}

        # Resource limits
        self.resource_limits = {
            "min_instances": 1,
            "max_instances": 10,
            "max_cpu_percent": 95.0,
            "max_memory_percent": 95.0,
        }

    async def initialize_policies(self):
        """Initialize auto-scaling policies in Redis."""
        try:
            existing_policies = await redis_manager.get(self.scaling_policies_key)
            if not existing_policies:
                default_policies = {
                    "target_metrics": self.target_metrics,
                    "scale_up_thresholds": self.scale_up_thresholds,
                    "scale_down_thresholds": self.scale_down_thresholds,
                    "resource_limits": self.resource_limits,
                    "cooldown_period": 300,  # 5 minutes cooldown between scaling actions
                    "scaling_enabled": True,
                }

                await redis_manager.set(
                    self.scaling_policies_key,
                    json.dumps(default_policies),
                    ex=2592000,  # 30 days
                )
                logger.info("Default auto-scaling policies initialized")
        except Exception as e:
            logger.error(f"Error initializing auto-scaling policies: {e}")

    @with_error_bus("collect_current_metrics")
    async def collect_current_metrics(self) -> ResourceMetrics:
        """Collect current system resource metrics."""
        try:
            # Collect system-level metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory_percent = psutil.virtual_memory().percent
            disk_percent = psutil.disk_usage("/").percent if hasattr(psutil, "disk_usage") else 0

            # Get network I/O (simplified)
            net_io = psutil.net_io_counters()
            network_io_mb = (net_io.bytes_sent + net_io.bytes_recv) / (1024 * 1024)  # Convert to MB

            # Collect application-level metrics if available
            active_connections = 0
            requests_per_second = 0
            average_response_time = 0
            error_rate = 0

            # This would typically come from the application metrics collector
            # For now, we'll simulate values
            try:
                if self.metrics_collector:
                    app_metrics = await self.metrics_collector.get_recent_metrics(minutes=1)
                    if app_metrics:
                        active_connections = app_metrics.get("active_connections", 0)
                        requests_per_second = app_metrics.get("requests_per_second", 0)
                        average_response_time = app_metrics.get("avg_response_time", 0)
                        error_rate = app_metrics.get("error_rate", 0)
            except Exception:
                # If metrics collector is not available, use simulated values
                active_connections = 10
                requests_per_second = 50
                average_response_time = 200
                error_rate = 1.0

            metrics = ResourceMetrics(
                cpu_usage=cpu_percent,
                memory_usage=memory_percent,
                disk_usage=disk_percent,
                network_io=network_io_mb,
                active_connections=active_connections,
                requests_per_second=requests_per_second,
                average_response_time=average_response_time,
                error_rate=error_rate,
                timestamp=datetime.utcnow(),
            )

            # Store current metrics in Redis
            metrics_data = {
                "cpu_usage": metrics.cpu_usage,
                "memory_usage": metrics.memory_usage,
                "disk_usage": metrics.disk_usage,
                "network_io": metrics.network_io,
                "active_connections": metrics.active_connections,
                "requests_per_second": metrics.requests_per_second,
                "average_response_time": metrics.average_response_time,
                "error_rate": metrics.error_rate,
                "timestamp": metrics.timestamp.isoformat(),
            }

            await redis_manager.set(
                self.current_metrics_key,
                json.dumps(metrics_data),
                ex=300,  # 5 minutes
            )

            return metrics
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
            # Return default metrics in case of error
            return ResourceMetrics(
                cpu_usage=50.0,
                memory_usage=50.0,
                disk_usage=50.0,
                network_io=1.0,
                active_connections=5,
                requests_per_second=25,
                average_response_time=250.0,
                error_rate=0.5,
                timestamp=datetime.utcnow(),
            )

    async def analyze_scaling_need(self, current_metrics: ResourceMetrics) -> ScalingRecommendation:
        """Analyze if scaling is needed based on current metrics."""
        try:
            # Get current policies
            policies = await self._get_policies()
            if not policies.get("scaling_enabled", True):
                return ScalingRecommendation(
                    current_resources={},
                    recommended_resources={},
                    reason="Auto-scaling is disabled",
                    confidence=1.0,
                    timestamp=datetime.utcnow(),
                    cost_impact=0.0,
                )

            # Get current resource allocation (simulated)
            current_resources = await self._get_current_resource_allocation()

            # Determine scaling direction based on metrics
            scale_direction = self._determine_scaling_direction(current_metrics, policies)

            if scale_direction == 0:  # No scaling needed
                return ScalingRecommendation(
                    current_resources=current_resources,
                    recommended_resources=current_resources.copy(),
                    reason="Resource usage is within acceptable ranges",
                    confidence=0.9,
                    timestamp=datetime.utcnow(),
                    cost_impact=0.0,
                )

            # Calculate recommended resource adjustment
            recommended_resources = self._calculate_resource_adjustment(
                current_resources, current_metrics, scale_direction, policies
            )

            # Determine reason for scaling
            reasons = []
            if current_metrics.cpu_usage > policies["scale_up_thresholds"]["cpu"]:
                reasons.append(
                    f"CPU usage ({current_metrics.cpu_usage}%) exceeds threshold ({policies['scale_up_thresholds']['cpu']}%)"
                )
            elif current_metrics.cpu_usage < policies["scale_down_thresholds"]["cpu"]:
                reasons.append(
                    f"CPU usage ({current_metrics.cpu_usage}%) below threshold ({policies['scale_down_thresholds']['cpu']}%)"
                )

            if current_metrics.memory_usage > policies["scale_up_thresholds"]["memory"]:
                reasons.append(
                    f"Memory usage ({current_metrics.memory_usage}%) exceeds threshold ({policies['scale_up_thresholds']['memory']}%)"
                )
            elif current_metrics.memory_usage < policies["scale_down_thresholds"]["memory"]:
                reasons.append(
                    f"Memory usage ({current_metrics.memory_usage}%) below threshold ({policies['scale_down_thresholds']['memory']}%)"
                )

            if (
                current_metrics.average_response_time
                > policies["scale_up_thresholds"]["response_time"]
            ):
                reasons.append(
                    f"Response time ({current_metrics.average_response_time}ms) exceeds threshold ({policies['scale_up_thresholds']['response_time']}ms)"
                )

            if current_metrics.requests_per_second > policies["scale_up_thresholds"]["rps"]:
                reasons.append(
                    f"Requests per second ({current_metrics.requests_per_second}) exceeds threshold ({policies['scale_up_thresholds']['rps']})"
                )
            elif current_metrics.requests_per_second < policies["scale_down_thresholds"]["rps"]:
                reasons.append(
                    f"Requests per second ({current_metrics.requests_per_second}) below threshold ({policies['scale_down_thresholds']['rps']})"
                )

            reason = (
                "; ".join(reasons)
                if reasons
                else "Resource usage patterns indicate scaling opportunity"
            )

            # Calculate estimated cost impact
            cost_impact = self._estimate_cost_impact(current_resources, recommended_resources)

            confidence = self._calculate_scaling_confidence(current_metrics, scale_direction)

            return ScalingRecommendation(
                current_resources=current_resources,
                recommended_resources=recommended_resources,
                reason=reason,
                confidence=confidence,
                timestamp=datetime.utcnow(),
                cost_impact=cost_impact,
            )
        except Exception as e:
            logger.error(f"Error analyzing scaling need: {e}")
            # Return neutral recommendation in case of error
            current_resources = await self._get_current_resource_allocation()
            return ScalingRecommendation(
                current_resources=current_resources,
                recommended_resources=current_resources.copy(),
                reason=f"Error analyzing scaling need: {e!s}",
                confidence=0.0,
                timestamp=datetime.utcnow(),
                cost_impact=0.0,
            )

    async def execute_scaling_action(self, recommendation: ScalingRecommendation) -> bool:
        """Execute the scaling action based on recommendation."""
        try:
            # Check cooldown period to prevent excessive scaling
            last_scaling_time = await self._get_last_scaling_time()
            cooldown_period = (await self._get_policies()).get("cooldown_period", 300)  # 5 minutes

            if (
                last_scaling_time
                and (datetime.utcnow() - last_scaling_time).seconds < cooldown_period
            ):
                logger.info("Skipping scaling action due to cooldown period")
                return False

            # Implement the scaling action
            # This would typically involve calling cloud provider APIs
            # For simulation, we'll just log the action
            scaling_successful = await self._perform_scaling(recommendation.recommended_resources)

            if scaling_successful:
                # Record scaling action
                await self._record_scaling_action(recommendation)
                logger.info(
                    f"Successfully scaled resources: {recommendation.recommended_resources}"
                )
            else:
                logger.warning(f"Failed to scale resources: {recommendation.recommended_resources}")

            return scaling_successful
        except Exception as e:
            logger.error(f"Error executing scaling action: {e}")
            return False

    def _determine_scaling_direction(self, metrics: ResourceMetrics, policies: dict) -> int:
        """
        Determine scaling direction.
        Returns: 1 for scale up, -1 for scale down, 0 for no change.
        """
        scale_up_triggered = (
            metrics.cpu_usage > policies["scale_up_thresholds"]["cpu"]
            or metrics.memory_usage > policies["scale_up_thresholds"]["memory"]
            or metrics.average_response_time > policies["scale_up_thresholds"]["response_time"]
            or metrics.requests_per_second > policies["scale_up_thresholds"]["rps"]
        )

        scale_down_triggered = (
            metrics.cpu_usage < policies["scale_down_thresholds"]["cpu"]
            and metrics.memory_usage < policies["scale_down_thresholds"]["memory"]
            and metrics.requests_per_second < policies["scale_down_thresholds"]["rps"]
        )

        if scale_up_triggered:
            return 1
        elif scale_down_triggered:
            return -1
        else:
            return 0

    def _calculate_resource_adjustment(
        self,
        current_resources: dict[str, float],
        metrics: ResourceMetrics,
        direction: int,
        policies: dict,
    ) -> dict[str, float]:
        """Calculate the recommended resource adjustment."""
        recommended = current_resources.copy()

        # Adjust based on direction
        if direction == 1:  # Scale up
            # Increase instances by 1 or by 20% of current, whichever is greater
            current_instances = recommended.get("instances", 1)
            increase_by = max(1, int(current_instances * 0.2))
            new_instances = min(
                current_instances + increase_by, policies["resource_limits"]["max_instances"]
            )
            recommended["instances"] = new_instances

            # Potentially increase other resources too
            if metrics.cpu_usage > policies["scale_up_thresholds"]["cpu"]:
                recommended["cpu_cores"] = recommended.get("cpu_cores", 1) + 0.5
            if metrics.memory_usage > policies["scale_up_thresholds"]["memory"]:
                recommended["memory_gb"] = recommended.get("memory_gb", 1) + 1.0

        elif direction == -1:  # Scale down
            # Decrease instances by 1 or by 20% of current, whichever is greater, but respect minimum
            current_instances = recommended.get("instances", 1)
            decrease_by = max(1, int(current_instances * 0.2))
            new_instances = max(
                current_instances - decrease_by, policies["resource_limits"]["min_instances"]
            )
            recommended["instances"] = new_instances

            # Potentially decrease other resources too
            if metrics.cpu_usage < policies["scale_down_thresholds"]["cpu"]:
                recommended["cpu_cores"] = max(recommended.get("cpu_cores", 1) - 0.5, 0.5)
            if metrics.memory_usage < policies["scale_down_thresholds"]["memory"]:
                recommended["memory_gb"] = max(recommended.get("memory_gb", 1) - 1.0, 0.5)

        return recommended

    async def _get_current_resource_allocation(self) -> dict[str, float]:
        """Get current resource allocation (simulated)."""
        try:
            # This would typically query the infrastructure provider
            # For now, return default values
            return {"instances": 2, "cpu_cores": 2.0, "memory_gb": 4.0, "disk_gb": 20.0}
        except Exception as e:
            logger.error(f"Error getting current resource allocation: {e}")
            return {"instances": 1, "cpu_cores": 1.0, "memory_gb": 2.0, "disk_gb": 10.0}

    async def _perform_scaling(self, target_resources: dict[str, float]) -> bool:
        """Perform the actual scaling operation (simulated)."""
        try:
            # This would typically call cloud provider APIs to adjust resources
            # For simulation purposes, just log the intended action
            logger.info(f"Intended scaling action: {target_resources}")

            # Simulate a successful scaling operation
            # In real implementation, this would interact with cloud providers
            await asyncio.sleep(0.1)  # Simulate API call delay

            # Update last scaling time
            await redis_manager.set(
                "autoscaling:last_scale_time",
                datetime.utcnow().isoformat(),
                ex=2592000,  # 30 days
            )

            return True
        except Exception as e:
            logger.error(f"Error performing scaling: {e}")
            return False

    @with_error_bus("_estimate_cost_impact")
    def _estimate_cost_impact(
        self, current: dict[str, float], recommended: dict[str, float]
    ) -> float:
        """Estimate the cost impact of scaling action."""
        try:
            # Simplified cost estimation
            current_cost = sum(current.values())  # Simplified calculation
            recommended_cost = sum(recommended.values())  # Simplified calculation

            return recommended_cost - current_cost
        except Exception:
            return 0.0

    @with_error_bus("_calculate_scaling_confidence")
    def _calculate_scaling_confidence(self, metrics: ResourceMetrics, direction: int) -> float:
        """Calculate confidence in the scaling recommendation."""
        try:
            if direction == 0:
                return 0.9  # High confidence in "no change" when metrics are stable

            # Calculate confidence based on how far metrics are from thresholds
            confidence_factors = []

            if direction == 1:  # Scale up
                cpu_factor = min(1.0, (metrics.cpu_usage - 70.0) / 30.0)  # Max at 100%
                mem_factor = min(1.0, (metrics.memory_usage - 75.0) / 25.0)  # Max at 100%
                resp_factor = min(
                    1.0, (metrics.average_response_time - 500.0) / 1000.0
                )  # Max at 1500ms
                confidence_factors.extend([cpu_factor, mem_factor, resp_factor])
            else:  # Scale down
                cpu_factor = min(
                    1.0, (30.0 - metrics.cpu_usage) / 30.0
                )  # Higher confidence when much lower
                mem_factor = min(1.0, (40.0 - metrics.memory_usage) / 40.0)
                rps_factor = min(1.0, (30.0 - metrics.requests_per_second) / 30.0)
                confidence_factors.extend([cpu_factor, mem_factor, rps_factor])

            # Average the factors and ensure it's between 0.5 and 1.0
            avg_confidence = (
                sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5
            )
            return max(0.5, min(1.0, avg_confidence))
        except Exception:
            return 0.7  # Default confidence

    @with_error_bus("_get_last_scaling_time")
    async def _get_last_scaling_time(self) -> datetime | None:
        """Get the time of the last scaling action."""
        try:
            last_time_str = await redis_manager.get("autoscaling:last_scale_time")
            if last_time_str:
                return datetime.fromisoformat(last_time_str)
            return None
        except Exception:
            return None

    async def _record_scaling_action(self, recommendation: ScalingRecommendation):
        """Record the scaling action in history."""
        try:
            action_data = {
                "current_resources": recommendation.current_resources,
                "recommended_resources": recommendation.recommended_resources,
                "reason": recommendation.reason,
                "confidence": recommendation.confidence,
                "cost_impact": recommendation.cost_impact,
                "timestamp": recommendation.timestamp.isoformat(),
            }

            # Get existing history
            history = await redis_manager.get(self.scaling_history_key)
            if history:
                history_list = json.loads(history)
            else:
                history_list = []

            # Add new action
            history_list.append(action_data)

            # Keep only the last N actions
            max_history = 100
            if len(history_list) > max_history:
                history_list = history_list[-max_history:]

            await redis_manager.set(
                self.scaling_history_key,
                json.dumps(history_list),
                ex=2592000,  # 30 days
            )
        except Exception as e:
            logger.error(f"Error recording scaling action: {e}")

    async def _get_policies(self) -> dict[str, Any]:
        """Get current auto-scaling policies."""
        try:
            policies_json = await redis_manager.get(self.scaling_policies_key)
            if policies_json:
                return json.loads(policies_json)
            else:
                return {}
        except Exception as e:
            logger.error(f"Error getting policies: {e}")
            return {}


# Global instance
auto_scaling_agent = AutoScalingAgent()

# Initialize scaling policy on module load — শুধুমাত্র একটা event loop চলমান থাকলেই টাস্ক শিডিউল করা হয়;
# বাংলা: import-time-এ event loop না থাকলে RuntimeError এড়ানো হয়, আর টাস্কের রেফারেন্স ট্র্যাক করে
# রাখা হয় যাতে GC হয়ে মাঝপথে বাতিল না হয়ে যায় (RUF006)।
try:
    track_task(asyncio.get_running_loop().create_task(auto_scaling_agent.initialize_policies()))
except RuntimeError:
    logger.debug(
        "No running event loop at import time; skipping eager scaling policy init "
        "(call initialize_policies() explicitly during app startup instead)."
    )
