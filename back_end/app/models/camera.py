from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

from .common import utc_now


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="Kamera Entok", nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), default="opencv", nullable=False)
    source_value: Mapped[str] = mapped_column(Text, default="0", nullable=False)
    username_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_start: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    detection_interval_seconds: Mapped[float] = mapped_column(Float, default=2.0, nullable=False)
    confidence_threshold: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    snapshot_cooldown_seconds: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
