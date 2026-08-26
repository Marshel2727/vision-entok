from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import UploadedImage, User
from app.services import file_service
from app.services.event_service import media_url


router = APIRouter(prefix="/uploads", tags=["Uploads"])


@router.post("/images")
def upload_image(
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
    )

    db.add(uploaded_image)
    db.commit()
    db.refresh(uploaded_image)

    return {
        "success": True,
        "message": "Gambar berhasil diupload.",
        "data": {
            "id": uploaded_image.id,
            "filename": uploaded_image.filename,
            "original_filename": uploaded_image.original_filename,
            "url": media_url(uploaded_image.file_path, "uploads"),
            "content_type": uploaded_image.content_type,
            "size_bytes": uploaded_image.size_bytes,
            "width": uploaded_image.width,
            "height": uploaded_image.height,
            "source": uploaded_image.source,
            "created_at": uploaded_image.created_at,
        },
        "meta": {},
    }
