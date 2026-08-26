from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


class LoggerWriter:
    def __init__(self, logger: logging.Logger, level: int) -> None:
        self.logger = logger
        self.level = level
        self.buffer = ""

    def write(self, message: str) -> int:
        self.buffer += message
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line.strip():
                self.logger.log(self.level, line.rstrip())
        return len(message)

    def flush(self) -> None:
        if self.buffer.strip():
            self.logger.log(self.level, self.buffer.rstrip())
        self.buffer = ""

    def isatty(self) -> bool:
        return False


def configure_logging(log_file: Path) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("entok_vision_lite")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=4,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    )
    logger.addHandler(handler)
    logger.propagate = False

    if sys.stdout is None:
        sys.stdout = LoggerWriter(logger, logging.INFO)  # type: ignore[assignment]
    if sys.stderr is None:
        sys.stderr = LoggerWriter(logger, logging.ERROR)  # type: ignore[assignment]
    return logger
