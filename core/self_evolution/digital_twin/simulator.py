"""
SupremeAI Digital Twin - Impact Simulator
=========================================

Simulates the impact of system changes, failures, and interventions
before applying them to the real system. Uses the topology mapper to
understand dependencies and predict cascading effects.

Bengali:
ইম্প্যাক্ট সিমুলেটর - সিস্টেম পরিবর্তন, ব্যর্থতা ও হস্তক্ষেপের প্রভাব সিমুলেট করে
"""

import asyncio
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from core.logging_config import logger

from .topology import SystemTopologyMapper, get_topology_mapper


class SimulationType(Enum):
    SERVICE_FAILURE = "service_failure"
    TRAFFIC_SPIKE = "traffic_spike"
    NETWORK_LATENCY = "network_latency"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    SECURITY_INCIDENT = "security_incident"
    CONFIG_CHANGE = "config_change"


@dataclass
class SimulationResult:
    simulation_id: str
    simulation_type: SimulationType
    timestamp: str
    duration: float  # seconds
    affected_services: list[str]
    predicted_impact: str  # low, medium, high, critical
    probability_of_occurrence: float  # 0.0 to 1.0
    confidence_score: float  # 0.0 to 1.0
    recommendations: list[str]
    cascade_effects: list[dict]  # List of cascading effect predictions


@dataclass
class FailureScenario:
    service_id: str
    failure_type: str  # 'complete', 'partial', 'intermittent', 'slow'
    duration_minutes: int
    probability: float  # 0.0 to 1.0
    recovery_time_minutes: int


@dataclass
class TrafficScenario:
    service_id: str
    multiplier: float  # traffic multiplier (e.g., 2.0 for 2x traffic)
    duration_minutes: int
    start_time: datetime


