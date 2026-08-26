import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class EncryptionService:
    def __init__(self) -> None:
        raw_key = settings.APP_ENCRYPTION_KEY.strip()
        if raw_key:
            key = raw_key.encode("utf-8")
        else:
            key = base64.urlsafe_b64encode(
                hashlib.sha256(settings.JWT_SECRET_KEY.encode("utf-8")).digest()
            )
        self.fernet = Fernet(key)

    def encrypt(self, value: str | None) -> str | None:
        if not value:
            return None
        return self.fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str | None) -> str | None:
        if not value:
            return None
        try:
            return self.fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            return None
