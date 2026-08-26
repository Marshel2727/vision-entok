from io import BytesIO
from uuid import uuid4
from pathlib import Path

import cv2
from fastapi import HTTPException, UploadFile
from PIL import Image

from app.config import settings


class FileService:
    allowed_content_types = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }

    def save_upload_image(self, file: UploadFile) -> dict:
        if file.content_type not in self.allowed_content_types:
            raise HTTPException(
                status_code=400,
                detail="Format file tidak didukung. Gunakan JPG, PNG, atau WEBP.",
            )

        content = file.file.read()
        max_size = settings.MAX_UPLOAD_MB * 1024 * 1024

        if len(content) > max_size:
            raise HTTPException(
                status_code=400,
                detail=f"Ukuran file maksimal {settings.MAX_UPLOAD_MB} MB.",
            )

        try:
            image = Image.open(BytesIO(content))
            width, height = image.size
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="File bukan gambar yang valid.",
            )

        upload_dir = settings.upload_path
        upload_dir.mkdir(parents=True, exist_ok=True)

        extension = self.allowed_content_types[file.content_type]
        filename = f"{uuid4().hex}{extension}"
        file_path = upload_dir / filename
        file_path.write_bytes(content)

        return {
            "filename": filename,
            "original_filename": file.filename,
            "file_path": str(file_path),
            "content_type": file.content_type,
            "size_bytes": len(content),
            "width": width,
            "height": height,
        }

    def save_annotated_image(self, frame, *, category: str = "annotated") -> dict:
        if category == "camera":
            output_dir = settings.camera_media_path
        else:
            output_dir = settings.annotated_path
            category = "annotated"
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid4().hex}.jpg"
        path = output_dir / filename
        if not cv2.imwrite(str(path), frame):
            raise HTTPException(status_code=500, detail="Gambar hasil tidak dapat disimpan.")
        return {
            "filename": filename,
            "file_path": str(path),
            "media_url": f"/api/media/{category}/{filename}",
        }

    @staticmethod
    def remove_file(path_value: str | Path | None) -> None:
        if not path_value:
            return
        path = Path(path_value)
        if path.is_file():
            path.unlink()
