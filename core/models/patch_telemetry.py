import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class PatchTelemetry(Base):
    """বাংলা মন্তব্য: Self-Healing Engine এর ফিডব্যাক লুপ — ইউজার একটি auto-generated
    প্যাচ Accept/Reject/Modify করলে তার রেকর্ড। এই ডেটা ছাড়া সিস্টেম শিখতে পারে না
    কোন ধরনের প্যাচ বিশ্বাসযোগ্য, তাই persist করা must, শুধু log করা যথেষ্ট না।
    """

    __tablename__ = "patch_telemetry"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    error_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    patch_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # ACCEPTED / REJECTED / MODIFIED
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
