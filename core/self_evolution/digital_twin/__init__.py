"""
SupremeAI Digital Twin - Main Integration Module
===============================================

Main entry point for the digital twin world model system.
Integrates topology mapping, impact simulation, and remediation capabilities.

Bengali:
ডিজিটাল টুইন মডেল - প্রধান একীকরণ মডিউল
টপোলজি ম্যাপিং, ইম্প্যাক্ট সিমুলেশন এবং রিমেডিয়েশন ক্ষমতা একীকরণ করে
"""

from core.contracts.security_policy import SEVERITY_LEVELS
from core.logging_config import logger

from .remediation_engine import (
    RemediationAction,
    RemediationEngine,
    RemediationExecution,
    RemediationPlan,
    RemediationStatus,
    get_remediation_engine,
)
from .simulator import (
    FailureScenario,
    ImpactSimulator,
    SimulationResult,
    SimulationType,
    TrafficScenario,
    get_impact_simulator,
)
from .topology import (
    DataFlowEdge,
    ResourceUtilization,
    ServiceNode,
    SystemTopologyMapper,
    discover_system_topology,
    get_topology_mapper,
)

# Version information
__version__ = "1.0.0"
__author__ = "SupremeAI Team"
__description__ = "Digital Twin World Model for SupremeAI 2.0"


