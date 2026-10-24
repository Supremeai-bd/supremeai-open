import uuid

from sqlalchemy import Boolean, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class SelectorHealingEvent(Base):
    __tablename__ = "selector_healing_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Ideally this would be a ForeignKey to site_actions_registry, but we assume it's created or will be linked later
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)

    old_selector: Mapped[str] = mapped_column(String(500), nullable=False)
    new_selector: Mapped[str] = mapped_column(String(500), nullable=False)

    confidence_score: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    auto_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    screenshot_before_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    screenshot_after_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
