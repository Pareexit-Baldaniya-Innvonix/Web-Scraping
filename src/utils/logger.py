# ----- library import -----
import os
import logging
from logging import Logger
from logging.config import dictConfig
from typing import Any

# ----- local import -----
from src.classes.Settings import settings
from src.config.constants import LOG_DIR

# ----- unified format -----
_LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

# ----- mapping levels -----
LEVEL_MAP: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

# ----- determine log level based on settings, default is INFO -----
TARGET_LEVEL: int = LEVEL_MAP.get(settings.LOG_LEVEL.upper(), logging.INFO)

# ----- use JSON logs in production, Standard for local dev -----
SELECTED_FORMATTER: str = "json" if settings.ENV == "production" else "standard"

# ----- centralized logging configuration dictionary -----
LOGGING_CONFIG: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": _LOG_FORMAT,
            "datefmt": _DATE_FORMAT,
            "json_ensure_ascii": False,
        },
        "standard": {
            "format": _LOG_FORMAT,
            "datefmt": _DATE_FORMAT,
        },
    },
    "handlers": {
        "console": {
            "level": TARGET_LEVEL,
            "formatter": SELECTED_FORMATTER,
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
        "file": {
            "level": TARGET_LEVEL,
            "formatter": SELECTED_FORMATTER,
            "class": "logging.FileHandler",
            "filename": f"{LOG_DIR}/scraper.log",
            "mode": "a",
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "urllib3": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": TARGET_LEVEL,
    },
}


# ----- initializes the logging configuration -----
def setup_logging() -> None:
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        dictConfig(LOGGING_CONFIG)
    except Exception as error:
        logging.basicConfig(level=logging.INFO)
        logging.error(f"Failed to load LOGGING_CONFIG: {error}")


# ----- returns a logger instance for a specific module -----
def get_logger(name: str) -> Logger:
    return logging.getLogger(name)
