from __future__ import annotations

import logging
import threading
import time
from urllib.parse import quote, urlsplit, urlunsplit

import cv2

from ai.frame_sources import create_frame_source
from app.database import SessionLocal
from app.models import Camera, DetectionEvent

from .detection_service import DetectionService
from .encryption_service import EncryptionService
from .event_service import add_detection_rows, outcome_from_detections
from .file_service import FileService


logger = logging.getLogger(__name__)


class CameraRuntimeManager:
    def __init__(self, detector: DetectionService, files: FileService) -> None:
        self.detector = detector
        self.files = files
        self.encryption = EncryptionService()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._latest_jpeg: bytes | None = None
        self._status = "stopped"
        self._error: str | None = None
        self._fps = 0.0
        self._last_detection: dict | None = None
        self._active_camera_id: int | None = None
        self._last_snapshot_at = 0.0

    @staticmethod
    def _source_with_credentials(source: str, username: str | None, password: str | None) -> str:
        if not username or "://" not in source:
            return source
        parts = urlsplit(source)
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        credentials = quote(username, safe="")
        if password:
            credentials += f":{quote(password, safe='')}"
        return urlunsplit((parts.scheme, f"{credentials}@{host}", parts.path, parts.query, parts.fragment))

    def _runtime_config(self, camera: Camera) -> dict:
        config = dict(camera.config_json or {})
        username = self.encryption.decrypt(camera.username_encrypted)
        password = self.encryption.decrypt(camera.password_encrypted)
        config["source_type"] = camera.source_type
        config["source"] = self._source_with_credentials(camera.source_value, username, password)
        return config

    def test_camera(self, camera: Camera) -> dict:
        source = create_frame_source(self._runtime_config(camera))
        try:
            source.open()
            ok, frame = source.read()
            if not ok or frame is None:
                raise RuntimeError("Kamera terbuka tetapi frame belum tersedia.")
            height, width = frame.shape[:2]
            return {"connected": True, "width": width, "height": height}
        finally:
            source.release()

    def start(self, camera_id: int) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                if self._active_camera_id == camera_id:
                    return
                raise RuntimeError("Kamera lain masih aktif.")
            self._stop.clear()
            self._status = "starting"
            self._error = None
            self._active_camera_id = camera_id
            self._thread = threading.Thread(target=self._run, args=(camera_id,), daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=5)
        with self._lock:
            self._status = "stopped"
            self._active_camera_id = None
            self._thread = None

    def _persist_detection(self, camera: Camera, detections: list[dict], annotated, elapsed_ms: float) -> None:
        db = SessionLocal()
        try:
            outcome = outcome_from_detections(detections)
            annotated_path = None
            now = time.time()
            if outcome == "abnormal" and now - self._last_snapshot_at >= camera.snapshot_cooldown_seconds:
                saved = self.files.save_annotated_image(annotated, category="camera")
                annotated_path = saved["file_path"]
                self._last_snapshot_at = now
            event = DetectionEvent(
                camera_id=camera.id,
                source_type="camera",
                status="completed",
                outcome=outcome,
                max_confidence=max((item["confidence"] for item in detections), default=None),
                detection_count=len(detections),
                inference_time_ms=elapsed_ms,
                model_version=self.detector.model_version,
                annotated_path=annotated_path,
            )
            db.add(event)
            db.flush()
            add_detection_rows(
                db,
                event,
                detections,
                uploaded_image_id=None,
                frame_path=None,
                annotated_path=annotated_path,
                camera_source=camera.name,
            )
            db.commit()
            with self._lock:
                self._last_detection = {
                    "event_id": event.id,
                    "outcome": outcome,
                    "confidence": event.max_confidence,
                    "detected_at": event.detected_at.isoformat(),
                }
        except Exception:
            db.rollback()
            logger.exception("Gagal menyimpan event kamera")
        finally:
            db.close()

    def _run(self, camera_id: int) -> None:
        db = SessionLocal()
        source = None
        try:
            camera = db.get(Camera, camera_id)
            if not camera or not camera.is_enabled:
                raise RuntimeError("Konfigurasi kamera tidak aktif.")
            config = self._runtime_config(camera)
            source = create_frame_source(config)
            source.open()
            with self._lock:
                self._status = "running"
            last_frame_at = time.perf_counter()
            last_inference_at = 0.0

            while not self._stop.is_set():
                ok, frame = source.read()
                if not ok or frame is None:
                    time.sleep(0.1)
                    continue
                now = time.perf_counter()
                delta = max(now - last_frame_at, 1e-6)
                last_frame_at = now
                display_frame = frame

                if now - last_inference_at >= camera.detection_interval_seconds:
                    detections, annotated, elapsed_ms = self.detector.detect_frame(
                        frame,
                        camera.confidence_threshold,
                    )
                    display_frame = annotated
                    last_inference_at = now
                    self._persist_detection(camera, detections, annotated, elapsed_ms)

                encoded, buffer = cv2.imencode(".jpg", display_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if encoded:
                    with self._lock:
                        self._latest_jpeg = buffer.tobytes()
                        self._fps = 1 / delta
        except Exception as exc:
            logger.exception("Runtime kamera berhenti")
            with self._lock:
                self._status = "error"
                self._error = str(exc)
        finally:
            if source is not None:
                source.release()
            db.close()
            if self._stop.is_set():
                with self._lock:
                    self._status = "stopped"

    def status(self) -> dict:
        with self._lock:
            return {
                "status": self._status,
                "error": self._error,
                "fps": round(self._fps, 1),
                "camera_id": self._active_camera_id,
                "has_frame": self._latest_jpeg is not None,
                "last_detection": self._last_detection,
            }

    def mjpeg(self):
        while True:
            with self._lock:
                frame = self._latest_jpeg
                state = self._status
            if frame:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            elif state in {"stopped", "error"}:
                return
            time.sleep(0.1)
