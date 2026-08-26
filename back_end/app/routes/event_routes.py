from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user
from app.models import DetectionEvent, User
from app.models.common import utc_now
from app.schemas import EventReviewRequest
from app.services.event_service import serialize_event


router = APIRouter(prefix="/detection-events", tags=["Detection Events"])


@router.get("")
def list_events(
    page: int = Query(default=1, ge=1), limit: int = Query(default=20, ge=1, le=100),
    outcome: str | None = None, source_type: str | None = None, status: str | None = None,
    review_status: str | None = None, min_confidence: float | None = Query(default=None, ge=0, le=1),
    date_from: date | None = None, date_to: date | None = None,
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    query = db.query(DetectionEvent)
    if outcome: query = query.filter(DetectionEvent.outcome == outcome)
    if source_type: query = query.filter(DetectionEvent.source_type == source_type)
    if status: query = query.filter(DetectionEvent.status == status)
    if review_status: query = query.filter(DetectionEvent.review_status == review_status)
    if min_confidence is not None: query = query.filter(DetectionEvent.max_confidence >= min_confidence)
    if date_from: query = query.filter(DetectionEvent.detected_at >= datetime.combine(date_from, time.min))
    if date_to: query = query.filter(DetectionEvent.detected_at <= datetime.combine(date_to, time.max))
    total = query.count()
    events = query.options(joinedload(DetectionEvent.uploaded_image)).order_by(DetectionEvent.detected_at.desc()).offset((page - 1) * limit).limit(limit).all()
    return {"success": True, "message": "Riwayat deteksi berhasil diambil.", "data": [serialize_event(event, include_detections=False) for event in events], "meta": {"page": page, "limit": limit, "total": total}}


@router.get("/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    event = db.query(DetectionEvent).options(joinedload(DetectionEvent.uploaded_image), joinedload(DetectionEvent.detections)).filter(DetectionEvent.id == event_id).first()
    if not event: raise HTTPException(status_code=404, detail="Event deteksi tidak ditemukan.")
    return {"success": True, "message": "Detail deteksi berhasil diambil.", "data": serialize_event(event), "meta": {}}


@router.patch("/{event_id}/review")
def review_event(event_id: int, payload: EventReviewRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    event = db.get(DetectionEvent, event_id)
    if not event: raise HTTPException(status_code=404, detail="Event deteksi tidak ditemukan.")
    event.review_status = payload.status
    event.reviewed_label = payload.corrected_label if payload.status == "corrected" else None
    event.review_notes = payload.notes
    event.reviewed_by = user.id
    event.reviewed_at = utc_now()
    db.commit()
    return {"success": True, "message": "Review berhasil disimpan.", "data": serialize_event(event), "meta": {}}
