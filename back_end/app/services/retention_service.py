import logging
import threading
from datetime import timedelta

from app.config import settings
from app.database import SessionLocal
from app.models import DetectionEvent
from app.models.common import utc_now

from .file_service import FileService


logger = logging.getLogger(__name__)


class RetentionService:
    def __init__(self, files: FileService) -> None:
        self.files = files
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def cleanup(self) -> dict[str, int]:
        db = SessionLocal()
        removed_images = 0
        removed_events = 0
        try:
            image_cutoff = utc_now() - timedelta(days=settings.IMAGE_RETENTION_DAYS)
            events = db.query(DetectionEvent).filter(
                DetectionEvent.detected_at < image_cutoff,
                DetectionEvent.annotated_path.is_not(None),
                DetectionEvent.review_status != "corrected",
            ).all()
            for event in events:
                self.files.remove_file(event.annotated_path)
                event.annotated_path = None
                removed_images += 1
            metadata_cutoff = utc_now() - timedelta(days=settings.CAMERA_METADATA_RETENTION_DAYS)
            old_events = db.query(DetectionEvent).filter(
                DetectionEvent.source_type == "camera",
                DetectionEvent.detected_at < metadata_cutoff,
                DetectionEvent.review_status != "corrected",
            ).all()
            for event in old_events:
                db.delete(event)
                removed_events += 1
            db.commit()
            return {"removed_images": removed_images, "removed_events": removed_events}
        except Exception:
            db.rollback()
            logger.exception("Cleanup retensi gagal")
            return {"removed_images": 0, "removed_events": 0}
        finally:
            db.close()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.cleanup()
            self._stop.wait(24 * 60 * 60)
