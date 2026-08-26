from pathlib import Path

from sqlalchemy.orm import Session

from app.models import DetectionEvent, DetectionResult, UploadedImage


def outcome_from_detections(detections: list[dict]) -> str:
    if any(item["is_abnormal"] for item in detections):
        return "abnormal"
    if detections:
        return "normal"
    return "no_detection"


def media_url(path_value: str | None, category: str) -> str | None:
    if not path_value:
        return None
    return f"/api/media/{category}/{Path(path_value).name}"


def add_detection_rows(
    db: Session,
    event: DetectionEvent,
    detections: list[dict],
    *,
    uploaded_image_id: int | None,
    frame_path: str | None,
    annotated_path: str | None,
    camera_source: str | None,
) -> None:
    for detection in detections:
        bbox = detection["bbox"]
        db.add(
            DetectionResult(
                event_id=event.id,
                uploaded_image_id=uploaded_image_id,
                label=detection["label"],
                confidence=detection["confidence"],
                bbox_x=bbox["x"],
                bbox_y=bbox["y"],
                bbox_width=bbox["width"],
                bbox_height=bbox["height"],
                is_abnormal=detection["is_abnormal"],
                frame_path=frame_path,
                annotated_path=annotated_path,
                camera_source=camera_source,
            )
        )


def serialize_event(event: DetectionEvent, *, include_detections: bool = True) -> dict:
    upload: UploadedImage | None = event.uploaded_image
    data = {
        "id": event.id,
        "source_type": event.source_type,
        "status": event.status,
        "outcome": event.outcome,
        "max_confidence": event.max_confidence,
        "detection_count": event.detection_count,
        "inference_time_ms": event.inference_time_ms,
        "model_version": event.model_version,
        "annotated_url": media_url(event.annotated_path, "camera" if event.source_type == "camera" else "annotated"),
        "error_message": event.error_message,
        "review": {
            "status": event.review_status,
            "corrected_label": event.reviewed_label,
            "notes": event.review_notes,
            "reviewed_by": event.reviewed_by,
            "reviewed_at": event.reviewed_at,
        },
        "detected_at": event.detected_at,
        "image": None,
    }
    if upload:
        data["image"] = {
            "id": upload.id,
            "filename": upload.filename,
            "original_filename": upload.original_filename,
            "url": media_url(upload.file_path, "uploads"),
            "width": upload.width,
            "height": upload.height,
            "size_bytes": upload.size_bytes,
        }
    if include_detections:
        data["detections"] = [
            {
                "id": item.id,
                "label": item.label,
                "confidence": item.confidence,
                "is_abnormal": item.is_abnormal,
                "bbox": {"x": item.bbox_x, "y": item.bbox_y, "width": item.bbox_width, "height": item.bbox_height},
            }
            for item in event.detections
        ]
    return data
