import enum
import uuid
from decimal import Decimal

from sqlalchemy import Enum, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class PolicyScope(enum.StrEnum):
    global_scope = "global"
    per_platform = "per_platform"
    per_action = "per_action"


class ExecutionPolicy(Base):
    __tablename__ = "execution_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)

    scope: Mapped[PolicyScope] = mapped_column(
        Enum(PolicyScope, name="policy_scope_enum", create_type=True),
        nullable=False,
        default=PolicyScope.global_scope,
    )
    scope_ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    max_timeout_seconds: Mapped[int] = mapped_column(Integer, default=45, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    max_serverless_compute_budget_usd: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), default=Decimal("0.0500"), nullable=False
    )
    max_concurrent_sandboxes: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    circuit_breaker_failure_threshold: Mapped[int] = mapped_column(
        Integer, default=5, nullable=False
    )
    circuit_breaker_cooldown_seconds: Mapped[int] = mapped_column(
        Integer, default=300, nullable=False
    )
