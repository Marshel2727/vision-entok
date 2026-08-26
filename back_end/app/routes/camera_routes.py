from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models import Camera, User
from app.schemas import CameraUpdate
from app.services import camera_manager, encryption_service


router = APIRouter(prefix="/camera", tags=["Camera"])


def serialize_camera(camera: Camera | None) -> dict | None:
    if not camera:
        return None
    return {
        "id": camera.id,
        "name": camera.name,
        "source_type": camera.source_type,
        "source_value": camera.source_value,
        "has_username": bool(camera.username_encrypted),
        "has_password": bool(camera.password_encrypted),
        "config": camera.config_json or {},
        "is_enabled": camera.is_enabled,
        "auto_start": camera.auto_start,
        "detection_interval_seconds": camera.detection_interval_seconds,
        "confidence_threshold": camera.confidence_threshold,
        "snapshot_cooldown_seconds": camera.snapshot_cooldown_seconds,
        "created_at": camera.created_at,
        "updated_at": camera.updated_at,
    }


@router.get("")
def get_camera(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    camera = db.query(Camera).order_by(Camera.id).first()
    return {"success": True, "message": "Konfigurasi kamera berhasil diambil.", "data": serialize_camera(camera), "meta": {}}


@router.put("")
def update_camera(payload: CameraUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    camera = db.query(Camera).order_by(Camera.id).first() or Camera()
    camera.name = payload.name
    camera.source_type = payload.source_type
    camera.source_value = payload.source_value
    camera.config_json = payload.config
    camera.is_enabled = payload.is_enabled
    camera.auto_start = payload.auto_start
    camera.detection_interval_seconds = payload.detection_interval_seconds
    camera.confidence_threshold = payload.confidence_threshold
    camera.snapshot_cooldown_seconds = payload.snapshot_cooldown_seconds
    if payload.username is not None:
        camera.username_encrypted = encryption_service.encrypt(payload.username)
    if payload.password is not None:
        camera.password_encrypted = encryption_service.encrypt(payload.password)
    db.add(camera)
    db.commit()
    db.refresh(camera)
    return {"success": True, "message": "Konfigurasi kamera berhasil disimpan.", "data": serialize_camera(camera), "meta": {}}


@router.post("/test")
def test_camera(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    camera = db.query(Camera).order_by(Camera.id).first()
    if not camera: raise HTTPException(status_code=404, detail="Konfigurasi kamera belum tersedia.")
    try:
        result = camera_manager.test_camera(camera)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "message": "Kamera berhasil diuji.", "data": result, "meta": {}}


@router.post("/start")
def start_camera(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    camera = db.query(Camera).order_by(Camera.id).first()
    if not camera: raise HTTPException(status_code=404, detail="Konfigurasi kamera belum tersedia.")
    try: camera_manager.start(camera.id)
    except RuntimeError as exc: raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"success": True, "message": "Kamera sedang dijalankan.", "data": camera_manager.status(), "meta": {}}


@router.post("/stop")
def stop_camera(_: User = Depends(require_admin)):
    camera_manager.stop()
    return {"success": True, "message": "Kamera dihentikan.", "data": camera_manager.status(), "meta": {}}


@router.get("/status")
def camera_status(_: User = Depends(get_current_user)):
    return {"success": True, "message": "Status kamera berhasil diambil.", "data": camera_manager.status(), "meta": {}}


@router.get("/stream.mjpg")
def camera_stream(_: User = Depends(get_current_user)):
    return StreamingResponse(camera_manager.mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame")