class DigitalTwinWorldModel:
    """
    Main class that integrates all digital twin capabilities.

    Provides a unified interface to:
    - Map system topology
    - Simulate system changes and failures
    - Automatically remediate issues
    - Predict cascading effects
    """

    def __init__(self):
        self.topology_mapper = get_topology_mapper()
        self.impact_simulator = get_impact_simulator()
        self.remediation_engine = get_remediation_engine()

    async def initialize(self):
        """Initialize all digital twin components."""
        # Discover initial system topology
        topology = await discover_system_topology()
        logger.info(
            f"Initialized digital twin with {topology['summary']['total_services']} services"
        )

        return topology

    async def run_comprehensive_analysis(self, service_id: str):
        """
        Run a comprehensive analysis of a service including:
        - Current topology position
        - Dependency analysis
        - Impact simulation
        - Risk assessment
        """
        # Get current topology
        topology = await self.topology_mapper.get_topology_snapshot()

        # Get impact analysis
        impact_analysis = await self.topology_mapper.get_impact_analysis(service_id)

        # Run failure simulation
        failure_sim = await self.impact_simulator.simulate_service_failure(
            service_id, failure_type="complete", duration_minutes=10
        )

        # Run traffic simulation
        traffic_sim = await self.impact_simulator.simulate_traffic_spike(
            service_id, multiplier=2.5, duration_minutes=15
        )

        # Combine results
        analysis = {
            "service_id": service_id,
            "topology_position": self._find_service_position(topology, service_id),
            "impact_analysis": impact_analysis,
            "failure_simulation": failure_sim,
            "traffic_simulation": traffic_sim,
            "risk_assessment": self._assess_risk(failure_sim, traffic_sim),
            "recommendations": self._combine_recommendations(
                [
                    failure_sim.recommendations,
                    traffic_sim.recommendations,
                    impact_analysis.get("recommendations", []),
                ]
            ),
        }

        return analysis

    def _find_service_position(self, topology: dict, service_id: str) -> dict:
        """Find the position of a service in the topology."""
        service = next((s for s in topology["services"] if s["id"] == service_id), None)
        if not service:
            return {}

        # Find incoming and outgoing flows
        incoming_flows = [f for f in topology["data_flows"] if f["target_node_id"] == service_id]
        outgoing_flows = [f for f in topology["data_flows"] if f["source_node_id"] == service_id]

        return {
            "service_info": service,
            "incoming_dependencies": len(incoming_flows),
            "outgoing_dependencies": len(outgoing_flows),
            "connected_services": len(
                set(
                    [f["source_node_id"] for f in incoming_flows]
                    + [f["target_node_id"] for f in outgoing_flows]
                )
            ),
        }

    def _assess_risk(self, failure_sim: SimulationResult, traffic_sim: SimulationResult) -> str:
        """Assess overall risk based on simulations."""
        # Combine impact levels
        # Issue #684 (H-04): 1-based impact ranks derived from the canonical
        # severity ladder (core.contracts.security_policy.SEVERITY_LEVELS) —
        # identical values to the previous inline map, single-sourced now.
        impact_scores = {name: rank + 1 for name, rank in SEVERITY_LEVELS.items()}

        failure_score = impact_scores.get(failure_sim.predicted_impact, 1)
        traffic_score = impact_scores.get(traffic_sim.predicted_impact, 1)

        # Weight failure impact higher as it's more dangerous
        combined_score = (failure_score * 0.7) + (traffic_score * 0.3)

        if combined_score >= 3.0:
            return "critical"
        elif combined_score >= 2.0:
            return "high"
        elif combined_score >= 1.0:
            return "medium"
        else:
            return "low"

    def _combine_recommendations(self, recommendation_lists: list) -> list:
        """Combine and deduplicate recommendations from multiple sources."""
        all_recommendations = []
        seen = set()

        for rec_list in recommendation_lists:
            for rec in rec_list:
                if rec not in seen:
                    all_recommendations.append(rec)
                    seen.add(rec)

        return all_recommendations

    async def trigger_autonomous_remediation(self, service_id: str, issue_type: str = "auto"):
        """
        Trigger autonomous remediation for a service based on detected issue.

        Args:
            service_id: ID of the service needing remediation
            issue_type: Type of issue ('failure', 'overload', 'auto' for auto-detection)
        """
        if issue_type == "auto":
            # Run analysis to determine the best remediation approach
            analysis = await self.run_comprehensive_analysis(service_id)

            if analysis["risk_assessment"] in ["critical", "high"]:
                # Determine the most appropriate remediation plan
                plan = await self._create_adaptive_remediation_plan(service_id, analysis)
                execution_results = await self.remediation_engine._execute_remediation_plan(plan)
                return execution_results
            else:
                return None  # Low risk, no action needed
        else:
            # Manual remediation trigger
            if issue_type == "failure":
                action = RemediationAction.RESTART_SERVICE
            elif issue_type == "overload":
                action = RemediationAction.SCALE_UP
            else:
                action = RemediationAction.RESTART_SERVICE  # default

            result = await self.remediation_engine.manual_trigger_remediation(service_id, action)
            return [result]

    async def _create_adaptive_remediation_plan(self, service_id: str, analysis: dict):
        """Create an adaptive remediation plan based on analysis."""
        from .remediation_engine import RemediationAction, RemediationPlan

        issue_description = f"Adaptive remediation for {service_id} based on risk assessment: {analysis['risk_assessment']}"

        # Select actions based on risk level
        if analysis["risk_assessment"] == "critical":
            actions = [
                RemediationAction.ISOLATE_COMPONENT,
                RemediationAction.FAILOVER,
                RemediationAction.RESTART_SERVICE,
            ]
        elif analysis["risk_assessment"] == "high":
            actions = [RemediationAction.SCALE_UP, RemediationAction.RESTART_SERVICE]
        elif analysis["risk_assessment"] == "medium":
            actions = [RemediationAction.RESTART_SERVICE]
        else:
            actions = []  # No action for low risk

        plan = RemediationPlan(
            id=f"adaptive_{service_id}_{hash(str(analysis)) % 10000}",
            issue_detected_at=analysis["failure_simulation"].timestamp,
            issue_description=issue_description,
            affected_services=analysis["impact_analysis"]["downstream_services"],
            predicted_impact=analysis["risk_assessment"],
            recommended_actions=actions,
            confidence_score=analysis["failure_simulation"].confidence_score,
            estimated_recovery_time_minutes=analysis["failure_simulation"].duration * 2,
            rollback_possible=True,
            created_at=analysis["failure_simulation"].timestamp,
        )

        return plan

    async def get_system_digital_twin_state(self):
        """Get the complete digital twin state of the system."""
        topology = await self.topology_mapper.get_topology_snapshot()
        remediation_stats = self.remediation_engine.get_statistics()

        return {
            "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
            "topology": topology,
            "remediation_engine_status": remediation_stats,
            "simulator_status": {
                "recent_simulations": len(self.impact_simulator.simulation_history),
                "last_simulation": (
                    self.impact_simulator.simulation_history[-1].timestamp
                    if self.impact_simulator.simulation_history
                    else None
                ),
            },
            "health_summary": self._generate_health_summary(topology, remediation_stats),
        }

    def _generate_health_summary(self, topology: dict, remediation_stats: dict):
        """Generate a health summary from topology and remediation data."""
        services = topology["services"]
        utilizations = topology["resource_utilization"]

        total_services = len(services)
        healthy_services = len([s for s in services if s["status"] == "running"])
        error_services = len([s for s in services if s["status"] == "error"])

        high_cpu_services = len([u for u in utilizations if u["cpu_percent"] > 80])
        high_memory_services = len([u for u in utilizations if u["memory_percent"] > 80])

        return {
            "overall_health_percentage": (healthy_services / max(1, total_services)) * 100,
            "total_services": total_services,
            "healthy_services": healthy_services,
            "error_services": error_services,
            "warning_services": total_services - healthy_services - error_services,
            "high_cpu_services": high_cpu_services,
            "high_memory_services": high_memory_services,
            "remediation_success_rate": remediation_stats.get("success_rate", 0),
            "active_remediation_plans": remediation_stats.get("active_plans", 0),
        }


