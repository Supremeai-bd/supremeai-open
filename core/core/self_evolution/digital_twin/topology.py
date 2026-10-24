"""
SupremeAI Digital Twin - System Topology Mapper
================================================

Maps the complete system topology including:
- Services and their dependencies
- Data flows between components
- Resource utilization patterns
- Network connectivity between microservices

Uses SQLite as lightweight alternative to Neo4j for zero-cost compliance.

Bengali:
সিস্টেম টপোলজি ম্যাপিং - ডিপেন্ডেন্সি, ডেটা ফ্লো, রিসোর্স ব্যবহার ও নেটওয়ার্ক কানেক্টিভিটি ট্র্যাক করে
"""

import asyncio
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from core.config import settings
from core.logging_config import logger


@dataclass
class ServiceNode:
    """Represents a service in the system topology."""

    id: str
    name: str
    type: str  # 'api', 'worker', 'database', 'cache', 'external'
    version: str
    status: str  # 'running', 'stopped', 'error', 'unknown'
    host: str
    port: int
    cpu_usage: float
    memory_usage: float
    created_at: str
    updated_at: str


@dataclass
class DataFlowEdge:
    """Represents a data flow relationship between services."""

    id: str
    source_node_id: str
    target_node_id: str
    flow_type: str  # 'request_response', 'pub_sub', 'streaming', 'batch'
    data_volume: float  # bytes per minute
    latency: float  # milliseconds
    reliability: float  # 0.0 to 1.0
    created_at: str
    updated_at: str


@dataclass
class ResourceUtilization:
    """Represents resource usage for a node."""

    node_id: str
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    network_io: float  # bytes per second
    timestamp: str


