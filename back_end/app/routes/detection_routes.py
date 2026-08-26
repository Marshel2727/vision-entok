from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import DetectionEvent, UploadedImage, User
from app.models.common import utc_now
from app.services import detection_service, file_service
from app.services.event_service import add_detection_rows, outcome_from_detections, serialize_event


router = APIRouter(prefix="/detections", tags=["Detections"])


@router.post("/images")
def detect_uploaded_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    saved_image = file_service.save_upload_image(file)

    uploaded_image = UploadedImage(
        filename=saved_image["filename"],
        original_filename=saved_image["original_filename"],
        file_path=saved_image["file_path"],
        content_type=saved_image["content_type"],
        size_bytes=saved_image["size_bytes"],
        width=saved_image["width"],
        height=saved_image["height"],
        source="upload",
        status="processing",
    )
    db.add(uploaded_image)
    db.flush()
    event = DetectionEvent(uploaded_image_id=uploaded_image.id, source_type="upload", status="processing")
    db.add(event)
    db.commit()

    try:
        detections, annotated_frame, elapsed_ms = detection_service.detect_image_with_annotation(uploaded_image.file_path)
        annotated = file_service.save_annotated_image(annotated_frame)
        event.outcome = outcome_from_detections(detections)
        event.status = "completed"
        event.max_confidence = max((item["confidence"] for item in detections), default=None)
        event.detection_count = len(detections)
        event.inference_time_ms = elapsed_ms
        event.model_version = detection_service.model_version
        event.annotated_path = annotated["file_path"]
        uploaded_image.status = "completed"
        uploaded_image.processed_at = utc_now()
        add_detection_rows(
            db,
            event,
            detections,
            uploaded_image_id=uploaded_image.id,
            frame_path=uploaded_image.file_path,
            annotated_path=annotated["file_path"],
            camera_source=None,
        )
        db.commit()
        db.refresh(event)
    except HTTPException as exc:
        db.rollback()
        failed_event = db.get(DetectionEvent, event.id)
        upload = db.get(UploadedImage, uploaded_image.id)
        if failed_event:
            failed_event.status = "failed"
            failed_event.error_message = str(exc.detail)[:1000]
            failed_event.uploaded_image_id = None
        if upload:
            file_service.remove_file(upload.file_path)
            db.delete(upload)
        db.commit()
        raise
    except Exception as exc:
        db.rollback()
        failed_event = db.get(DetectionEvent, event.id)
        upload = db.get(UploadedImage, uploaded_image.id)
        if failed_event:
            failed_event.status = "failed"
            failed_event.error_message = "Inferensi gagal diproses."
            failed_event.uploaded_image_id = None
        if upload:
            file_service.remove_file(upload.file_path)
            db.delete(upload)
        db.commit()
        raise HTTPException(status_code=500, detail="Inferensi gagal diproses.") from exc

    return {
        "success": True,
        "message": "Deteksi gambar selesai.",
        "data": serialize_event(event),
        "meta": {},
    }
