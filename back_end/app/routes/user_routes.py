from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.models import AuthSession, User
from app.models.common import utc_now
from app.schemas import PasswordResetRequest, UserCreate, UserUpdate
from app.services.auth_service import AuthService


router = APIRouter(prefix="/users", tags=["Users"])
auth_service = AuthService()


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


@router.get("")
def list_users(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = db.query(User).order_by(User.created_at.desc())
    total = query.count()
    users = query.offset((page - 1) * limit).limit(limit).all()
    return {
        "success": True,
        "message": "Daftar pengguna berhasil diambil.",
        "data": [serialize_user(user) for user in users],
        "meta": {"page": page, "limit": limit, "total": total},
    }


@router.post("", status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=409, detail="Username sudah digunakan.")
    user = User(
        username=payload.username,
        full_name=payload.full_name,
        password_hash=auth_service.hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"success": True, "message": "Pengguna berhasil dibuat.", "data": serialize_user(user), "meta": {}}


@router.patch("/{user_id}")
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan.")
    changes = payload.model_dump(exclude_unset=True)
    if user.id == admin.id and (
        changes.get("is_active") is False or changes.get("role") == "operator"
    ):
        raise HTTPException(status_code=400, detail="Admin tidak dapat menonaktifkan atau menurunkan role sendiri.")
    for key, value in changes.items():
        setattr(user, key, value)
    db.commit()
    return {"success": True, "message": "Pengguna berhasil diperbarui.", "data": serialize_user(user), "meta": {}}


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: int,
    payload: PasswordResetRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan.")
    user.password_hash = auth_service.hash_password(payload.password)
    db.query(AuthSession).filter(
        AuthSession.user_id == user.id,
        AuthSession.revoked_at.is_(None),
    ).update({AuthSession.revoked_at: utc_now()}, synchronize_session=False)
    db.commit()
    return {"success": True, "message": "Password berhasil direset dan seluruh sesi dicabut.", "data": None, "meta": {}}
