from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

from .common import utc_now


class DetectionEvent(Base):
    __tablename__ = "detection_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    uploaded_image_id: Mapped[int | None] = mapped_column(
        ForeignKey("uploaded_images.id"),
        nullable=True,
        index=True,
    )
    camera_id: Mapped[int | None] = mapped_column(
        ForeignKey("cameras.id"),
        nullable=True,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(30), default="upload", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="processing", nullable=False, index=True)
    outcome: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    max_confidence: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    detection_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inference_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(150), nullable=True)
    annotated_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(30), default="unreviewed", nullable=False, index=True
    )
    reviewed_label: Mapped[str | None] = mapped_column(String(30), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    detections = relationship(
        "DetectionResult",
        back_populates="event",
        cascade="all, delete-orphan",
    )
    uploaded_image = relationship("UploadedImage")
    camera = relationship("Camera")
    reviewer = relationship("User")
