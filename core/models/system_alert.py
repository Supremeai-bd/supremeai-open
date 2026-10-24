import datetime

from sqlalchemy import Boolean, Column, DateTime, String, Text

from models.base import Base


class SystemAlert(Base):
    __tablename__ = "system_alerts"

    id = Column(String(36), primary_key=True)
    level = Column(String(20), nullable=False, default="info")  # info, warning, error, critical
    message = Column(Text, nullable=False)
    resolved = Column(Boolean, default=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.UTC)
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)
