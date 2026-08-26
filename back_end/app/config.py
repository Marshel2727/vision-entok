from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, text


BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    APP_NAME: str = "Deteksi Entok Backend"
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    API_PREFIX: str = "/api"

    FRONTEND_URL: str = "http://localhost:3000"

    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "cv_entok_db"
    DATABASE_URL: str = "mysql+pymysql://root@127.0.0.1:3306/cv_entok_db?charset=utf8mb4"

    UPLOAD_DIR: str = "app/static/uploads"
    ANNOTATED_DIR: str = "app/static/annotated"
    CAMERA_MEDIA_DIR: str = "app/static/camera"
    TEMP_DIR: str = "app/static/temp"
    MAX_UPLOAD_MB: int = 10

    AI_MODEL_PATH: str = "ai/models/best.pt"
    AI_CONFIDENCE_THRESHOLD: float = 0.50
    ABNORMAL_LABEL: str = "abnormal"
    SAVE_ABNORMAL_ONLY: bool = True

    JWT_SECRET_KEY: str = "change-this-development-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 15
    REFRESH_TOKEN_DAYS: int = 7
    AUTH_COOKIE_SECURE: bool = False
    ACCESS_COOKIE_NAME: str = "entok_access"
    REFRESH_COOKIE_NAME: str = "entok_refresh"
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCK_MINUTES: int = 15
    APP_ENCRYPTION_KEY: str = ""

    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "logs"
    IMAGE_RETENTION_DAYS: int = 30
    CAMERA_METADATA_RETENTION_DAYS: int = 90

    CAMERA_SOURCE: str = ""
    CCTV_HOST: str = ""
    CCTV_USERNAME: str = ""
    CCTV_PASSWORD: str = ""
    CCTV_RTSP_PATH: str = "/Streaming/Channels/101"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def upload_path(self) -> Path:
        return BASE_DIR / self.UPLOAD_DIR

    @property
    def annotated_path(self) -> Path:
        return BASE_DIR / self.ANNOTATED_DIR

    @property
    def camera_media_path(self) -> Path:
        return BASE_DIR / self.CAMERA_MEDIA_DIR

    @property
    def temp_path(self) -> Path:
        return BASE_DIR / self.TEMP_DIR

    @property
    def log_path(self) -> Path:
        return BASE_DIR / self.LOG_DIR

    @property
    def ai_model_path(self) -> Path:
        model_path = Path(self.AI_MODEL_PATH)
        if model_path.is_absolute():
            return model_path
        return (BASE_DIR / model_path).resolve()

    @property
    def frontend_origins(self) -> list[str]:
        return [url.strip() for url in self.FRONTEND_URL.split(",") if url.strip()]


settings = Settings()


def db_connection() -> bool:
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return True
