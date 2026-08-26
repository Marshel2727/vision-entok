from fastapi import Cookie, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import AuthSession, User
from app.services.auth_service import AuthService


auth_service = AuthService()


def get_current_user(
    db: Session = Depends(get_db),
    access_cookie: str | None = Cookie(default=None, alias=settings.ACCESS_COOKIE_NAME),
    authorization: str | None = Header(default=None),
) -> User:
    token = access_cookie
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Autentikasi diperlukan.")

    payload = auth_service.decode_access(token)
    user = db.get(User, int(payload["sub"]))
    session = (
        db.query(AuthSession)
        .filter(AuthSession.session_id == payload.get("sid"))
        .first()
    )
    if not user or not user.is_active or not session or session.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Sesi tidak aktif.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Akses admin diperlukan.")
    return user
