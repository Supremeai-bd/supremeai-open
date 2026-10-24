"""
Performance Tuning Agent for SupremeAI 2.0
Continuously optimizes system performance based on metrics and usage patterns.
"""

import asyncio
import json
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import psutil

from core.cache.redis_manager import redis_manager
from core.errors.error_bus import with_error_bus
from core.llm.token_deductor import TokenDeductor
from core.logging_config import logger
from monitoring.metrics_collector import MetricsCollector


@dataclass
class PerformanceMetric:
    """Data class to hold performance metric information."""

    timestamp: datetime
    cpu_usage: float  # Percentage
    memory_usage: float  # Percentage
    disk_io_read: float  # MB/s
    disk_io_write: float  # MB/s
    network_io_in: float  # MB/s
    network_io_out: float  # MB/s
    response_time_ms: float
    requests_per_second: float
    error_rate: float  # Percentage
    active_connections: int
    queue_depth: int


@dataclass
class OptimizationRecommendation:
    """Data class to hold performance optimization recommendations."""

    component: str
    recommendation: str
    expected_impact: str  # low, medium, high
    confidence: float  # 0.0 to 1.0
    implementation_effort: str  # low, medium, high
    timestamp: datetime


@dataclass
class PerformanceTuningResult:
    """Data class to hold performance tuning results."""

    optimization_id: str
    timestamp: datetime
    applied_optimizations: list[str]
    performance_improvement: dict[str, float]  # Before/after metrics
    status: str  # success, partial, failed
    notes: str


