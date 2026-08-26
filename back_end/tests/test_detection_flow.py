from io import BytesIO

import numpy as np
from PIL import Image

from app.config import settings
from app.services import detection_service
from app.services.event_service import outcome_from_detections


def image_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (64, 64), "white").save(output, format="JPEG")
    return output.getvalue()


def test_outcome_priority():
    assert outcome_from_detections([]) == "no_detection"
    assert outcome_from_detections([{"is_abnormal": False}]) == "normal"
    assert outcome_from_detections([{"is_abnormal": False}, {"is_abnormal": True}]) == "abnormal"


def test_upload_detection_creates_event_and_annotation(logged_in_client, monkeypatch, tmp_path):
    original_upload = settings.UPLOAD_DIR
    original_annotated = settings.ANNOTATED_DIR
    settings.UPLOAD_DIR = str(tmp_path / "uploads")
    settings.ANNOTATED_DIR = str(tmp_path / "annotated")

    def fake_detect(_path, _confidence=None):
        detections = [{"label": "abnormal", "confidence": 0.91, "is_abnormal": True, "bbox": {"x": 1.0, "y": 2.0, "width": 30.0, "height": 20.0}}]
        return detections, np.zeros((64, 64, 3), dtype=np.uint8), 12.5

    monkeypatch.setattr(detection_service, "detect_image_with_annotation", fake_detect)
    monkeypatch.setattr(detection_service, "_model_version", "fake:test")
    try:
        response = logged_in_client.post("/api/detections/images", files={"file": ("mata.jpg", image_bytes(), "image/jpeg")})
    finally:
        settings.UPLOAD_DIR = original_upload
        settings.ANNOTATED_DIR = original_annotated

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["outcome"] == "abnormal"
    assert data["detection_count"] == 1
    assert data["annotated_url"].startswith("/api/media/annotated/")


def test_invalid_file_type_is_rejected(logged_in_client):
    response = logged_in_client.post("/api/detections/images", files={"file": ("data.txt", b"not image", "text/plain")})
    assert response.status_code == 400
