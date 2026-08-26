from typing import Any, Literal

from pydantic import BaseModel, Field


class CameraUpdate(BaseModel):
    name: str = Field(default="Kamera Entok", min_length=2, max_length=120)
    source_type: Literal["opencv", "rtsp", "ffmpeg", "screen", "adb"]
    source_value: str = Field(min_length=1, max_length=2000)
    username: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, max_length=500)
    config: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = False
    auto_start: bool = False
    detection_interval_seconds: float = Field(default=2.0, ge=0.5, le=60)
    confidence_threshold: float = Field(default=0.5, ge=0.05, le=1.0)
    snapshot_cooldown_seconds: float = Field(default=5.0, ge=0, le=3600)
