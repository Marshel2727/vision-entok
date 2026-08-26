from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import LoginRequest
from app.services.auth_service import AuthService


router = APIRouter(prefix="/auth", tags=["Auth"])
auth_service = AuthService()


def user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
    }


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    common = {
        "httponly": True,
        "secure": settings.AUTH_COOKIE_SECURE,
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie(
        settings.ACCESS_COOKIE_NAME,
        access_token,
        max_age=settings.ACCESS_TOKEN_MINUTES * 60,
        **common,
    )
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=settings.REFRESH_TOKEN_DAYS * 24 * 60 * 60,
        **common,
    )


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = auth_service.authenticate(db, payload.username, payload.password)
    access, refresh, _ = auth_service.issue_session(
        db,
        user,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    set_auth_cookies(response, access, refresh)
    return {"success": True, "message": "Login berhasil.", "data": user_payload(user), "meta": {}}


@router.post("/refresh")
def refresh_session(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME),
    db: Session = Depends(get_db),
):
    if not refresh_token:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Refresh token tidak tersedia.")
    access, refresh, user = auth_service.rotate_refresh(
        db,
        refresh_token,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    set_auth_cookies(response, access, refresh)
    return {"success": True, "message": "Sesi diperbarui.", "data": user_payload(user), "meta": {}}


@router.post("/logout")
def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME),
    db: Session = Depends(get_db),
):
    auth_service.revoke_refresh(db, refresh_token)
    response.delete_cookie(settings.ACCESS_COOKIE_NAME, path="/")
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path="/")
    return {"success": True, "message": "Logout berhasil.", "data": None, "meta": {}}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"success": True, "message": "Profil berhasil diambil.", "data": user_payload(user), "meta": {}}
