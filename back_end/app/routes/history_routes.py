from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import DetectionResult, UploadedImage, User
from app.services.event_service import media_url


router = APIRouter(prefix="/history", tags=["History"])


@router.get("/uploads")
def get_upload_history(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    uploads = (
        db.query(UploadedImage)
        .order_by(desc(UploadedImage.created_at))
        .limit(limit)
        .all()
    )

    return {
        "success": True,
        "message": "Riwayat upload berhasil diambil.",
        "data": [
            {
                "id": item.id,
                "filename": item.filename,
                "original_filename": item.original_filename,
                "url": media_url(item.file_path, "uploads"),
                "content_type": item.content_type,
                "size_bytes": item.size_bytes,
                "width": item.width,
                "height": item.height,
                "source": item.source,
                "created_at": item.created_at,
            }
            for item in uploads
        ],
        "meta": {"limit": limit},
    }


@router.get("/detections")
def get_detection_history(
    abnormal_only: bool = False,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    query = db.query(DetectionResult).order_by(desc(DetectionResult.detected_at))

    if abnormal_only:
        query = query.filter(DetectionResult.is_abnormal.is_(True))

    detections = query.limit(limit).all()

    return {
        "success": True,
        "message": "Riwayat deteksi berhasil diambil.",
        "data": [
            {
                "id": item.id,
                "uploaded_image_id": item.uploaded_image_id,
                "label": item.label,
                "confidence": item.confidence,
                "is_abnormal": item.is_abnormal,
                "bbox": {
                    "x": item.bbox_x,
                    "y": item.bbox_y,
                    "width": item.bbox_width,
                    "height": item.bbox_height,
                },
                "frame_url": media_url(item.frame_path, "uploads"),
                "annotated_url": media_url(item.annotated_path, "annotated"),
                "camera_source": item.camera_source,
                "detected_at": item.detected_at,
            }
            for item in detections
        ],
        "meta": {"limit": limit, "abnormal_only": abnormal_only},
    }
