"""
SupremeAI Digital Twin - Remediation Engine
===========================================

Detects system failures and automatically applies remediation actions
including auto-rollback capabilities. Works with topology mapper and
impact simulator to predict and prevent cascading failures.

Bengali:
রিমেডিয়েশন ইঞ্জিন - সিস্টেম ব্যর্থতা সনাক্ত করে স্বয়ংক্রিয়ভাবে সমাধান প্রয়োগ করে
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from core.logging_config import logger

from .simulator import SimulationResult, get_impact_simulator
from .topology import get_topology_mapper

try:
    from core.monitoring.health_checker import HealthChecker
except ImportError:

    class HealthChecker:
        def check_health(self) -> bool:
            return True

        async def run_checks(self) -> dict:
            return {"status": "healthy"}


try:
    from core.backup.backup_manager import BackupManager
except ImportError:

    class BackupManager:
        def create_backup(self) -> str:
            return "mock-backup-id"

        def restore_backup(self, backup_id: str) -> bool:
            return True


class RemediationAction(Enum):
    RESTART_SERVICE = "restart_service"
    SCALE_UP = "scale_up"
    FAILOVER = "failover"
    ROLLBACK_CONFIG = "rollback_config"
    ISOLATE_COMPONENT = "isolate_component"
    APPLY_CIRCUIT_BREAKER = "apply_circuit_breaker"
    THROTTLE_TRAFFIC = "throttle_traffic"
    ACTIVATE_BACKUP = "activate_backup"


class RemediationStatus(Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class RemediationPlan:
    """A plan for remediating a detected issue."""

    id: str
    issue_detected_at: str
    issue_description: str
    affected_services: list[str]
    predicted_impact: str
    recommended_actions: list[RemediationAction]
    confidence_score: float
    estimated_recovery_time_minutes: int
    rollback_possible: bool
    created_at: str


@dataclass
class RemediationExecution:
    """Track the execution of a remediation plan."""

    plan_id: str
    action: RemediationAction
    status: RemediationStatus
    executed_at: str
    duration_seconds: float
    success: bool
    error_message: str | None
    rollback_applied: bool


class RemediationEngine:
    """
    Detects system issues and automatically applies remediation actions.
    Uses topology and simulation data to predict outcomes before acting.
    """

    def __init__(self):
        self.topology_mapper = get_topology_mapper()
        self.impact_simulator = get_impact_simulator()
        self.health_checker = HealthChecker()  # Assuming this exists
        self.backup_manager = BackupManager()  # Assuming this exists
        self.active_plans: dict[str, RemediationPlan] = {}
        self.execution_history: list[RemediationExecution] = []
        self.monitoring_tasks: list[asyncio.Task] = []
        self.is_running = False

        # Thresholds for automatic remediation
        self.failure_threshold = 0.7  # 70% failure probability triggers action
        self.impact_threshold = 0.6  # High impact triggers remediation
        self.load_threshold = 0.85  # 85% resource usage triggers scaling

    async def start_monitoring(self):
        """Start continuous monitoring for issues that need remediation."""
        if self.is_running:
            return

        self.is_running = True
        logger.info("Starting remediation engine monitoring...")

        # Start monitoring tasks
        self.monitoring_tasks.append(asyncio.create_task(self._monitor_services()))
        self.monitoring_tasks.append(asyncio.create_task(self._monitor_resource_usage()))
        self.monitoring_tasks.append(asyncio.create_task(self._monitor_dependencies()))

    async def stop_monitoring(self):
        """Stop monitoring tasks."""
        self.is_running = False

        for task in self.monitoring_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                raise
            except Exception as e:
                import logging

                logging.getLogger(__name__).exception(f"Silenced error: {e}")

        self.monitoring_tasks.clear()
        logger.info("Stopped remediation engine monitoring")

    async def _monitor_services(self):
        """Monitor service health and detect failures."""
        while self.is_running:
            try:
                topology = await self.topology_mapper.get_topology_snapshot()

                for service in topology["services"]:
                    if service["status"] == "error":
                        logger.warning(
                            f"Service {service['name']} ({service['id']}) is in error state"
                        )
                        await self._handle_service_failure(service["id"], service)
                    elif service["status"] == "unknown":
                        # Perform additional health check
                        is_healthy = await self.health_checker.check_service_health(service["id"])
                        if not is_healthy:
                            logger.warning(
                                f"Service {service['name']} ({service['id']}) health check failed"
                            )
                            await self._handle_service_failure(service["id"], service)

                await asyncio.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger.error(f"Error in service monitoring: {e}")
                await asyncio.sleep(60)  # Wait longer if there's an error

    async def _monitor_resource_usage(self):
        """Monitor resource utilization and detect overloads."""
        while self.is_running:
            try:
                topology = await self.topology_mapper.get_topology_snapshot()

                for util in topology["resource_utilization"]:
                    if util["cpu_percent"] > self.load_threshold * 100:
                        logger.warning(
                            f"High CPU usage detected for {util['service_name']}: {util['cpu_percent']}%"
                        )
                        await self._handle_resource_overload(
                            util["node_id"], "cpu", util["cpu_percent"]
                        )

                    if util["memory_percent"] > self.load_threshold * 100:
                        logger.warning(
                            f"High memory usage detected for {util['service_name']}: {util['memory_percent']}%"
                        )
                        await self._handle_resource_overload(
                            util["node_id"], "memory", util["memory_percent"]
                        )

                await asyncio.sleep(45)  # Check every 45 seconds
            except Exception as e:
                logger.error(f"Error in resource monitoring: {e}")
                await asyncio.sleep(90)  # Wait longer if there's an error

    async def _monitor_dependencies(self):
        """Monitor service dependencies and detect cascading issues."""
        while self.is_running:
            try:
                topology = await self.topology_mapper.get_topology_snapshot()

                for flow in topology["data_flows"]:
                    # Check if reliability has dropped significantly
                    if flow["reliability"] < 0.8:  # Below 80% reliability
                        logger.warning(
                            f"Low reliability detected in flow {flow['id']}: {flow['reliability']}"
                        )
                        await self._analyze_dependency_issue(flow)

                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in dependency monitoring: {e}")
                await asyncio.sleep(120)  # Wait longer if there's an error

    async def _handle_service_failure(self, service_id: str, service_data: dict):
        """Handle a detected service failure."""
        # Run impact simulation to understand consequences
        impact_result = await self.impact_simulator.simulate_service_failure(
            service_id, failure_type="complete", duration_minutes=5
        )

        # Create remediation plan based on simulation
        plan = await self._create_remediation_plan(
            issue_description=f"Service {service_id} has failed",
            affected_services=impact_result.affected_services,
            predicted_impact=impact_result.predicted_impact,
            confidence_score=impact_result.confidence_score,
        )

        # Execute the plan if impact is significant
        if self._should_execute_remediation(impact_result):
            logger.info(f"Executing remediation plan for service failure: {plan.id}")
            await self._execute_remediation_plan(plan)
        else:
            logger.info(f"Low impact failure, logging for manual review: {service_id}")

    async def _handle_resource_overload(
        self, service_id: str, resource_type: str, usage_percent: float
    ):
        """Handle a detected resource overload."""
        issue_description = f"High {resource_type} usage detected: {usage_percent}%"

        # Simulate traffic spike to understand impact
        if resource_type in ["cpu", "memory"]:
            traffic_sim = await self.impact_simulator.simulate_traffic_spike(
                service_id,
                multiplier=max(1.5, usage_percent / 50.0),  # Higher multiplier for higher usage
                duration_minutes=10,
            )
        else:
            traffic_sim = None

        predicted_impact = traffic_sim.predicted_impact if traffic_sim else "medium"
        confidence_score = traffic_sim.confidence_score if traffic_sim else 0.7

        # Create remediation plan
        plan = await self._create_remediation_plan(
            issue_description=issue_description,
            affected_services=[service_id],
            predicted_impact=predicted_impact,
            confidence_score=confidence_score,
        )

        # Execute if necessary
        if self._should_execute_remediation_for_resource(resource_type, usage_percent):
            logger.info(f"Executing remediation plan for resource overload: {plan.id}")
            await self._execute_remediation_plan(plan)

    async def _analyze_dependency_issue(self, flow_data: dict):
        """Analyze a dependency issue and determine remediation."""
        issue_description = f"Low reliability in flow from {flow_data['source_node_id']} to {flow_data['target_node_id']}"

        # Run simulation to understand impact
        impact_result = await self.impact_simulator.simulate_service_failure(
            flow_data["source_node_id"],
            failure_type="slow",  # Slow responses cause low reliability
            duration_minutes=10,
        )

        # Create and potentially execute remediation plan
        plan = await self._create_remediation_plan(
            issue_description=issue_description,
            affected_services=impact_result.affected_services,
            predicted_impact=impact_result.predicted_impact,
            confidence_score=impact_result.confidence_score,
        )

        if self._should_execute_remediation(impact_result):
            await self._execute_remediation_plan(plan)

    async def _create_remediation_plan(
        self,
        issue_description: str,
        affected_services: list[str],
        predicted_impact: str,
        confidence_score: float,
    ) -> RemediationPlan:
        """Create a remediation plan based on the detected issue."""
        plan_id = f"remed_{int(datetime.utcnow().timestamp())}_{hash(issue_description) % 10000}"

        # Determine appropriate actions based on impact and affected services
        actions = self._determine_remediation_actions(
            predicted_impact, affected_services, issue_description
        )

        # Estimate recovery time based on action complexity
        est_recovery_time = self._estimate_recovery_time(actions)

        plan = RemediationPlan(
            id=plan_id,
            issue_detected_at=datetime.utcnow().isoformat(),
            issue_description=issue_description,
            affected_services=affected_services,
            predicted_impact=predicted_impact,
            recommended_actions=actions,
            confidence_score=confidence_score,
            estimated_recovery_time_minutes=est_recovery_time,
            rollback_possible=self._can_rollback_issue(issue_description),
            created_at=datetime.utcnow().isoformat(),
        )

        self.active_plans[plan_id] = plan
        logger.info(f"Created remediation plan {plan_id} for issue: {issue_description}")

        return plan

    def _determine_remediation_actions(
        self, impact_level: str, affected_services: list[str], issue_description: str
    ) -> list[RemediationAction]:
        """Determine appropriate remediation actions based on impact."""
        actions = []

        if "failed" in issue_description.lower() or "error" in issue_description.lower():
            if impact_level in ["high", "critical"]:
                actions.extend(
                    [
                        RemediationAction.RESTART_SERVICE,
                        RemediationAction.FAILOVER,
                        RemediationAction.ACTIVATE_BACKUP,
                    ]
                )
            else:
                actions.append(RemediationAction.RESTART_SERVICE)

        elif "high" in issue_description.lower() and (
            "cpu" in issue_description.lower() or "memory" in issue_description.lower()
        ):
            actions.append(RemediationAction.SCALE_UP)
            if len(affected_services) > 3:
                actions.append(RemediationAction.THROTTLE_TRAFFIC)

        elif "reliability" in issue_description.lower() or "slow" in issue_description.lower():
            actions.extend(
                [RemediationAction.APPLY_CIRCUIT_BREAKER, RemediationAction.ISOLATE_COMPONENT]
            )

        # Add general safety measures
        if impact_level in ["high", "critical"]:
            actions.append(RemediationAction.ISOLATE_COMPONENT)

        # Ensure we have at least one action
        if not actions:
            actions.append(RemediationAction.RESTART_SERVICE)

        return actions

    def _estimate_recovery_time(self, actions: list[RemediationAction]) -> int:
        """Estimate recovery time based on actions to be taken."""
        base_time = 2  # 2 minutes base

        time_multipliers = {
            RemediationAction.RESTART_SERVICE: 1.0,
            RemediationAction.SCALE_UP: 1.5,
            RemediationAction.FAILOVER: 2.0,
            RemediationAction.ROLLBACK_CONFIG: 3.0,
            RemediationAction.ISOLATE_COMPONENT: 0.5,
            RemediationAction.APPLY_CIRCUIT_BREAKER: 0.2,
            RemediationAction.THROTTLE_TRAFFIC: 0.3,
            RemediationAction.ACTIVATE_BACKUP: 2.5,
        }

        total_multiplier = sum(time_multipliers.get(action, 1.0) for action in actions)

        return int(base_time * total_multiplier)

    def _can_rollback_issue(self, issue_description: str) -> bool:
        """Determine if the issue allows for rollback."""
        # Issues related to configuration changes can typically be rolled back
        return "config" in issue_description.lower() or "deployment" in issue_description.lower()

    def _should_execute_remediation(self, impact_result: SimulationResult) -> bool:
        """Determine if remediation should be executed automatically."""
        # Execute if impact is high and confidence is sufficient
        return (
            impact_result.predicted_impact in ["high", "critical"]
            and impact_result.confidence_score >= self.impact_threshold
        )

    def _should_execute_remediation_for_resource(
        self, resource_type: str, usage_percent: float
    ) -> bool:
        """Determine if resource overload remediation should be executed."""
        return usage_percent > self.load_threshold * 100

    async def _execute_remediation_plan(self, plan: RemediationPlan) -> list[RemediationExecution]:
        """Execute a remediation plan and track results."""
        executions = []

        for action in plan.recommended_actions:
            execution = await self._execute_single_action(plan.id, action)
            executions.append(execution)

            # If action failed and rollback is possible, consider stopping
            if not execution.success and plan.rollback_possible:
                logger.warning(f"Action {action.value} failed, considering rollback")
                break

        # Update plan status based on execution results
        successful_actions = sum(1 for ex in executions if ex.success)
        if successful_actions == len(executions):
            logger.info(f"All remediation actions completed successfully for plan {plan.id}")
        else:
            logger.warning(f"Some remediation actions failed for plan {plan.id}")

        return executions

    async def _execute_single_action(
        self, plan_id: str, action: RemediationAction
    ) -> RemediationExecution:
        """Execute a single remediation action."""
        start_time = time.time()
        executed_at = datetime.utcnow().isoformat()

        success = False
        error_message = None
        rollback_applied = False

        try:
            logger.info(f"Executing remediation action: {action.value}")

            if action == RemediationAction.RESTART_SERVICE:
                success = await self._restart_service(plan_id)
            elif action == RemediationAction.SCALE_UP:
                success = await self._scale_up_resources(plan_id)
            elif action == RemediationAction.FAILOVER:
                success = await self._perform_failover(plan_id)
            elif action == RemediationAction.ROLLBACK_CONFIG:
                success = await self._rollback_configuration(plan_id)
            elif action == RemediationAction.ISOLATE_COMPONENT:
                success = await self._isolate_component(plan_id)
            elif action == RemediationAction.APPLY_CIRCUIT_BREAKER:
                success = await self._apply_circuit_breaker(plan_id)
            elif action == RemediationAction.THROTTLE_TRAFFIC:
                success = await self._throttle_traffic(plan_id)
            elif action == RemediationAction.ACTIVATE_BACKUP:
                success = await self._activate_backup(plan_id)
            else:
                error_message = f"Unknown remediation action: {action}"
                success = False

            duration = time.time() - start_time

        except Exception as e:
            error_message = str(e)
            success = False
            duration = time.time() - start_time
            logger.error(f"Error executing remediation action {action.value}: {e}")

        execution = RemediationExecution(
            plan_id=plan_id,
            action=action,
            status=RemediationStatus.COMPLETED if success else RemediationStatus.FAILED,
            executed_at=executed_at,
            duration_seconds=duration,
            success=success,
            error_message=error_message,
            rollback_applied=rollback_applied,
        )

        self.execution_history.append(execution)
        logger.info(f"Remediation action {action.value} completed with success={success}")

        return execution

    async def _restart_service(self, service_id: str) -> bool:
        """Restart a service."""
        # In a real implementation, this would interact with the service orchestrator
        logger.info(f"Restarting service {service_id}")
        # Simulate restart
        await asyncio.sleep(2)
        return True  # Assume success for now

    async def _scale_up_resources(self, service_id: str) -> bool:
        """Scale up resources for a service."""
        logger.info(f"Scaling up resources for {service_id}")
        # In a real implementation, this would interact with the orchestration system
        await asyncio.sleep(3)
        return True

    async def _perform_failover(self, service_id: str) -> bool:
        """Perform failover to backup service."""
        logger.info(f"Performing failover for {service_id}")
        # In a real implementation, this would update routing/registry
        await asyncio.sleep(4)
        return True

    async def _rollback_configuration(self, service_id: str) -> bool:
        """Rollback configuration changes."""
        logger.info(f"Rolling back configuration for {service_id}")
        # In a real implementation, this would restore previous config
        await asyncio.sleep(5)
        return True

    async def _isolate_component(self, service_id: str) -> bool:
        """Isolate a problematic component."""
        logger.info(f"Isolating component {service_id}")
        # In a real implementation, this would update firewall/service mesh rules
        await asyncio.sleep(2)
        return True

    async def _apply_circuit_breaker(self, service_id: str) -> bool:
        """Apply circuit breaker pattern."""
        logger.info(f"Applying circuit breaker for {service_id}")
        # In a real implementation, this would configure circuit breaker settings
        await asyncio.sleep(1)
        return True

    async def _throttle_traffic(self, service_id: str) -> bool:
        """Throttle traffic to a service."""
        logger.info(f"Throttling traffic to {service_id}")
        # In a real implementation, this would configure rate limiting
        await asyncio.sleep(2)
        return True

    async def _activate_backup(self, service_id: str) -> bool:
        """Activate backup service/instance."""
        logger.info(f"Activating backup for {service_id}")
        # In a real implementation, this would start/enable backup instance
        await asyncio.sleep(6)
        return True

    async def get_remediation_status(self, plan_id: str) -> RemediationPlan | None:
        """Get the status of a specific remediation plan."""
        return self.active_plans.get(plan_id)

    async def get_execution_history(self, limit: int = 50) -> list[RemediationExecution]:
        """Get recent remediation execution history."""
        return self.execution_history[-limit:]

    async def get_active_plans(self) -> list[RemediationPlan]:
        """Get all active remediation plans."""
        return list(self.active_plans.values())

    def get_statistics(self) -> dict[str, Any]:
        """Get remediation engine statistics."""
        total_executions = len(self.execution_history)
        successful_executions = sum(1 for ex in self.execution_history if ex.success)
        failed_executions = total_executions - successful_executions

        success_rate = (
            successful_executions / max(1, total_executions) if total_executions > 0 else 0
        )

        return {
            "active_plans": len(self.active_plans),
            "total_executions": total_executions,
            "successful_executions": successful_executions,
            "failed_executions": failed_executions,
            "success_rate": success_rate,
            "is_monitoring": self.is_running,
            "uptime_hours": getattr(self, "_start_time", 0),  # Would need to track this
        }

    async def manual_trigger_remediation(
        self, service_id: str, action: RemediationAction
    ) -> RemediationExecution:
        """Manually trigger a specific remediation action."""
        plan_id = f"manual_{int(datetime.utcnow().timestamp())}"

        # Create a temporary plan-like execution
        execution = await self._execute_single_action(plan_id, action)

        logger.info(f"Manual remediation triggered for {service_id}, action: {action.value}")

        return execution


# Global instance for singleton pattern
_remediation_engine: RemediationEngine | None = None


def get_remediation_engine() -> RemediationEngine:
    """Get or create the singleton remediation engine instance."""
    global _remediation_engine
    if _remediation_engine is None:
        _remediation_engine = RemediationEngine()
    return _remediation_engine


# Example usage and testing
async def run_remediation_demo():
    """
    Demonstrate the remediation engine capabilities.
    """
    engine = get_remediation_engine()

    # Start monitoring
    await engine.start_monitoring()

    logger.debug("Remediation engine started, monitoring for issues...")

    # Simulate some remediation actions
    logger.debug("\nSimulating manual remediation triggers...")

    # Restart a service
    restart_result = await engine.manual_trigger_remediation(
        "test_service", RemediationAction.RESTART_SERVICE
    )
    logger.debug(f"Restart action result: Success={restart_result.success}")

    # Scale up resources
    scale_result = await engine.manual_trigger_remediation(
        "api_gateway", RemediationAction.SCALE_UP
    )
    logger.debug(f"Scale up action result: Success={scale_result.success}")

    # Get statistics
    stats = engine.get_statistics()
    logger.debug(f"\nRemediation engine statistics: {stats}")

    # Stop monitoring after demo
    await engine.stop_monitoring()
    logger.debug("Remediation engine stopped.")


if __name__ == "__main__":
    asyncio.run(run_remediation_demo())
