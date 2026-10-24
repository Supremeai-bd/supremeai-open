from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from models.base import Base
from utils.uuid_gen import UUIDv7, generate_uuid7


class AgentReflection(Base):
    """
    Agent experience and learning memory.
    """

    __tablename__ = "agent_reflections"

    id = Column(UUIDv7, primary_key=True, default=generate_uuid7)
    agent_id = Column(Integer, ForeignKey("dynamic_agents.id", ondelete="CASCADE"))
    task_id = Column(String)  # Reference to pending_tasks.db sqlite
    outcome_summary = Column(Text)
    learned_patterns = Column(JSON().with_variant(JSONB, "postgresql"))
    confidence_score = Column(Float)
    created_at = Column(DateTime(timezone=True), default=func.now())


class DynamicCapability(Base):
    """
    Dynamically created tools/skills (On-the-fly synthesis).
    """

    __tablename__ = "dynamic_capabilities"

    id = Column(UUIDv7, primary_key=True, default=generate_uuid7)
    capability_name = Column(Text)
    code_blob = Column(Text)
    success_rate = Column(Float, default=0.0)
    version = Column(Integer, default=1)
    is_auto_generated = Column(Boolean, default=True)
    is_approved = Column(Boolean, default=False)


class ExecutionChain(Base):
    """
    Chain of thought log tracking the agent's logic process.
    """

    __tablename__ = "execution_chains"

    id = Column(UUIDv7, primary_key=True, default=generate_uuid7)
    task_id = Column(String)  # Reference to pending_tasks.db sqlite
    chain_of_thought = Column(Text)
    tokens_used = Column(Integer)
    model_provider = Column(Text)
    raw_response = Column(JSON().with_variant(JSONB, "postgresql"))
    created_at = Column(DateTime(timezone=True), default=func.now())
