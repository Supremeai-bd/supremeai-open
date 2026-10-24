from sqlalchemy import Boolean, Column, DateTime, Integer, Text
from sqlalchemy.sql import func

from models.base import Base
from utils.uuid_gen import UUIDv7, generate_uuid7


class SystemDependency(Base):
    """
    Tracking for system dependencies and vulnerability status.
    """

    __tablename__ = "system_dependencies"

    id = Column(UUIDv7, primary_key=True, default=generate_uuid7)
    package_name = Column(Text, nullable=False)
    current_version = Column(Text, nullable=False)
    latest_version = Column(Text)
    status = Column(Text, default="healthy")  # healthy, vulnerable, deprecated
    last_audit_at = Column(DateTime(timezone=True), default=func.now())


class ApiEndpoint(Base):
    """
    API endpoint health monitor heartbeat.
    """

    __tablename__ = "api_endpoints"

    id = Column(UUIDv7, primary_key=True, default=generate_uuid7)
    path = Column(Text, nullable=False)
    method = Column(Text, nullable=False)
    expected_status = Column(Integer, default=200)
    is_critical = Column(Boolean, default=True)
    last_ping_status = Column(Text)  # up, down, degraded
    latency_ms = Column(Integer)
    last_check_at = Column(DateTime(timezone=True))


class SystemIncident(Base):
    """
    Incident management when things break in the system.
    """

    __tablename__ = "system_incidents"

    id = Column(UUIDv7, primary_key=True, default=generate_uuid7)
    incident_type = Column(Text)  # e.g., 'dependency_drift', 'api_latency_high'
    severity = Column(Text)  # 'critical', 'warning'
    is_auto_resolved = Column(Boolean, default=False)
    remediation_log = Column(Text)  # Remediation steps taken by agent
    resolved_at = Column(DateTime(timezone=True))
