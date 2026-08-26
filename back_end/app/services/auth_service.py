from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from uuid import uuid4

import jwt
from fastapi import HTTPException, status
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuthSession, User
from app.models.common import utc_now


password_hash = PasswordHash.recommended()


class AuthService:
    def hash_password(self, password: str) -> str:
        return password_hash.hash(password)

    def verify_password(self, password: str, password_digest: str) -> bool:
        return password_hash.verify(password, password_digest)

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def authenticate(self, db: Session, username: str, password: str) -> User:
        user = db.query(User).filter(User.username == username.strip().lower()).first()
        now = utc_now()

        if user and user.locked_until and user.locked_until > now:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Terlalu banyak percobaan login. Coba kembali nanti.",
            )

        valid = bool(user and self.verify_password(password, user.password_hash))
        if not valid:
            if user:
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= settings.LOGIN_MAX_ATTEMPTS:
                    user.locked_until = now + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
                    user.failed_login_attempts = 0
                db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Username atau password salah.",
            )

        if not user.is_active:
            raise HTTPException(status_code=403, detail="Akun tidak aktif.")

        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        db.commit()
        return user

    def _access_token(self, user: User, session_id: str) -> str:
        now = utc_now()
        payload = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
            "sid": session_id,
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
        }
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    def issue_session(
        self,
        db: Session,
        user: User,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[str, str, AuthSession]:
        raw_refresh = secrets.token_urlsafe(48)
        session_id = uuid4().hex
        session = AuthSession(
            session_id=session_id,
            user_id=user.id,
            refresh_token_hash=self.hash_token(raw_refresh),
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=utc_now() + timedelta(days=settings.REFRESH_TOKEN_DAYS),
        )
        db.add(session)
        db.commit()
        return self._access_token(user, session_id), raw_refresh, session

    def decode_access(self, token: str) -> dict:
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail="Sesi tidak valid atau kedaluwarsa.") from exc
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Token tidak valid.")
        return payload

    def rotate_refresh(
        self,
        db: Session,
        raw_refresh: str,
        *,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[str, str, User]:
        session = (
            db.query(AuthSession)
            .filter(AuthSession.refresh_token_hash == self.hash_token(raw_refresh))
            .first()
        )
        if (
            not session
            or session.revoked_at is not None
            or session.expires_at <= utc_now()
            or not session.user.is_active
        ):
            raise HTTPException(status_code=401, detail="Refresh token tidak valid.")

        session.revoked_at = utc_now()
        access, refresh, _ = self.issue_session(
            db,
            session.user,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return access, refresh, session.user

    def revoke_refresh(self, db: Session, raw_refresh: str | None) -> None:
        if not raw_refresh:
            return
        session = (
            db.query(AuthSession)
            .filter(AuthSession.refresh_token_hash == self.hash_token(raw_refresh))
            .first()
        )
        if session and session.revoked_at is None:
            session.revoked_at = utc_now()
            db.commit()
