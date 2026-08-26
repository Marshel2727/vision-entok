import logging
from logging.handlers import RotatingFileHandler

from app.config import settings


def configure_logging() -> None:
    settings.log_path.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL.upper())
    if any(isinstance(handler, RotatingFileHandler) for handler in root.handlers):
        return
    handler = RotatingFileHandler(
        settings.log_path / "deteksi_entok.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)
