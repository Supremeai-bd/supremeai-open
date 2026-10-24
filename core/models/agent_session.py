import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class AgentSessionState(enum.StrEnum):
    Idle = "Idle"
    Scanning_Target_DOM = "Scanning_Target_DOM"
    Executing_Workflows = "Executing_Workflows"
    Circuit_Breaker_Open = "Circuit_Breaker_Open"
    Self_Healing_Retries = "Self_Healing_Retries"
    Awaiting_Human_Input = "Awaiting_Human_Input"
    Success = "Success"
    Failed = "Failed"


class ControlMode(enum.StrEnum):
    agent = "agent"
    pending_handoff = "pending_handoff"
    human = "human"


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)

    current_state: Mapped[AgentSessionState] = mapped_column(
        Enum(AgentSessionState, name="agent_session_state", create_type=True),
        nullable=False,
        default=AgentSessionState.Idle,
    )
    control_mode: Mapped[ControlMode] = mapped_column(
        Enum(ControlMode, name="control_mode", create_type=True),
        nullable=False,
        default=ControlMode.agent,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
