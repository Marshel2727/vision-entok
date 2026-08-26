from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import DetectionEvent, User
from app.models.common import utc_now
from app.services.event_service import serialize_event


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary")
def dashboard_summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    total = db.query(func.count(DetectionEvent.id)).scalar() or 0
    counts = dict(db.query(DetectionEvent.outcome, func.count(DetectionEvent.id)).filter(DetectionEvent.status == "completed").group_by(DetectionEvent.outcome).all())
    failed = db.query(func.count(DetectionEvent.id)).filter(DetectionEvent.status == "failed").scalar() or 0
    trend_rows = db.query(func.date(DetectionEvent.detected_at), DetectionEvent.outcome, func.count(DetectionEvent.id)).filter(DetectionEvent.detected_at >= utc_now() - timedelta(days=13), DetectionEvent.status == "completed").group_by(func.date(DetectionEvent.detected_at), DetectionEvent.outcome).order_by(func.date(DetectionEvent.detected_at)).all()
    trends: dict[str, dict] = {}
    for day, event_outcome, count in trend_rows:
        key = str(day)
        trends.setdefault(key, {"date": key, "normal": 0, "abnormal": 0, "no_detection": 0})
        trends[key][event_outcome or "no_detection"] = count
    recent = db.query(DetectionEvent).filter(DetectionEvent.outcome == "abnormal").order_by(DetectionEvent.detected_at.desc()).limit(5).all()
    completed = sum(counts.values())
    abnormal = counts.get("abnormal", 0)
    data = {"total": total, "normal": counts.get("normal", 0), "abnormal": abnormal, "no_detection": counts.get("no_detection", 0), "failed": failed, "abnormal_percentage": round(abnormal / completed * 100, 2) if completed else 0, "trends": list(trends.values()), "recent_abnormal": [serialize_event(item, include_detections=False) for item in recent]}
    return {"success": True, "message": "Ringkasan dashboard berhasil diambil.", "data": data, "meta": {}}
