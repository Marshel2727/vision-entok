from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.config import settings
from app.dependencies import get_current_user
from app.models import User


router = APIRouter(prefix="/media", tags=["Media"])


@router.get("/{category}/{filename}")
def get_media(category: str, filename: str, _: User = Depends(get_current_user)):
    roots = {"uploads": settings.upload_path, "annotated": settings.annotated_path, "camera": settings.camera_media_path}
    root = roots.get(category)
    if root is None or Path(filename).name != filename: raise HTTPException(status_code=404, detail="Media tidak ditemukan.")
    target = (root / filename).resolve()
    if root.resolve() not in target.parents or not target.is_file(): raise HTTPException(status_code=404, detail="Media tidak ditemukan.")
    return FileResponse(target)