class ImpactSimulator:
    """
    Simulates various system scenarios to predict impact before applying changes.
    """

    def __init__(self, topology_mapper: SystemTopologyMapper):
        self.topology_mapper = topology_mapper
        self.simulation_history: list[SimulationResult] = []

    async def simulate_service_failure(
        self, service_id: str, failure_type: str = "complete", duration_minutes: int = 5
    ) -> SimulationResult:
        """
        Simulate a service failure and predict its impact.
        """
        start_time = datetime.utcnow()
        logger.info(f"Starting service failure simulation for {service_id}, type: {failure_type}")

        # Get current topology
        topology = await self.topology_mapper.get_topology_snapshot()

        # Find the service being simulated
        target_service = next((s for s in topology["services"] if s["id"] == service_id), None)
        if not target_service:
            raise ValueError(f"Service {service_id} not found in topology")

        # Analyze impact of this failure
        impact_analysis = await self.topology_mapper.get_impact_analysis(service_id)

        # Simulate cascade effects
        cascade_effects = await self._simulate_cascade_effects(
            service_id, failure_type, duration_minutes, topology
        )

        # Determine predicted impact level
        impact_level = self._calculate_impact_level(impact_analysis, cascade_effects)

        # Generate recommendations
        recommendations = self._generate_failure_recommendations(
            service_id, failure_type, impact_analysis
        )

        # Calculate probability based on historical patterns and service criticality
        probability = self._calculate_failure_probability(target_service, failure_type)

        # Calculate confidence score based on data availability
        confidence_score = self._calculate_confidence_score(topology, impact_analysis)

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        result = SimulationResult(
            simulation_id=f"sim_{int(start_time.timestamp())}_{random.randint(1000, 9999)}",
            simulation_type=SimulationType.SERVICE_FAILURE,
            timestamp=start_time.isoformat(),
            duration=duration,
            affected_services=[s["id"] for s in impact_analysis.get("downstream_services", [])],
            predicted_impact=impact_level,
            probability_of_occurrence=probability,
            confidence_score=confidence_score,
            recommendations=recommendations,
            cascade_effects=cascade_effects,
        )

        self.simulation_history.append(result)
        logger.info(f"Service failure simulation completed. Impact: {impact_level}")

        return result

    async def simulate_traffic_spike(
        self, service_id: str, multiplier: float = 2.0, duration_minutes: int = 10
    ) -> SimulationResult:
        """
        Simulate a traffic spike and predict its impact.
        """
        start_time = datetime.utcnow()
        logger.info(f"Starting traffic spike simulation for {service_id}, multiplier: {multiplier}")

        # Get current topology
        topology = await self.topology_mapper.get_topology_snapshot()

        # Find the service being simulated
        target_service = next((s for s in topology["services"] if s["id"] == service_id), None)
        if not target_service:
            raise ValueError(f"Service {service_id} not found in topology")

        # Simulate the traffic increase
        # This affects CPU and memory usage, potentially causing cascading effects
        increased_load = {
            "cpu_usage": min(100.0, target_service["cpu_usage"] * multiplier),
            "memory_usage": min(
                100.0, target_service["memory_usage"] * (multiplier * 0.8)
            ),  # Memory grows slower
            "latency_increase_factor": multiplier * 0.5,  # Latency increases with traffic
        }

        # Analyze impact with increased load
        impact_analysis = await self.topology_mapper.get_impact_analysis(service_id)

        # Simulate cascade effects due to increased load
        cascade_effects = await self._simulate_load_cascade_effects(
            service_id, increased_load, duration_minutes, topology
        )

        # Determine predicted impact level
        impact_level = self._calculate_impact_level(impact_analysis, cascade_effects)

        # Generate recommendations
        recommendations = self._generate_traffic_recommendations(
            service_id, multiplier, impact_analysis
        )

        # Calculate probability based on traffic patterns
        probability = min(
            0.95, multiplier * 0.1
        )  # Higher multiplier = higher probability of issues

        # Calculate confidence score
        confidence_score = self._calculate_confidence_score(topology, impact_analysis)

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        result = SimulationResult(
            simulation_id=f"sim_{int(start_time.timestamp())}_{random.randint(1000, 9999)}",
            simulation_type=SimulationType.TRAFFIC_SPIKE,
            timestamp=start_time.isoformat(),
            duration=duration,
            affected_services=[s["id"] for s in impact_analysis.get("downstream_services", [])],
            predicted_impact=impact_level,
            probability_of_occurrence=probability,
            confidence_score=confidence_score,
            recommendations=recommendations,
            cascade_effects=cascade_effects,
        )

        self.simulation_history.append(result)
        logger.info(f"Traffic spike simulation completed. Impact: {impact_level}")

        return result

    async def _simulate_cascade_effects(
        self, failed_service_id: str, failure_type: str, duration_minutes: int, topology: dict
    ) -> list[dict]:
        """
        Simulate how a failure propagates through the system.
        """
        cascade_effects = []

        # Get dependency chain
        deps = await self.topology_mapper.get_dependency_chain(failed_service_id, depth=5)

        for dep in deps["dependency_chains"]:
            # Calculate probability of cascade based on reliability and failure type
            base_reliability = 0.95  # Default reliability
            failure_severity_multiplier = {
                "complete": 1.0,
                "partial": 0.6,
                "intermittent": 0.4,
                "slow": 0.3,
            }.get(failure_type, 0.5)

            # Find the flow to determine actual reliability
            flow = next(
                (
                    f
                    for f in topology["data_flows"]
                    if f["source_node_id"] == dep["source"] and f["target_node_id"] == dep["target"]
                ),
                None,
            )

            if flow:
                actual_reliability = flow["reliability"]
            else:
                actual_reliability = base_reliability

            # Probability of cascade = (1 - reliability) * severity_multiplier
            cascade_probability = (1 - actual_reliability) * failure_severity_multiplier

            if random.random() < cascade_probability:
                # Cascade effect occurs
                effect_severity = (
                    "high"
                    if cascade_probability > 0.7
                    else "medium"
                    if cascade_probability > 0.3
                    else "low"
                )

                cascade_effects.append(
                    {
                        "source_service": dep["source"],
                        "target_service": dep["target"],
                        "effect_type": "dependency_failure",
                        "severity": effect_severity,
                        "probability": cascade_probability,
                        "estimated_delay_minutes": random.randint(1, duration_minutes),
                        "additional_impact": f"{dep['target_name']} may experience degraded performance",
                    }
                )

        return cascade_effects

    async def _simulate_load_cascade_effects(
        self, service_id: str, increased_load: dict, duration_minutes: int, topology: dict
    ) -> list[dict]:
        """
        Simulate how increased load propagates through the system.
        """
        cascade_effects = []

        # Get services that depend on this one (they'll be affected by slower responses)
        deps = await self.topology_mapper.get_dependency_chain(service_id, depth=3)

        for dep in deps["dependency_chains"]:
            # Calculate load impact based on flow characteristics
            flow = next(
                (
                    f
                    for f in topology["data_flows"]
                    if f["source_node_id"] == dep["source"] and f["target_node_id"] == dep["target"]
                ),
                None,
            )

            if flow:
                # Higher latency and lower reliability mean higher chance of cascade
                load_impact_factor = (1 - flow["reliability"]) * (
                    increased_load["latency_increase_factor"]
                )

                if load_impact_factor > 0.3:  # Threshold for significant impact
                    effect_severity = "high" if load_impact_factor > 0.7 else "medium"

                    cascade_effects.append(
                        {
                            "source_service": dep["source"],
                            "target_service": dep["target"],
                            "effect_type": "performance_degradation",
                            "severity": effect_severity,
                            "estimated_delay_minutes": int(
                                duration_minutes * increased_load["latency_increase_factor"]
                            ),
                            "additional_impact": f"{dep['target_name']} response times may increase significantly",
                        }
                    )

        return cascade_effects

    def _calculate_impact_level(self, impact_analysis: dict, cascade_effects: list[dict]) -> str:
        """
        Calculate the overall impact level based on analysis and cascade effects.
        """
        # Base impact from topology analysis
        base_level = impact_analysis.get("impact_level", "low")

        # Factor in cascade effects
        cascade_severity_score = sum(
            {"high": 3, "medium": 2, "low": 1}.get(effect["severity"], 1)
            for effect in cascade_effects
        )

        # Convert to impact level
        if cascade_severity_score >= 6:
            return "critical"
        elif cascade_severity_score >= 4:
            return "high"
        elif cascade_severity_score >= 2:
            return "medium"
        else:
            return base_level

    def _generate_failure_recommendations(
        self, service_id: str, failure_type: str, impact_analysis: dict
    ) -> list[str]:
        """
        Generate recommendations based on failure simulation.
        """
        recommendations = []

        impact_level = impact_analysis.get("impact_level", "low")

        if impact_level == "critical":
            recommendations.extend(
                [
                    f"IMMEDIATE ACTION REQUIRED: {service_id} failure will cause system-wide outage",
                    "Activate emergency failover procedures",
                    "Notify all stakeholders immediately",
                    "Prepare for service degradation in dependent systems",
                ]
            )
        elif impact_level == "high":
            recommendations.extend(
                [
                    f"High impact predicted for {service_id} failure",
                    "Ensure backup systems are ready",
                    "Monitor dependent services closely",
                    "Prepare mitigation strategies",
                ]
            )
        elif impact_level == "medium":
            recommendations.extend(
                [
                    f"Medium impact predicted for {service_id} failure",
                    "Increase monitoring for affected services",
                    "Have rollback procedures ready",
                    "Inform relevant teams",
                ]
            )
        else:
            recommendations.extend(
                [
                    f"Low impact predicted for {service_id} failure",
                    "Standard monitoring procedures sufficient",
                    "Document the event for trend analysis",
                ]
            )

        # Add failure-type specific recommendations
        if failure_type == "complete":
            recommendations.append("Verify service can be restarted cleanly")
        elif failure_type == "slow":
            recommendations.append("Check for resource constraints or bottlenecks")
        elif failure_type == "intermittent":
            recommendations.append("Investigate network or timing issues")

        # Add dependency-specific recommendations
        downstream_count = len(impact_analysis.get("downstream_services", []))
        if downstream_count > 5:
            recommendations.append("Consider architectural changes to reduce coupling")

        return recommendations

    def _generate_traffic_recommendations(
        self, service_id: str, multiplier: float, impact_analysis: dict
    ) -> list[str]:
        """
        Generate recommendations based on traffic spike simulation.
        """
        recommendations = []

        impact_level = impact_analysis.get("impact_level", "low")

        if multiplier > 5.0:
            recommendations.append(
                "EXTREME TRAFFIC SPIKE DETECTED - Auto-scaling likely insufficient"
            )
        elif multiplier > 3.0:
            recommendations.append("HIGH TRAFFIC SPIKE - Verify auto-scaling configuration")
        elif multiplier > 2.0:
            recommendations.append("MODERATE TRAFFIC SPIKE - Monitor resource utilization closely")

        if impact_level in ["critical", "high"]:
            recommendations.extend(
                [
                    f"Traffic spike to {service_id} will likely cause service degradation",
                    "Consider implementing rate limiting or load shedding",
                    "Ensure circuit breakers are properly configured",
                    "Prepare additional capacity if possible",
                ]
            )
        else:
            recommendations.extend(
                [
                    f"Traffic spike to {service_id} appears manageable",
                    "Monitor performance metrics during peak",
                    "Consider pre-scaling if spike is predictable",
                ]
            )

        return recommendations

    def _calculate_failure_probability(self, service: dict, failure_type: str) -> float:
        """
        Calculate the probability of this specific failure occurring.
        """
        # Base probability
        base_prob = 0.05  # 5% base failure rate

        # Adjust based on current status and resource usage
        if service["status"] != "running":
            return 1.0  # Already failing

        # Higher resource usage = higher failure probability
        resource_stress = (service["cpu_usage"] + service["memory_usage"]) / 200.0
        stress_factor = min(1.0, resource_stress * 2)  # Cap at 2x

        # Different failure types have different probabilities
        type_multiplier = {"complete": 1.0, "partial": 1.5, "intermittent": 2.0, "slow": 1.2}.get(
            failure_type, 1.0
        )

        return min(0.95, base_prob * stress_factor * type_multiplier)

    def _calculate_confidence_score(self, topology: dict, impact_analysis: dict) -> float:
        """
        Calculate confidence in the simulation results.
        """
        # Confidence based on data completeness
        total_services = topology["summary"]["total_services"]
        services_with_util = topology["summary"]["total_nodes_with_utilization"]

        data_completeness = services_with_util / max(1, total_services)

        # Confidence based on dependency chain completeness
        len(impact_analysis.get("downstream_services", []))

        # Base confidence adjusted by data availability
        base_confidence = 0.7
        confidence = base_confidence * (0.5 + 0.5 * data_completeness)

        return min(0.95, confidence)  # Cap at 95% for safety

    async def run_scenario_simulation(self, scenario: FailureScenario) -> SimulationResult:
        """
        Run a predefined failure scenario.
        """
        return await self.simulate_service_failure(
            scenario.service_id, scenario.failure_type, scenario.duration_minutes
        )

    async def run_multiple_simulations(
        self, service_id: str, simulations: list[tuple[SimulationType, dict]]
    ) -> list[SimulationResult]:
        """
        Run multiple simulations for the same service and compare results.
        """
        results = []

        for sim_type, params in simulations:
            if sim_type == SimulationType.SERVICE_FAILURE:
                result = await self.simulate_service_failure(service_id, **params)
            elif sim_type == SimulationType.TRAFFIC_SPIKE:
                result = await self.simulate_traffic_spike(service_id, **params)
            else:
                continue  # Skip unsupported simulation types

            results.append(result)

        return results

    def get_simulation_report(self, days_back: int = 7) -> dict:
        """
        Generate a report of recent simulations.
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)

        recent_sims = [
            sim
            for sim in self.simulation_history
            if datetime.fromisoformat(sim.timestamp.replace("Z", "+00:00")) >= cutoff_date
        ]

        # Aggregate statistics
        stats = {
            "total_simulations": len(recent_sims),
            "by_type": {},
            "by_impact": {},
            "average_confidence": 0.0,
            "high_impact_count": 0,
        }

        for sim in recent_sims:
            # Count by type
            sim_type = sim.simulation_type.value
            stats["by_type"][sim_type] = stats["by_type"].get(sim_type, 0) + 1

            # Count by impact
            impact = sim.predicted_impact
            stats["by_impact"][impact] = stats["by_impact"].get(impact, 0) + 1

            # Track high impact
            if impact in ["high", "critical"]:
                stats["high_impact_count"] += 1

        if recent_sims:
            stats["average_confidence"] = sum(s.confidence_score for s in recent_sims) / len(
                recent_sims
            )

        return {
            "report_period_days": days_back,
            "generated_at": datetime.utcnow().isoformat(),
            "statistics": stats,
            "recent_simulations": recent_sims[-10:],  # Last 10 simulations
        }


# Global instance for singleton pattern
_impact_simulator: ImpactSimulator | None = None


def get_impact_simulator() -> ImpactSimulator:
    """Get or create the singleton impact simulator instance."""
    global _impact_simulator
    if _impact_simulator is None:
        topology_mapper = get_topology_mapper()
        _impact_simulator = ImpactSimulator(topology_mapper)
    return _impact_simulator


# Example usage and testing
async def run_sample_simulations():
    """
    Run sample simulations to demonstrate the impact simulator.
    """
    simulator = get_impact_simulator()

    logger.debug("Running sample service failure simulation...")
    failure_result = await simulator.simulate_service_failure(
        "llm_router", failure_type="complete", duration_minutes=10
    )
    logger.debug(f"Failure simulation result: {failure_result.predicted_impact} impact")
    logger.debug(f"Affected services: {len(failure_result.affected_services)}")
    logger.debug(f"Recommendations: {len(failure_result.recommendations)}")

    logger.debug("\nRunning sample traffic spike simulation...")
    traffic_result = await simulator.simulate_traffic_spike(
        "api_gateway", multiplier=3.0, duration_minutes=15
    )
    logger.debug(f"Traffic simulation result: {traffic_result.predicted_impact} impact")
    logger.debug(f"Cascade effects: {len(traffic_result.cascade_effects)}")

    # Generate a report
    report = simulator.get_simulation_report(days_back=7)
    logger.debug("\nSimulation report for last 7 days:")
    logger.debug(f"Total simulations: {report['statistics']['total_simulations']}")
    logger.debug(f"High/critical impacts: {report['statistics']['high_impact_count']}")

    return failure_result, traffic_result


# Aliases for SupremeBrowser and Cognitive Swarm
DigitalTwinSimulator = ImpactSimulator
get_digital_twin_simulator = get_impact_simulator


if __name__ == "__main__":
    asyncio.run(run_sample_simulations())
