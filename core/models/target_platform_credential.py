import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, Index, LargeBinary, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class AuthType(enum.StrEnum):
    oauth2 = "oauth2"
    cookie_session = "cookie_session"
    api_key = "api_key"  # pragma: allowlist secret
    basic_auth = "basic_auth"


class CredentialStatus(enum.StrEnum):
    active = "active"
    expired = "expired"
    revoked = "revoked"
    needs_reauth = "needs_reauth"


class TargetPlatformCredential(Base):
    __tablename__ = "target_platform_credentials"
    __table_args__ = (Index("idx_tpc_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)

    platform_label: Mapped[str] = mapped_column(String(255), nullable=False)

    auth_type: Mapped[AuthType] = mapped_column(
        Enum(AuthType, name="auth_type_enum", create_type=True), nullable=False
    )

    encrypted_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    kms_key_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[CredentialStatus] = mapped_column(
        Enum(CredentialStatus, name="credential_status_enum", create_type=True),
        nullable=False,
        default=CredentialStatus.active,
    )

    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
