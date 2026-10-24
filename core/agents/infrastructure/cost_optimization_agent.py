"""
Cost Optimization Agent for SupremeAI 2.0
Manages advanced cost optimization and budget adherence across the system.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from core.cache.redis_manager import redis_manager
from core.llm.token_deductor import TokenDeductor
from core.logging_config import logger
from core.utils.background_tasks import track_task
from monitoring.metrics_collector import MetricsCollector


@dataclass
class CostMetric:
    """Data class to hold cost metric information."""

    timestamp: datetime
    compute_cost: float  # USD
    storage_cost: float  # USD
    network_cost: float  # USD
    ai_model_cost: float  # USD
    total_cost: float  # USD
    budget_utilization: float  # Percentage of budget used
    cost_per_user: float  # USD per user
    cost_per_request: float  # USD per request


@dataclass
class OptimizationOpportunity:
    """Data class to hold cost optimization opportunities."""

    id: str
    category: str  # compute, storage, network, ai_models, etc.
    description: str
    potential_savings: float  # USD
    implementation_effort: str  # low, medium, high
    confidence: float  # 0.0 to 1.0
    timeline: str  # immediate, short_term, medium_term
    timestamp: datetime


@dataclass
class BudgetAlert:
    """Data class to hold budget alert information."""

    alert_id: str
    budget_category: str
    current_usage: float
    budget_limit: float
    threshold_percentage: float
    severity: str  # info, warning, critical
    timestamp: datetime
    recommendations: list[str]


class CostOptimizationAgent:
    """Agent that manages advanced cost optimization and budget adherence."""

    def __init__(self):
        self.name = "Cost Optimization Agent"
        self.token_deductor = TokenDeductor()
        self.metrics_collector = MetricsCollector() if "MetricsCollector" in globals() else None
        self.cost_metrics_key = "cost_optimization:metrics"
        self.optimization_opportunities_key = "cost_optimization:opportunities"
        self.budget_alerts_key = "cost_optimization:alerts"
        self.budget_config_key = "cost_optimization:budget_config"
        self.cost_forecast_key = "cost_optimization:forecast"

        # Default cost optimization strategies
        self.optimization_strategies = {
            "compute": {
                "right_sizing": {
                    "description": "Right-size compute resources based on actual usage",
                    "potential_savings_range": (0.15, 0.30),  # 15-30% savings
                    "effort": "medium",
                    "timeline": "short_term",
                },
                "reserved_instances": {
                    "description": "Purchase reserved instances for predictable workloads",
                    "potential_savings_range": (0.20, 0.40),  # 20-40% savings
                    "effort": "medium",
                    "timeline": "medium_term",
                },
                "auto_scaling": {
                    "description": "Implement intelligent auto-scaling to reduce idle resources",
                    "potential_savings_range": (0.10, 0.25),  # 10-25% savings
                    "effort": "high",
                    "timeline": "short_term",
                },
            },
            "storage": {
                "tier_optimization": {
                    "description": "Move data to appropriate storage tiers based on access patterns",
                    "potential_savings_range": (0.20, 0.50),  # 20-50% savings
                    "effort": "medium",
                    "timeline": "short_term",
                },
                "cleanup_old_data": {
                    "description": "Remove old or unused data to reduce storage costs",
                    "potential_savings_range": (0.05, 0.15),  # 5-15% savings
                    "effort": "low",
                    "timeline": "immediate",
                },
                "compression": {
                    "description": "Implement data compression to reduce storage requirements",
                    "potential_savings_range": (0.10, 0.20),  # 10-20% savings
                    "effort": "medium",
                    "timeline": "short_term",
                },
            },
            "network": {
                "cdn_optimization": {
                    "description": "Optimize CDN usage and caching strategies",
                    "potential_savings_range": (0.10, 0.30),  # 10-30% savings
                    "effort": "medium",
                    "timeline": "short_term",
                },
                "data_transfer": {
                    "description": "Optimize data transfer patterns to reduce cross-region costs",
                    "potential_savings_range": (0.15, 0.25),  # 15-25% savings
                    "effort": "high",
                    "timeline": "medium_term",
                },
            },
            "ai_models": {
                "model_selection": {
                    "description": "Choose cost-effective models for appropriate tasks",
                    "potential_savings_range": (0.20, 0.40),  # 20-40% savings
                    "effort": "low",
                    "timeline": "immediate",
                },
                "batch_processing": {
                    "description": "Batch requests to optimize per-request costs",
                    "potential_savings_range": (0.10, 0.20),  # 10-20% savings
                    "effort": "medium",
                    "timeline": "short_term",
                },
                "caching": {
                    "description": "Cache AI model responses to reduce repeated computation",
                    "potential_savings_range": (0.25, 0.50),  # 25-50% savings
                    "effort": "medium",
                    "timeline": "short_term",
                },
            },
        }

        # Default budget configuration
        self.default_budget_config = {
            "monthly_compute_budget": 1000.0,  # USD
            "monthly_storage_budget": 500.0,  # USD
            "monthly_network_budget": 200.0,  # USD
            "monthly_ai_budget": 300.0,  # USD
            "total_monthly_budget": 2000.0,  # USD
            "warning_threshold": 80.0,  # Percentage
            "critical_threshold": 95.0,  # Percentage
            "budget_reset_day": 1,  # Day of month to reset budget tracking
        }

    async def initialize_budget_config(self):
        """Initialize budget configuration in Redis."""
        try:
            existing_config = await redis_manager.get(self.budget_config_key)
            if not existing_config:
                await redis_manager.set(
                    self.budget_config_key,
                    json.dumps(self.default_budget_config),
                    ex=2592000,  # 30 days
                )
                logger.info("Default budget configuration initialized")
        except Exception as e:
            logger.error(f"Error initializing budget config: {e}")

    async def track_cost_metrics(self) -> CostMetric:
        """Track current cost metrics for the system."""
        try:
            # In a real implementation, this would connect to cloud billing APIs
            # For simulation, we'll calculate based on usage metrics
            current_time = datetime.utcnow()

            # Get usage metrics (this would come from monitoring system)
            usage_metrics = await self._get_usage_metrics()

            # Calculate costs based on simulated pricing
            compute_cost = usage_metrics.get("cpu_hours", 0) * 0.05  # $0.05 per CPU hour
            storage_cost = usage_metrics.get("gb_months", 0) * 0.023  # $0.023 per GB-month
            network_cost = usage_metrics.get("gb_transferred", 0) * 0.10  # $0.10 per GB
            ai_model_cost = usage_metrics.get("api_calls", 0) * 0.001  # $0.001 per API call

            total_cost = compute_cost + storage_cost + network_cost + ai_model_cost

            # Get budget configuration
            budget_config = await self._get_budget_config()
            monthly_budget = budget_config.get("total_monthly_budget", 2000.0)
            budget_utilization = (total_cost / monthly_budget) * 100 if monthly_budget > 0 else 0

            # Calculate per-user and per-request costs
            active_users = usage_metrics.get("active_users", 1)
            total_requests = usage_metrics.get("total_requests", 1)

            cost_per_user = total_cost / active_users
            cost_per_request = total_cost / total_requests

            # Create cost metric
            cost_metric = CostMetric(
                timestamp=current_time,
                compute_cost=round(compute_cost, 2),
                storage_cost=round(storage_cost, 2),
                network_cost=round(network_cost, 2),
                ai_model_cost=round(ai_model_cost, 2),
                total_cost=round(total_cost, 2),
                budget_utilization=round(budget_utilization, 2),
                cost_per_user=round(cost_per_user, 4),
                cost_per_request=round(cost_per_request, 6),
            )

            # Store cost metric
            await self._store_cost_metric(cost_metric)

            # Check for budget alerts
            await self._check_budget_alerts(cost_metric, budget_config)

            return cost_metric
        except Exception as e:
            logger.error(f"Error tracking cost metrics: {e}")
            return CostMetric(
                timestamp=datetime.utcnow(),
                compute_cost=0.0,
                storage_cost=0.0,
                network_cost=0.0,
                ai_model_cost=0.0,
                total_cost=0.0,
                budget_utilization=0.0,
                cost_per_user=0.0,
                cost_per_request=0.0,
            )

    async def identify_optimization_opportunities(self) -> list[OptimizationOpportunity]:
        """Identify cost optimization opportunities."""
        try:
            opportunities = []
            current_time = datetime.utcnow()

            # Get current cost metrics
            recent_metrics = await self._get_recent_cost_metrics(10)
            if not recent_metrics:
                return []

            latest_metric = recent_metrics[0]  # Most recent

            # Analyze each cost category for optimization opportunities
            categories_to_analyze = [
                ("compute", latest_metric.compute_cost),
                ("storage", latest_metric.storage_cost),
                ("network", latest_metric.network_cost),
                ("ai_models", latest_metric.ai_model_cost),
            ]

            for category, cost in categories_to_analyze:
                if category in self.optimization_strategies:
                    strategies = self.optimization_strategies[category]

                    for strategy_name, strategy_info in strategies.items():
                        # Calculate potential savings based on current cost and strategy
                        min_savings, max_savings = strategy_info["potential_savings_range"]
                        potential_savings = cost * ((min_savings + max_savings) / 2)  # Average

                        if potential_savings > 0.01:  # Only include if savings > 1 cent
                            opportunity = OptimizationOpportunity(
                                id=f"opp_{strategy_name}_{int(current_time.timestamp())}",
                                category=category,
                                description=strategy_info["description"],
                                potential_savings=round(potential_savings, 2),
                                implementation_effort=strategy_info["effort"],
                                confidence=0.8,  # Default confidence
                                timeline=strategy_info["timeline"],
                                timestamp=current_time,
                            )

                            opportunities.append(opportunity)

            # Sort opportunities by potential savings (descending)
            opportunities.sort(key=lambda x: x.potential_savings, reverse=True)

            # Store opportunities
            await self._store_optimization_opportunities(opportunities)

            logger.info(f"Identified {len(opportunities)} cost optimization opportunities")
            return opportunities
        except Exception as e:
            logger.error(f"Error identifying optimization opportunities: {e}")
            return []

    async def generate_cost_forecast(self, days_ahead: int = 30) -> dict[str, Any]:
        """
        Generate cost forecast for the specified number of days.

        Args:
            days_ahead: Number of days to forecast ahead

        Returns:
            Dictionary with cost forecast information
        """
        try:
            # Get historical cost data
            historical_metrics = await self._get_recent_cost_metrics(30)  # Last 30 days

            if len(historical_metrics) < 7:
                return {
                    "status": "insufficient_data",
                    "message": "Not enough historical data for forecasting",
                    "forecast": {},
                    "confidence": 0.0,
                }

            # Calculate daily average costs
            daily_totals = [m.total_cost for m in historical_metrics]
            avg_daily_cost = sum(daily_totals) / len(daily_totals)

            # Simple linear projection (could be enhanced with more sophisticated models)
            forecasted_costs = []
            current_date = datetime.utcnow()

            for day_offset in range(1, days_ahead + 1):
                forecast_date = current_date + timedelta(days=day_offset)
                # Apply slight growth factor to account for usage increases
                growth_factor = 1 + (day_offset * 0.001)  # 0.1% growth per day
                forecasted_cost = avg_daily_cost * growth_factor
                forecasted_costs.append(
                    {"date": forecast_date.isoformat(), "predicted_cost": round(forecasted_cost, 2)}
                )

            # Calculate total forecast
            total_forecast = sum(fc["predicted_cost"] for fc in forecasted_costs)

            forecast_result = {
                "status": "success",
                "days_forecast": days_ahead,
                "average_daily_cost": round(avg_daily_cost, 2),
                "total_forecast": round(total_forecast, 2),
                "daily_forecast": forecasted_costs,
                "confidence": 0.7,  # Basic confidence for simple model
                "trend": (
                    "increasing"
                    if avg_daily_cost > daily_totals[-7 if len(daily_totals) >= 7 else 0]
                    else "stable"
                ),
            }

            # Store forecast in Redis
            await redis_manager.set(
                self.cost_forecast_key,
                json.dumps(forecast_result),
                ex=86400,  # 24 hours
            )

            return forecast_result
        except Exception as e:
            logger.error(f"Error generating cost forecast: {e}")
            return {"status": "error", "message": str(e), "forecast": {}, "confidence": 0.0}

    async def optimize_resource_allocation(self) -> dict[str, Any]:
        """Optimize resource allocation based on cost analysis."""
        try:
            # Identify the highest cost categories
            recent_metrics = await self._get_recent_cost_metrics(7)  # Last 7 days
            if not recent_metrics:
                return {"status": "no_data", "message": "No cost metrics available"}

            # Calculate average costs over the period
            avg_compute = sum(m.compute_cost for m in recent_metrics) / len(recent_metrics)
            avg_storage = sum(m.storage_cost for m in recent_metrics) / len(recent_metrics)
            avg_network = sum(m.network_cost for m in recent_metrics) / len(recent_metrics)
            avg_ai = sum(m.ai_model_cost for m in recent_metrics) / len(recent_metrics)

            recommendations = []

            # Compute optimization
            if avg_compute > 100:  # If compute costs are high
                recommendations.append(
                    {
                        "category": "compute",
                        "action": "consider_right_sizing",
                        "details": "Compute costs are high, consider right-sizing instances",
                        "potential_savings": round(avg_compute * 0.2, 2),  # 20% savings estimate
                    }
                )

            # Storage optimization
            if avg_storage > 50:  # If storage costs are high
                recommendations.append(
                    {
                        "category": "storage",
                        "action": "optimize_tiers",
                        "details": "Storage costs are high, consider optimizing storage tiers",
                        "potential_savings": round(avg_storage * 0.3, 2),  # 30% savings estimate
                    }
                )

            # AI model optimization
            if avg_ai > 50:  # If AI costs are high
                recommendations.append(
                    {
                        "category": "ai_models",
                        "action": "optimize_model_selection",
                        "details": "AI model costs are high, consider optimizing model selection",
                        "potential_savings": round(avg_ai * 0.25, 2),  # 25% savings estimate
                    }
                )

            # Network optimization
            if avg_network > 25:  # If network costs are high
                recommendations.append(
                    {
                        "category": "network",
                        "action": "optimize_cdn_usage",
                        "details": "Network costs are high, consider optimizing CDN usage",
                        "potential_savings": round(avg_network * 0.2, 2),  # 20% savings estimate
                    }
                )

            result = {
                "status": "success",
                "timestamp": datetime.utcnow().isoformat(),
                "recommendations": recommendations,
                "total_potential_savings": round(
                    sum(r["potential_savings"] for r in recommendations), 2
                ),
                "highest_cost_categories": sorted(
                    [
                        ("compute", avg_compute),
                        ("storage", avg_storage),
                        ("ai_models", avg_ai),
                        ("network", avg_network),
                    ],
                    key=lambda x: x[1],
                    reverse=True,
                )[:2],
            }

            return result
        except Exception as e:
            logger.error(f"Error optimizing resource allocation: {e}")
            return {"status": "error", "message": str(e), "recommendations": []}

    async def _get_usage_metrics(self) -> dict[str, float]:
        """Get current usage metrics (simulated for demo purposes)."""
        try:
            # In a real implementation, this would connect to monitoring systems
            # For now, return simulated values
            return {
                "cpu_hours": 1000.0,
                "gb_months": 500.0,
                "gb_transferred": 100.0,
                "api_calls": 50000.0,
                "active_users": 1000,
                "total_requests": 100000,
            }
        except Exception as e:
            logger.error(f"Error getting usage metrics: {e}")
            return {
                "cpu_hours": 100.0,
                "gb_months": 100.0,
                "gb_transferred": 10.0,
                "api_calls": 5000.0,
                "active_users": 100,
                "total_requests": 10000,
            }

    async def _store_cost_metric(self, metric: CostMetric):
        """Store cost metric in Redis."""
        try:
            metric_data = {
                "timestamp": metric.timestamp.isoformat(),
                "compute_cost": metric.compute_cost,
                "storage_cost": metric.storage_cost,
                "network_cost": metric.network_cost,
                "ai_model_cost": metric.ai_model_cost,
                "total_cost": metric.total_cost,
                "budget_utilization": metric.budget_utilization,
                "cost_per_user": metric.cost_per_user,
                "cost_per_request": metric.cost_per_request,
            }

            # Get existing metrics
            existing_metrics = await redis_manager.get(self.cost_metrics_key)
            if existing_metrics:
                metrics_list = json.loads(existing_metrics)
            else:
                metrics_list = []

            # Add new metric
            metrics_list.append(metric_data)

            # Keep only the last N metrics
            max_metrics = 1000
            if len(metrics_list) > max_metrics:
                metrics_list = metrics_list[-max_metrics:]

            await redis_manager.set(
                self.cost_metrics_key,
                json.dumps(metrics_list),
                ex=2592000,  # 30 days
            )
        except Exception as e:
            logger.error(f"Error storing cost metric: {e}")

    async def _store_optimization_opportunities(self, opportunities: list[OptimizationOpportunity]):
        """Store optimization opportunities in Redis."""
        try:
            opportunities_data = []
            for opp in opportunities:
                opportunities_data.append(
                    {
                        "id": opp.id,
                        "category": opp.category,
                        "description": opp.description,
                        "potential_savings": opp.potential_savings,
                        "implementation_effort": opp.implementation_effort,
                        "confidence": opp.confidence,
                        "timeline": opp.timeline,
                        "timestamp": opp.timestamp.isoformat(),
                    }
                )

            # Get existing opportunities
            existing_opportunities = await redis_manager.get(self.optimization_opportunities_key)
            if existing_opportunities:
                opp_list = json.loads(existing_opportunities)
            else:
                opp_list = []

            # Add new opportunities
            opp_list.extend(opportunities_data)

            # Keep only the last N opportunities
            max_opportunities = 100
            if len(opp_list) > max_opportunities:
                opp_list = opp_list[-max_opportunities:]

            await redis_manager.set(
                self.optimization_opportunities_key,
                json.dumps(opp_list),
                ex=86400,  # 24 hours
            )
        except Exception as e:
            logger.error(f"Error storing optimization opportunities: {e}")

    async def _check_budget_alerts(self, current_metric: CostMetric, budget_config: dict[str, Any]):
        """Check if current costs trigger any budget alerts."""
        try:
            alerts = []
            current_time = datetime.utcnow()

            # Check total budget utilization
            warning_threshold = budget_config.get("warning_threshold", 80.0)
            critical_threshold = budget_config.get("critical_threshold", 95.0)

            if current_metric.budget_utilization >= critical_threshold:
                alert = BudgetAlert(
                    alert_id=f"alert_critical_{int(current_time.timestamp())}",
                    budget_category="total",
                    current_usage=current_metric.total_cost,
                    budget_limit=budget_config.get("total_monthly_budget", 2000.0),
                    threshold_percentage=critical_threshold,
                    severity="critical",
                    timestamp=current_time,
                    recommendations=[
                        "Immediate cost reduction required",
                        "Review all non-essential services",
                        "Consider pausing non-critical operations",
                    ],
                )
                alerts.append(alert)
            elif current_metric.budget_utilization >= warning_threshold:
                alert = BudgetAlert(
                    alert_id=f"alert_warning_{int(current_time.timestamp())}",
                    budget_category="total",
                    current_usage=current_metric.total_cost,
                    budget_limit=budget_config.get("total_monthly_budget", 2000.0),
                    threshold_percentage=warning_threshold,
                    severity="warning",
                    timestamp=current_time,
                    recommendations=[
                        "Approaching budget limit",
                        "Review upcoming expenses",
                        "Consider optimization opportunities",
                    ],
                )
                alerts.append(alert)

            # Store alerts
            if alerts:
                await self._store_budget_alerts(alerts)
        except Exception as e:
            logger.error(f"Error checking budget alerts: {e}")

    async def _store_budget_alerts(self, alerts: list[BudgetAlert]):
        """Store budget alerts in Redis."""
        try:
            alerts_data = []
            for alert in alerts:
                alerts_data.append(
                    {
                        "alert_id": alert.alert_id,
                        "budget_category": alert.budget_category,
                        "current_usage": alert.current_usage,
                        "budget_limit": alert.budget_limit,
                        "threshold_percentage": alert.threshold_percentage,
                        "severity": alert.severity,
                        "timestamp": alert.timestamp.isoformat(),
                        "recommendations": alert.recommendations,
                    }
                )

            # Get existing alerts
            existing_alerts = await redis_manager.get(self.budget_alerts_key)
            if existing_alerts:
                alerts_list = json.loads(existing_alerts)
            else:
                alerts_list = []

            # Add new alerts
            alerts_list.extend(alerts_data)

            # Keep only recent alerts (last 7 days worth)
            cutoff_time = datetime.utcnow() - timedelta(days=7)
            recent_alerts = [
                alert
                for alert in alerts_list
                if datetime.fromisoformat(alert["timestamp"]) >= cutoff_time
            ]

            await redis_manager.set(
                self.budget_alerts_key,
                json.dumps(recent_alerts),
                ex=86400,  # 24 hours
            )
        except Exception as e:
            logger.error(f"Error storing budget alerts: {e}")

    async def _get_recent_cost_metrics(self, limit: int = 30) -> list[CostMetric]:
        """Get recent cost metrics from Redis."""
        try:
            metrics_data = await redis_manager.get(self.cost_metrics_key)
            if not metrics_data:
                return []

            all_metrics = json.loads(metrics_data)
            recent_metrics = []

            for item in reversed(all_metrics[-limit:]):  # Most recent first
                recent_metrics.append(
                    CostMetric(
                        timestamp=datetime.fromisoformat(item["timestamp"]),
                        compute_cost=item["compute_cost"],
                        storage_cost=item["storage_cost"],
                        network_cost=item["network_cost"],
                        ai_model_cost=item["ai_model_cost"],
                        total_cost=item["total_cost"],
                        budget_utilization=item["budget_utilization"],
                        cost_per_user=item["cost_per_user"],
                        cost_per_request=item["cost_per_request"],
                    )
                )

            return recent_metrics
        except Exception as e:
            logger.error(f"Error getting recent cost metrics: {e}")
            return []

    async def _get_budget_config(self) -> dict[str, Any]:
        """Get current budget configuration."""
        try:
            config_json = await redis_manager.get(self.budget_config_key)
            if config_json:
                return json.loads(config_json)
            else:
                return self.default_budget_config
        except Exception as e:
            logger.error(f"Error getting budget config: {e}")
            return self.default_budget_config

    async def get_cost_optimization_report(self) -> dict[str, Any]:
        """
        Generate a comprehensive cost optimization report.

        Returns:
            Dictionary with cost optimization report
        """
        try:
            # Get recent metrics
            recent_metrics = await self._get_recent_cost_metrics(30)
            if not recent_metrics:
                return {"status": "no_data", "message": "No cost metrics available"}

            # Get optimization opportunities
            opportunities = await self.identify_optimization_opportunities()

            # Get cost forecast
            forecast = await self.generate_cost_forecast()

            # Calculate key metrics
            total_spent = sum(m.total_cost for m in recent_metrics)
            avg_daily_cost = total_spent / len(recent_metrics)

            # Find highest cost category
            avg_compute = sum(m.compute_cost for m in recent_metrics) / len(recent_metrics)
            avg_storage = sum(m.storage_cost for m in recent_metrics) / len(recent_metrics)
            avg_network = sum(m.network_cost for m in recent_metrics) / len(recent_metrics)
            avg_ai = sum(m.ai_model_cost for m in recent_metrics) / len(recent_metrics)

            highest_cost_cat = max(
                [
                    ("Compute", avg_compute),
                    ("Storage", avg_storage),
                    ("Network", avg_network),
                    ("AI Models", avg_ai),
                ],
                key=lambda x: x[1],
            )

            report = {
                "status": "success",
                "report_generated_at": datetime.utcnow().isoformat(),
                "period_analyzed": f"Last {len(recent_metrics)} days",
                "key_metrics": {
                    "total_spent_usd": round(total_spent, 2),
                    "average_daily_cost_usd": round(avg_daily_cost, 2),
                    "highest_cost_category": highest_cost_cat[0],
                    "highest_cost_amount": round(highest_cost_cat[1], 2),
                },
                "optimization_opportunities": {
                    "count": len(opportunities),
                    # FIX: আগে `sum(min(3, len(opportunities)), key=...)` ছিল — সেটা int-কে
                    # iterable হিসেবে দেওয়ায় TypeError হত। সঠিক logic: top-3 opportunities
                    # (potential_savings অনুযায়ী descending sort) এর savings যোগ করা।
                    "top_3_potential_savings": round(
                        (
                            sum(
                                opp.potential_savings
                                for opp in sorted(
                                    opportunities,
                                    key=lambda x: x.potential_savings,
                                    reverse=True,
                                )[:3]
                            )
                            if opportunities
                            else 0
                        ),
                        2,
                    ),
                    "categories_covered": list(set(opp.category for opp in opportunities)),
                },
                "forecast": forecast,
                "recommendations": [
                    "Focus optimization efforts on highest cost category",
                    "Review and implement top optimization opportunities",
                    "Monitor budget utilization closely",
                    "Consider setting up automated cost alerts",
                ],
            }

            # Add top opportunities to report
            if opportunities:
                report["top_opportunities"] = [
                    {
                        "category": opp.category,
                        "description": opp.description,
                        "potential_savings": opp.potential_savings,
                        "timeline": opp.timeline,
                    }
                    for opp in sorted(
                        opportunities, key=lambda x: x.potential_savings, reverse=True
                    )[:5]
                ]

            return report
        except Exception as e:
            logger.error(f"Error generating cost optimization report: {e}")
            return {"status": "error", "message": str(e)}


# Global instance
cost_optimization_agent = CostOptimizationAgent()

# Initialize budget config on module load — শুধুমাত্র একটা event loop চলমান থাকলেই টাস্ক শিডিউল করা হয়;
# বাংলা: import-time-এ event loop না থাকলে RuntimeError এড়ানো হয়, আর টাস্কের রেফারেন্স ট্র্যাক করে
# রাখা হয় যাতে GC হয়ে মাঝপথে বাতিল না হয়ে যায় (RUF006)।
try:
    track_task(
        asyncio.get_running_loop().create_task(cost_optimization_agent.initialize_budget_config())
    )
except RuntimeError:
    logger.debug(
        "No running event loop at import time; skipping eager budget config init "
        "(call initialize_budget_config() explicitly during app startup instead)."
    )