# Global instance for singleton pattern
_digital_twin_model: DigitalTwinWorldModel = None


def get_digital_twin_model() -> DigitalTwinWorldModel:
    """Get or create the singleton digital twin model instance."""
    global _digital_twin_model
    if _digital_twin_model is None:
        _digital_twin_model = DigitalTwinWorldModel()
    return _digital_twin_model


async def initialize_digital_twin():
    """Initialize the digital twin system."""
    model = get_digital_twin_model()
    await model.initialize()
    return model


# For backward compatibility
__all__ = [
    "DataFlowEdge",
    # Main integration
    "DigitalTwinWorldModel",
    "FailureScenario",
    # Simulation components
    "ImpactSimulator",
    "RemediationAction",
    # Remediation components
    "RemediationEngine",
    "RemediationExecution",
    "RemediationPlan",
    "RemediationStatus",
    "ResourceUtilization",
    "ServiceNode",
    "SimulationResult",
    "SimulationType",
    # Topology components
    "SystemTopologyMapper",
    "TrafficScenario",
    "discover_system_topology",
    "get_digital_twin_model",
    "get_impact_simulator",
    "get_remediation_engine",
    "get_topology_mapper",
    "initialize_digital_twin",
]


# Example usage
async def demo_digital_twin():
    """Demonstrate digital twin capabilities."""
    logger.debug("Initializing Digital Twin World Model...")

    model = await initialize_digital_twin()

    logger.debug("\nRunning comprehensive analysis on LLM Router...")
    analysis = await model.run_comprehensive_analysis("llm_router")
    logger.debug(f"Risk assessment: {analysis['risk_assessment']}")
    logger.debug(f"Recommendations: {len(analysis['recommendations'])}")

    logger.debug("\nGetting system digital twin state...")
    state = await model.get_system_digital_twin_state()
    logger.debug(f"Overall health: {state['health_summary']['overall_health_percentage']:.1f}%")
    logger.debug(f"Active remediation plans: {state['health_summary']['active_remediation_plans']}")

    return model


if __name__ == "__main__":
    import asyncio

    asyncio.run(demo_digital_twin())