class PerformanceTuningAgent:
    """Agent that continuously optimizes system performance."""

    def __init__(self):
        self.name = "Performance Tuning Agent"
        self.token_deductor = TokenDeductor()
        self.metrics_collector = MetricsCollector() if "MetricsCollector" in globals() else None
        self.performance_metrics_key = "performance_tuning:metrics"
        self.optimization_history_key = "performance_tuning:optimization_history"
        self.tuning_recommendations_key = "performance_tuning:recommendations"
        self.system_config_key = "performance_tuning:system_config"

        # Performance thresholds and targets
        self.performance_targets = {
            "cpu_target": 70.0,  # Target CPU utilization
            "memory_target": 75.0,  # Target memory utilization
            "response_time_target": 200.0,  # Target response time in ms
            "error_rate_target": 1.0,  # Target error rate percentage
            "rps_target": 100.0,  # Target requests per second per instance
        }

        self.performance_thresholds = {
            "cpu_high": 85.0,  # Threshold for CPU optimization
            "memory_high": 90.0,  # Threshold for memory optimization
            "response_time_high": 1000.0,  # Threshold for response time optimization
            "error_rate_high": 5.0,  # Threshold for error optimization
            "queue_depth_high": 50,  # Threshold for queue optimization
        }

        # Maintain metric history for trend analysis
        self.metric_history_size = 100
        self.response_time_history = deque(maxlen=self.metric_history_size)
        self.cpu_usage_history = deque(maxlen=self.metric_history_size)
        self.memory_usage_history = deque(maxlen=self.metric_history_size)

        # Available optimizations
        self.available_optimizations = {
            "caching": {
                "description": "Implement or tune caching strategies",
                "components": ["database", "api", "static_content"],
                "typical_impact": "high",
                "implementation_effort": "medium",
            },
            "database_indexing": {
                "description": "Optimize database queries with proper indexing",
                "components": ["database"],
                "typical_impact": "high",
                "implementation_effort": "medium",
            },
            "connection_pooling": {
                "description": "Optimize connection pooling settings",
                "components": ["database", "external_apis"],
                "typical_impact": "medium",
                "implementation_effort": "low",
            },
            "load_balancing": {
                "description": "Adjust load balancing strategies",
                "components": ["api", "web_server"],
                "typical_impact": "medium",
                "implementation_effort": "high",
            },
            "resource_allocation": {
                "description": "Adjust system resource allocation",
                "components": ["system", "containers"],
                "typical_impact": "high",
                "implementation_effort": "medium",
            },
            "garbage_collection": {
                "description": "Tune garbage collection parameters",
                "components": ["runtime", "application"],
                "typical_impact": "medium",
                "implementation_effort": "low",
            },
            "compression": {
                "description": "Enable or optimize data compression",
                "components": ["network", "storage"],
                "typical_impact": "medium",
                "implementation_effort": "low",
            },
            "async_processing": {
                "description": "Convert synchronous operations to async",
                "components": ["api", "processing"],
                "typical_impact": "high",
                "implementation_effort": "high",
            },
        }

    @with_error_bus("collect_performance_metrics")
    async def collect_performance_metrics(self) -> PerformanceMetric:
        """Collect current system performance metrics."""
        try:
            # Collect system-level metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory_percent = psutil.virtual_memory().percent

            # Get disk I/O stats
            disk_io = psutil.disk_io_counters()
            disk_read_mb = (disk_io.read_bytes / (1024 * 1024)) if disk_io else 0
            disk_write_mb = (disk_io.write_bytes / (1024 * 1024)) if disk_io else 0

            # Get network I/O stats
            net_io = psutil.net_io_counters()
            net_in_mb = (net_io.bytes_recv / (1024 * 1024)) if net_io else 0
            net_out_mb = (net_io.bytes_sent / (1024 * 1024)) if net_io else 0

            # Collect application-level metrics
            active_connections = 0
            response_time_ms = 0
            requests_per_second = 0
            error_rate = 0
            queue_depth = 0

            # This would typically come from the application metrics collector
            try:
                if self.metrics_collector:
                    app_metrics = await self.metrics_collector.get_recent_metrics(minutes=1)
                    if app_metrics:
                        active_connections = app_metrics.get("active_connections", 0)
                        response_time_ms = app_metrics.get("avg_response_time", 0)
                        requests_per_second = app_metrics.get("requests_per_second", 0)
                        error_rate = app_metrics.get("error_rate", 0)
                        queue_depth = app_metrics.get("queue_depth", 0)
            except Exception:
                # Fallback values if metrics collector unavailable
                active_connections = 10
                response_time_ms = 150
                requests_per_second = 50
                error_rate = 0.5
                queue_depth = 5

            # Update history deques
            self.response_time_history.append(response_time_ms)
            self.cpu_usage_history.append(cpu_percent)
            self.memory_usage_history.append(memory_percent)

            # Create metric object
            metric = PerformanceMetric(
                timestamp=datetime.utcnow(),
                cpu_usage=cpu_percent,
                memory_usage=memory_percent,
                disk_io_read=disk_read_mb,
                disk_io_write=disk_write_mb,
                network_io_in=net_in_mb,
                network_io_out=net_out_mb,
                response_time_ms=response_time_ms,
                requests_per_second=requests_per_second,
                error_rate=error_rate,
                active_connections=active_connections,
                queue_depth=queue_depth,
            )

            # Store metric in Redis
            metric_data = {
                "timestamp": metric.timestamp.isoformat(),
                "cpu_usage": metric.cpu_usage,
                "memory_usage": metric.memory_usage,
                "disk_io_read": metric.disk_io_read,
                "disk_io_write": metric.disk_io_write,
                "network_io_in": metric.network_io_in,
                "network_io_out": metric.network_io_out,
                "response_time_ms": metric.response_time_ms,
                "requests_per_second": metric.requests_per_second,
                "error_rate": metric.error_rate,
                "active_connections": metric.active_connections,
                "queue_depth": metric.queue_depth,
            }

            # Add to metrics history in Redis
            existing_metrics = await redis_manager.get(self.performance_metrics_key)
            if existing_metrics:
                metrics_list = json.loads(existing_metrics)
            else:
                metrics_list = []

            metrics_list.append(metric_data)

            # Keep only the last N metrics
            max_metrics = 1000
            if len(metrics_list) > max_metrics:
                metrics_list = metrics_list[-max_metrics:]

            await redis_manager.set(
                self.performance_metrics_key,
                json.dumps(metrics_list),
                ex=2592000,  # 30 days
            )

            return metric
        except Exception as e:
            logger.error(f"Error collecting performance metrics: {e}")
            # Return default metrics in case of error
            return PerformanceMetric(
                timestamp=datetime.utcnow(),
                cpu_usage=50.0,
                memory_usage=50.0,
                disk_io_read=0.0,
                disk_io_write=0.0,
                network_io_in=0.0,
                network_io_out=0.0,
                response_time_ms=200.0,
                requests_per_second=25.0,
                error_rate=0.1,
                active_connections=5,
                queue_depth=2,
            )

    async def analyze_performance_trends(self) -> list[OptimizationRecommendation]:
        """Analyze performance metrics to identify optimization opportunities."""
        try:
            recommendations = []

            # Get current metrics
            current_metric = await self.collect_performance_metrics()

            # Check for CPU optimization opportunities
            if current_metric.cpu_usage > self.performance_thresholds["cpu_high"]:
                recommendations.append(
                    OptimizationRecommendation(
                        component="system",
                        recommendation="CPU usage is high. Consider implementing async processing or optimizing algorithms.",
                        expected_impact="high",
                        confidence=0.8,
                        implementation_effort="high",
                        timestamp=datetime.utcnow(),
                    )
                )

            # Check for memory optimization opportunities
            if current_metric.memory_usage > self.performance_thresholds["memory_high"]:
                recommendations.append(
                    OptimizationRecommendation(
                        component="system",
                        recommendation="Memory usage is high. Consider implementing caching strategies or optimizing memory management.",
                        expected_impact="high",
                        confidence=0.7,
                        implementation_effort="medium",
                        timestamp=datetime.utcnow(),
                    )
                )

            # Check for response time optimization opportunities
            if current_metric.response_time_ms > self.performance_thresholds["response_time_high"]:
                recommendations.append(
                    OptimizationRecommendation(
                        component="api",
                        recommendation="Response time is high. Consider implementing caching or optimizing database queries.",
                        expected_impact="high",
                        confidence=0.9,
                        implementation_effort="medium",
                        timestamp=datetime.utcnow(),
                    )
                )

            # Check for error rate optimization opportunities
            if current_metric.error_rate > self.performance_thresholds["error_rate_high"]:
                recommendations.append(
                    OptimizationRecommendation(
                        component="system",
                        recommendation="Error rate is high. Consider improving error handling and resilience.",
                        expected_impact="medium",
                        confidence=0.6,
                        implementation_effort="medium",
                        timestamp=datetime.utcnow(),
                    )
                )

            # Check for queue depth optimization opportunities
            if current_metric.queue_depth > self.performance_thresholds["queue_depth_high"]:
                recommendations.append(
                    OptimizationRecommendation(
                        component="messaging",
                        recommendation="Queue depth is high. Consider scaling consumers or optimizing processing.",
                        expected_impact="high",
                        confidence=0.8,
                        implementation_effort="medium",
                        timestamp=datetime.utcnow(),
                    )
                )

            # Analyze trends in the history
            if len(self.response_time_history) >= 10:
                recent_avg = sum(list(self.response_time_history)[-10:]) / 10
                historical_avg = (
                    sum(list(self.response_time_history)[:10]) / 10
                    if len(self.response_time_history) > 10
                    else recent_avg
                )

                if recent_avg > historical_avg * 1.2:  # 20% degradation
                    recommendations.append(
                        OptimizationRecommendation(
                            component="system",
                            recommendation="Response time is degrading over time. Investigate performance bottlenecks.",
                            expected_impact="medium",
                            confidence=0.7,
                            implementation_effort="medium",
                            timestamp=datetime.utcnow(),
                        )
                    )

            # Add to recommendations history
            if recommendations:
                await self._store_recommendations(recommendations)

            return recommendations
        except Exception as e:
            logger.error(f"Error analyzing performance trends: {e}")
            return []

    async def apply_optimization(
        self, optimization_name: str, parameters: dict[str, Any] | None = None
    ) -> PerformanceTuningResult:
        """
        Apply a specific performance optimization.

        Args:
            optimization_name: Name of the optimization to apply
            parameters: Additional parameters for the optimization

        Returns:
            PerformanceTuningResult with the outcome
        """
        try:
            optimization_id = f"opt_{int(datetime.utcnow().timestamp())}_{optimization_name[:8]}"

            # Get performance metrics before applying optimization
            before_metrics = await self.collect_performance_metrics()

            # Apply the optimization
            success = await self._execute_optimization(optimization_name, parameters)

            # Get performance metrics after applying optimization
            await asyncio.sleep(5)  # Wait for changes to take effect
            after_metrics = await self.collect_performance_metrics()

            # Calculate performance improvement
            improvement = self._calculate_performance_improvement(before_metrics, after_metrics)

            # Determine status based on success and improvement
            status = "success" if success else "failed"
            if success and improvement.get("overall_score", 0) < 0.1:  # Minimal improvement
                status = "partial"

            result = PerformanceTuningResult(
                optimization_id=optimization_id,
                timestamp=datetime.utcnow(),
                applied_optimizations=[optimization_name],
                performance_improvement=improvement,
                status=status,
                notes=f"Applied {optimization_name} optimization",
            )

            # Store optimization result
            await self._store_optimization_result(result)

            logger.info(
                f"Applied optimization {optimization_name}: {status}, improvement: {improvement.get('overall_score', 0):.2f}"
            )
            return result
        except Exception as e:
            logger.error(f"Error applying optimization {optimization_name}: {e}")
            return PerformanceTuningResult(
                optimization_id=f"opt_{int(datetime.utcnow().timestamp())}_failed",
                timestamp=datetime.utcnow(),
                applied_optimizations=[optimization_name],
                performance_improvement={},
                status="failed",
                notes=f"Error applying optimization: {e!s}",
            )

    async def _execute_optimization(
        self, optimization_name: str, parameters: dict[str, Any]
    ) -> bool:
        """Execute only registered real executors; recommendations stay advisory."""
        if optimization_name not in self.available_optimizations:
            logger.warning("Unknown optimization: %s", optimization_name)
            return False

        # This agent has no durable executor, approval workflow, or rollback
        # contract for these changes. Never report a simulated sleep as success.
        logger.warning(
            "Optimization %s is advisory-only; no mutation was applied", optimization_name
        )
        return False

    def _calculate_performance_improvement(
        self, before: PerformanceMetric, after: PerformanceMetric
    ) -> dict[str, float]:
        """Calculate performance improvement between two states."""
        try:
            improvement = {
                "cpu_usage_change": before.cpu_usage - after.cpu_usage,
                "memory_usage_change": before.memory_usage - after.memory_usage,
                "response_time_change_ms": before.response_time_ms - after.response_time_ms,
                "error_rate_change": before.error_rate - after.error_rate,
                "rps_change": after.requests_per_second - before.requests_per_second,
            }

            # Calculate overall score (higher is better)
            # Normalize each metric and combine
            cpu_score = (
                max(0, min(1, (before.cpu_usage - after.cpu_usage) / before.cpu_usage))
                if before.cpu_usage > 0
                else 0
            )
            memory_score = (
                max(0, min(1, (before.memory_usage - after.memory_usage) / before.memory_usage))
                if before.memory_usage > 0
                else 0
            )
            response_score = (
                max(
                    0,
                    min(
                        1,
                        (before.response_time_ms - after.response_time_ms)
                        / before.response_time_ms,
                    ),
                )
                if before.response_time_ms > 0
                else 0
            )
            error_score = (
                max(0, min(1, (before.error_rate - after.error_rate) / before.error_rate))
                if before.error_rate > 0
                else 0
            )

            overall_score = (cpu_score + memory_score + response_score + error_score) / 4
            improvement["overall_score"] = round(overall_score, 3)

            return improvement
        except Exception as e:
            logger.error(f"Error calculating performance improvement: {e}")
            return {"overall_score": 0.0}

    async def get_optimization_recommendations(
        self, limit: int = 10
    ) -> list[OptimizationRecommendation]:
        """Get recent optimization recommendations."""
        try:
            recommendations_data = await redis_manager.get(self.tuning_recommendations_key)
            if not recommendations_data:
                return []

            recommendations_list = json.loads(recommendations_data)
            recommendations = []

            for item in reversed(recommendations_list[-limit:]):  # Most recent first
                recommendations.append(
                    OptimizationRecommendation(
                        component=item["component"],
                        recommendation=item["recommendation"],
                        expected_impact=item["expected_impact"],
                        confidence=item["confidence"],
                        implementation_effort=item["implementation_effort"],
                        timestamp=datetime.fromisoformat(item["timestamp"]),
                    )
                )

            return recommendations
        except Exception as e:
            logger.error(f"Error retrieving optimization recommendations: {e}")
            return []

    async def _store_recommendations(self, recommendations: list[OptimizationRecommendation]):
        """Store optimization recommendations in Redis."""
        try:
            recommendations_data = []
            for rec in recommendations:
                recommendations_data.append(
                    {
                        "component": rec.component,
                        "recommendation": rec.recommendation,
                        "expected_impact": rec.expected_impact,
                        "confidence": rec.confidence,
                        "implementation_effort": rec.implementation_effort,
                        "timestamp": rec.timestamp.isoformat(),
                    }
                )

            # Get existing recommendations
            existing_recommendations = await redis_manager.get(self.tuning_recommendations_key)
            if existing_recommendations:
                rec_list = json.loads(existing_recommendations)
            else:
                rec_list = []

            # Add new recommendations
            rec_list.extend(recommendations_data)

            # Keep only the last N recommendations
            max_recommendations = 100
            if len(rec_list) > max_recommendations:
                rec_list = rec_list[-max_recommendations:]

            await redis_manager.set(
                self.tuning_recommendations_key,
                json.dumps(rec_list),
                ex=86400,  # 24 hours
            )
        except Exception as e:
            logger.error(f"Error storing recommendations: {e}")

    async def _store_optimization_result(self, result: PerformanceTuningResult):
        """Store optimization result in Redis."""
        try:
            result_data = {
                "optimization_id": result.optimization_id,
                "timestamp": result.timestamp.isoformat(),
                "applied_optimizations": result.applied_optimizations,
                "performance_improvement": result.performance_improvement,
                "status": result.status,
                "notes": result.notes,
            }

            # Get existing results
            existing_results = await redis_manager.get(self.optimization_history_key)
            if existing_results:
                results_list = json.loads(existing_results)
            else:
                results_list = []

            # Add new result
            results_list.append(result_data)

            # Keep only the last N results
            max_results = 100
            if len(results_list) > max_results:
                results_list = results_list[-max_results:]

            await redis_manager.set(
                self.optimization_history_key,
                json.dumps(results_list),
                ex=2592000,  # 30 days
            )
        except Exception as e:
            logger.error(f"Error storing optimization result: {e}")

    async def get_performance_summary(self, hours: int = 24) -> dict[str, Any]:
        """
        Get a summary of performance metrics over the specified time period.

        Args:
            hours: Number of hours to include in the summary

        Returns:
            Dictionary with performance summary
        """
        try:
            # Get metrics from Redis
            metrics_data = await redis_manager.get(self.performance_metrics_key)
            if not metrics_data:
                return {"status": "no_data", "message": "No performance metrics available"}

            all_metrics = json.loads(metrics_data)

            # Filter metrics for the specified time period
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            filtered_metrics = [
                m for m in all_metrics if datetime.fromisoformat(m["timestamp"]) >= cutoff_time
            ]

            if not filtered_metrics:
                return {
                    "status": "no_data",
                    "message": f"No metrics available for last {hours} hours",
                }

            # Calculate averages and statistics
            cpu_values = [m["cpu_usage"] for m in filtered_metrics]
            memory_values = [m["memory_usage"] for m in filtered_metrics]
            response_times = [m["response_time_ms"] for m in filtered_metrics]
            error_rates = [m["error_rate"] for m in filtered_metrics]

            summary = {
                "status": "success",
                "period_hours": hours,
                "metric_count": len(filtered_metrics),
                "averages": {
                    "cpu_usage": round(sum(cpu_values) / len(cpu_values), 2),
                    "memory_usage": round(sum(memory_values) / len(memory_values), 2),
                    "response_time_ms": round(sum(response_times) / len(response_times), 2),
                    "error_rate": round(sum(error_rates) / len(error_rates), 2),
                },
                "peak_values": {
                    "cpu_usage": max(cpu_values),
                    "memory_usage": max(memory_values),
                    "response_time_ms": max(response_times),
                    "error_rate": max(error_rates),
                },
                "trend": "stable",  # This would be calculated based on actual trends
                "recommendations_needed": len(await self.get_optimization_recommendations(limit=5)),
            }

            # Determine trend based on last vs first values
            if len(filtered_metrics) > 1:
                first_cpu = filtered_metrics[0]["cpu_usage"]
                last_cpu = filtered_metrics[-1]["cpu_usage"]

                if last_cpu > first_cpu * 1.2:  # 20% increase
                    summary["trend"] = "degrading"
                elif last_cpu < first_cpu * 0.8:  # 20% decrease
                    summary["trend"] = "improving"

            return summary
        except Exception as e:
            logger.error(f"Error getting performance summary: {e}")
            return {"status": "error", "message": str(e)}

    async def run_continuous_tuning(self, interval_minutes: int = 15):
        """
        Run continuous performance tuning at specified intervals.

        Args:
            interval_minutes: Interval between tuning checks in minutes
        """
        logger.info(
            f"Starting continuous performance tuning (interval: {interval_minutes} minutes)"
        )

        while True:
            try:
                # Collect current metrics
                await self.collect_performance_metrics()

                # Analyze for optimization opportunities
                recommendations = await self.analyze_performance_trends()

                # Apply high-priority optimizations automatically
                for rec in recommendations:
                    if rec.expected_impact == "high" and rec.confidence > 0.7:
                        await self.apply_optimization(
                            f"{rec.component}_optimization",
                            {"recommendation": rec.recommendation, "priority": rec.expected_impact},
                        )

                logger.info(
                    f"Completed performance tuning cycle. Found {len(recommendations)} recommendations."
                )

                # Sleep until next cycle
                await asyncio.sleep(interval_minutes * 60)

            except Exception as e:
                logger.error(f"Error in continuous tuning loop: {e}")
                await asyncio.sleep(interval_minutes * 60)  # Continue despite errors


# Global instance
performance_tuning_agent = PerformanceTuningAgent()
