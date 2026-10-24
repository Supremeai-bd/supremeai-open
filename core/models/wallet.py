import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class UserWallet(Base):
    __tablename__ = "user_wallets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)

    # Pro Tip: Float ব্যবহার করলে প্রিসিশন লস হয়। তাই Micro-transactions এর জন্য Numeric(10,6) ব্যবহার করা হলো।
    balance_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), default=Decimal("0.000000"), nullable=False
    )
    monthly_allowance_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), default=Decimal("0.000000"), nullable=False
    )

    # Optimistic Concurrency Control (Second Layer of Defense against Double-Spending)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __mapper_args__ = {
        "version_id_col": version
    }  # SQLAlchemy অটোমেটিকভাবে ভার্সন ট্র্যাকিং এবং রেস-কন্ডিশন ব্লক করবে


class TransactionLedgerEntry(Base):
    __tablename__ = "transaction_ledger"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    # Pro Tip: Composite Index
    __table_args__ = (Index("idx_user_time", "user_id", "timestamp"),)
