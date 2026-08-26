from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DetectionResult(Base):
    __tablename__ = "detection_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("detection_events.id"),
        nullable=True,
        index=True,
    )

    uploaded_image_id: Mapped[int | None] = mapped_column(
        ForeignKey("uploaded_images.id"),
        nullable=True,
    )

    label: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    bbox_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_width: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_height: Mapped[float | None] = mapped_column(Float, nullable=True)

    is_abnormal: Mapped[bool] = mapped_column(Boolean, default=False)

    frame_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    annotated_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    camera_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    uploaded_image = relationship(
        "UploadedImage",
        back_populates="detections",
    )
    event = relationship("DetectionEvent", back_populates="detections")
