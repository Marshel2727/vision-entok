import hashlib
import threading
import time
from pathlib import Path

import cv2
from fastapi import HTTPException
from ultralytics import YOLO

from app.config import settings


class DetectionService:
    def __init__(self):
        self.model = None
        self.model_error: str | None = None
        self._lock = threading.RLock()
        self._model_version: str | None = None

    def load_model(self):
        model_path = settings.ai_model_path

        if not model_path.exists():
            self.model_error = f"Model AI tidak ditemukan: {model_path}"
            raise HTTPException(
                status_code=503,
                detail=f"Model AI tidak ditemukan: {model_path}",
            )

        with self._lock:
            if self.model is None:
                try:
                    self.model = YOLO(str(model_path))
                    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()[:12]
                    self._model_version = f"{model_path.name}:{digest}"
                    self.model_error = None
                except Exception as exc:
                    self.model_error = str(exc)
                    raise HTTPException(status_code=503, detail="Model AI gagal dimuat.") from exc

        return self.model

    def preload(self) -> bool:
        try:
            self.load_model()
            return True
        except HTTPException:
            return False

    @property
    def is_ready(self) -> bool:
        return self.model is not None and self.model_error is None

    @property
    def model_version(self) -> str | None:
        return self._model_version

    def _predict(self, source, confidence: float | None = None) -> tuple[list[dict], object, float]:
        model = self.load_model()
        started = time.perf_counter()
        with self._lock:
            results = model.predict(
                source=source,
                conf=confidence or settings.AI_CONFIDENCE_THRESHOLD,
                verbose=False,
            )
        elapsed_ms = (time.perf_counter() - started) * 1000
        detections: list[dict] = []
        for result in results:
            names = result.names
            for box in result.boxes:
                class_id = int(box.cls[0])
                label = names[class_id]
                confidence_value = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append(
                    {
                        "label": label,
                        "confidence": confidence_value,
                        "is_abnormal": label.lower() == settings.ABNORMAL_LABEL.lower(),
                        "bbox": {
                            "x": x1,
                            "y": y1,
                            "width": x2 - x1,
                            "height": y2 - y1,
                        },
                    }
                )
        annotated = results[0].plot() if results else source
        return detections, annotated, elapsed_ms

    def detect_image(self, image_path: str) -> list[dict]:
        path = Path(image_path)

        if not path.exists():
            raise HTTPException(
                status_code=404,
                detail="File gambar tidak ditemukan.",
            )

        detections, _, _ = self._predict(str(path))
        return detections

    def detect_image_with_annotation(
        self,
        image_path: str,
        confidence: float | None = None,
    ) -> tuple[list[dict], object, float]:
        path = Path(image_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="File gambar tidak ditemukan.")
        return self._predict(str(path), confidence)

    def detect_frame(
        self,
        frame,
        confidence: float | None = None,
    ) -> tuple[list[dict], object, float]:
        if frame is None:
            raise ValueError("Frame kosong.")
        return self._predict(frame, confidence)