class SystemTopologyMapper:
    """
    Maps the complete system topology and relationships between components.

    Implements zero-cost principle by using SQLite instead of Neo4j.
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or settings.topology_db_path or ":memory:"
        self._init_db()

    def _init_db(self):
        """Initialize the topology database with required tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create services table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS services (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                version TEXT,
                status TEXT DEFAULT 'unknown',
                host TEXT,
                port INTEGER,
                cpu_usage REAL DEFAULT 0.0,
                memory_usage REAL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """
        )

        # Create data_flows table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS data_flows (
                id TEXT PRIMARY KEY,
                source_node_id TEXT NOT NULL,
                target_node_id TEXT NOT NULL,
                flow_type TEXT NOT NULL,
                data_volume REAL DEFAULT 0.0,
                latency REAL DEFAULT 0.0,
                reliability REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (source_node_id) REFERENCES services(id),
                FOREIGN KEY (target_node_id) REFERENCES services(id)
            )
        """
        )

        # Create resource_utilization table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS resource_utilization (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT NOT NULL,
                cpu_percent REAL,
                memory_percent REAL,
                disk_percent REAL,
                network_io REAL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (node_id) REFERENCES services(id)
            )
        """
        )

        conn.commit()
        conn.close()

    async def add_service(self, service: ServiceNode) -> bool:
        """Add a service to the topology."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO services
                (id, name, type, version, status, host, port, cpu_usage, memory_usage, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    service.id,
                    service.name,
                    service.type,
                    service.version,
                    service.status,
                    service.host,
                    service.port,
                    service.cpu_usage,
                    service.memory_usage,
                    service.created_at,
                    service.updated_at,
                ),
            )

            conn.commit()
            conn.close()

            logger.info(f"Added service to topology: {service.name} ({service.id})")
            return True
        except Exception as e:
            logger.error(f"Failed to add service to topology: {e}")
            return False

    async def add_data_flow(self, flow: DataFlowEdge) -> bool:
        """Add a data flow relationship to the topology."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO data_flows
                (id, source_node_id, target_node_id, flow_type, data_volume, latency, reliability, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    flow.id,
                    flow.source_node_id,
                    flow.target_node_id,
                    flow.flow_type,
                    flow.data_volume,
                    flow.latency,
                    flow.reliability,
                    flow.created_at,
                    flow.updated_at,
                ),
            )

            conn.commit()
            conn.close()

            logger.info(
                f"Added data flow to topology: {flow.source_node_id} -> {flow.target_node_id}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to add data flow to topology: {e}")
            return False

    async def record_resource_utilization(self, utilization: ResourceUtilization) -> bool:
        """Record resource utilization for a node."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO resource_utilization
                (node_id, cpu_percent, memory_percent, disk_percent, network_io, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    utilization.node_id,
                    utilization.cpu_percent,
                    utilization.memory_percent,
                    utilization.disk_percent,
                    utilization.network_io,
                    utilization.timestamp,
                ),
            )

            conn.commit()
            conn.close()

            logger.debug(f"Recorded resource utilization for node: {utilization.node_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to record resource utilization: {e}")
            return False

    async def get_topology_snapshot(self) -> dict:
        """Get a complete snapshot of the system topology."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get all services
        cursor.execute("SELECT * FROM services ORDER BY name")
        services_rows = cursor.fetchall()
        services_desc = [d[0] for d in cursor.description]
        services = []
        for row in services_rows:
            service_dict = dict(zip(services_desc, row, strict=False))
            services.append(service_dict)

        # Get all data flows
        cursor.execute("SELECT * FROM data_flows ORDER BY source_node_id, target_node_id")
        flows_rows = cursor.fetchall()
        flows_desc = [d[0] for d in cursor.description]
        flows = []
        for row in flows_rows:
            flow_dict = dict(zip(flows_desc, row, strict=False))
            flows.append(flow_dict)

        # Get latest resource utilization for each node
        cursor.execute(
            """
            SELECT ru.*, s.name as service_name
            FROM resource_utilization ru
            JOIN services s ON ru.node_id = s.id
            WHERE ru.timestamp = (
                SELECT MAX(timestamp)
                FROM resource_utilization ru2
                WHERE ru2.node_id = ru.node_id
            )
        """
        )
        utilization_rows = cursor.fetchall()
        utilization_desc = [d[0] for d in cursor.description]
        utilization = []
        for row in utilization_rows:
            util_dict = dict(zip(utilization_desc, row, strict=False))
            utilization.append(util_dict)

        conn.close()

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "services": services,
            "data_flows": flows,
            "resource_utilization": utilization,
            "summary": {
                "total_services": len(services),
                "total_flows": len(flows),
                "total_nodes_with_utilization": len(utilization),
            },
        }

    async def get_impact_analysis(self, service_id: str) -> dict:
        """
        Analyze the impact of a service failure on the system.

        Returns:
            Dictionary with affected services and potential impact level.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Find services that depend on the given service (incoming edges)
        cursor.execute(
            """
            SELECT DISTINCT s.*
            FROM services s
            JOIN data_flows df ON s.id = df.source_node_id
            WHERE df.target_node_id = ?
        """,
            (service_id,),
        )

        upstream_services = [
            dict(zip([d[0] for d in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]

        # Find services that this service depends on (outgoing edges)
        cursor.execute(
            """
            SELECT DISTINCT s.*
            FROM services s
            JOIN data_flows df ON s.id = df.target_node_id
            WHERE df.source_node_id = ?
        """,
            (service_id,),
        )

        downstream_services = [
            dict(zip([d[0] for d in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]

        # Calculate impact scores based on flow reliability and volume
        cursor.execute(
            """
            SELECT
                df.flow_type,
                AVG(df.reliability) as avg_reliability,
                SUM(df.data_volume) as total_volume
            FROM data_flows df
            WHERE df.source_node_id = ? OR df.target_node_id = ?
            GROUP BY df.flow_type
        """,
            (service_id, service_id),
        )

        impact_metrics = [
            dict(zip([d[0] for d in cursor.description], row, strict=False))
            for row in cursor.fetchall()
        ]

        conn.close()

        # Calculate overall impact score
        total_reliability = sum(
            m["avg_reliability"] for m in impact_metrics if m["avg_reliability"]
        )
        sum(m["total_volume"] for m in impact_metrics if m["total_volume"])

        # Impact levels: 0-30% = low, 31-70% = medium, 71-100% = high
        impact_score = min(100, ((2 - total_reliability) * 50) if total_reliability > 0 else 100)
        if impact_score > 70:
            impact_level = "high"
        elif impact_score > 30:
            impact_level = "medium"
        else:
            impact_level = "low"

        return {
            "service_id": service_id,
            "impact_level": impact_level,
            "impact_score": impact_score,
            "affected_upstream_services": len(upstream_services),
            "affected_downstream_services": len(downstream_services),
            "upstream_services": upstream_services,
            "downstream_services": downstream_services,
            "impact_metrics": impact_metrics,
            "recommendations": self._generate_impact_recommendations(
                impact_level, downstream_services
            ),
        }

    def _generate_impact_recommendations(
        self, impact_level: str, affected_services: list
    ) -> list[str]:
        """Generate recommendations based on impact level."""
        recommendations = []

        if impact_level == "high":
            recommendations.extend(
                [
                    "Implement immediate redundancy for critical services",
                    "Activate failover mechanisms",
                    "Alert system administrators",
                    "Consider graceful degradation of non-critical features",
                ]
            )
        elif impact_level == "medium":
            recommendations.extend(
                [
                    "Monitor affected services closely",
                    "Prepare contingency plans",
                    "Scale up resources if possible",
                    "Review dependency chains",
                ]
            )
        else:
            recommendations.extend(
                [
                    "Continue normal monitoring",
                    "Log the event for trend analysis",
                    "No immediate action required",
                ]
            )

        if len(affected_services) > 5:
            recommendations.append("Consider architectural refactoring to reduce coupling")

        return recommendations

    async def get_dependency_chain(self, service_id: str, depth: int = 3) -> dict:
        """Get the full dependency chain for a service up to specified depth."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Recursive query to find dependencies up to specified depth
        dependencies = []
        visited = set()

        def find_deps(current_id: str, current_depth: int, path: list[str]):
            if current_depth >= depth or current_id in visited:
                return

            visited.add(current_id)
            path.append(current_id)

            # Find services this one depends on (targets of flows from this service)
            cursor.execute(
                """
                SELECT DISTINCT df.target_node_id, s.name, s.status
                FROM data_flows df
                JOIN services s ON df.target_node_id = s.id
                WHERE df.source_node_id = ?
            """,
                (current_id,),
            )

            targets = cursor.fetchall()
            for target_id, target_name, target_status in targets:
                if target_id not in visited:
                    dependencies.append(
                        {
                            "source": current_id,
                            "target": target_id,
                            "target_name": target_name,
                            "target_status": target_status,
                            "depth": current_depth + 1,
                            "path": path.copy(),
                        }
                    )
                    find_deps(target_id, current_depth + 1, path.copy())

            path.pop()

        find_deps(service_id, 0, [])
        conn.close()

        return {
            "root_service_id": service_id,
            "depth_limit": depth,
            "dependency_chains": dependencies,
            "total_dependencies": len(dependencies),
        }


# Global instance for singleton pattern
_topology_mapper: SystemTopologyMapper | None = None


def get_topology_mapper(db_path: str | None = None) -> SystemTopologyMapper:
    """Get or create the singleton topology mapper instance."""
    global _topology_mapper
    if _topology_mapper is None:
        _topology_mapper = SystemTopologyMapper(db_path=db_path)
    return _topology_mapper


async def discover_system_topology() -> dict:
    """
    Discover the current system topology by scanning running services.

    This is a simplified version - in a real system, this would integrate
    with service discovery mechanisms, Kubernetes APIs, etc.
    """
    mapper = get_topology_mapper()

    # বাংলা মন্তব্য: সার্ভিসগুলোর হোস্ট ডায়নামিক করা — এনভায়রনমেন্ট ভেরিয়েবল থাকলে সেখান থেকে নেবে, নাহলে localhost ফলব্যাক ব্যবহার করবে।
    default_host = os.getenv("DEFAULT_SERVICE_HOST", "localhost")
    services = [
        ServiceNode(
            id="api_gateway",
            name="API Gateway",
            type="api",
            version="1.0.0",
            status="running",
            host=os.getenv("API_GATEWAY_HOST", default_host),
            port=int(os.getenv("BACKEND_PORT", "8000")),
            cpu_usage=15.5,
            memory_usage=25.3,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        ),
        ServiceNode(
            id="llm_router",
            name="LLM Router",
            type="api",
            version="1.0.0",
            status="running",
            host=os.getenv("LLM_ROUTER_HOST", default_host),
            port=int(os.getenv("DIGITAL_TWIN_PORT", "8001")),
            cpu_usage=22.1,
            memory_usage=30.7,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        ),
        ServiceNode(
            id="redis_cache",
            name="Redis Cache",
            type="cache",
            version="7.0.0",
            status="running",
            host=os.getenv("REDIS_HOST", default_host),
            port=6379,
            cpu_usage=8.2,
            memory_usage=45.1,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        ),
        ServiceNode(
            id="supabase_db",
            name="Supabase Database",
            type="database",
            version="14.0.0",
            status="running",
            host=os.getenv("DB_HOST", default_host),
            port=5432,
            cpu_usage=18.7,
            memory_usage=65.2,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        ),
        ServiceNode(
            id="qdrant_db",
            name="Qdrant Vector DB",
            type="database",
            version="1.0.0",
            status="running",
            host=os.getenv("QDRANT_HOST", default_host),
            port=6333,
            cpu_usage=12.4,
            memory_usage=38.9,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        ),
    ]

    # Add the services to topology
    for service in services:
        await mapper.add_service(service)

    # Add known data flows
    flows = [
        DataFlowEdge(
            id="api_to_llm",
            source_node_id="api_gateway",
            target_node_id="llm_router",
            flow_type="request_response",
            data_volume=1024.5,
            latency=120.0,
            reliability=0.98,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        ),
        DataFlowEdge(
            id="llm_to_cache",
            source_node_id="llm_router",
            target_node_id="redis_cache",
            flow_type="request_response",
            data_volume=512.0,
            latency=5.0,
            reliability=0.99,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        ),
        DataFlowEdge(
            id="llm_to_db",
            source_node_id="llm_router",
            target_node_id="supabase_db",
            flow_type="request_response",
            data_volume=2048.0,
            latency=80.0,
            reliability=0.97,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        ),
        DataFlowEdge(
            id="llm_to_vector_db",
            source_node_id="llm_router",
            target_node_id="qdrant_db",
            flow_type="request_response",
            data_volume=1024.0,
            latency=45.0,
            reliability=0.96,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        ),
    ]

    for flow in flows:
        await mapper.add_data_flow(flow)

    # Return the current topology snapshot
    return await mapper.get_topology_snapshot()


# For testing purposes
if __name__ == "__main__":

    async def test_mapper():
        topology = await discover_system_topology()
        logger.debug(f"Discovered topology with {topology['summary']['total_services']} services")

        # Test impact analysis
        impact = await get_topology_mapper().get_impact_analysis("llm_router")
        logger.debug(f"Impact analysis for llm_router: {impact['impact_level']} impact")

        # Test dependency chain
        deps = await get_topology_mapper().get_dependency_chain("api_gateway")
        logger.debug(
            f"Dependency chain for api_gateway: {deps['total_dependencies']} dependencies found"
        )

    # Run the test
    asyncio.run(test_mapper())
