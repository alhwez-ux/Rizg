import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from app.core.config import Settings

_LOG_PATH = Path("data/logs/rizg.log")
_LOG_MAX_BYTES = 512_000
_LOG_BACKUPS = 2


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


def configure_logging(settings: Settings) -> None:
    """Configure root logging once at application startup."""

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(request_id)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    request_filter = RequestIdFilter()
    stdout = logging.StreamHandler(sys.stdout)
    stdout.setFormatter(formatter)
    stdout.addFilter(request_filter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(stdout)
    rotating = _rotating_handler(formatter, request_filter)
    if rotating is not None:
        root.addHandler(rotating)
    root.setLevel(level)

    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").handlers.clear()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def _rotating_handler(formatter: logging.Formatter, request_filter: logging.Filter) -> RotatingFileHandler | None:
    """Keep a small rotated file. StreamHandler does not retain lines, and this file cannot grow without bound."""

    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            _LOG_PATH,
            maxBytes=_LOG_MAX_BYTES,
            backupCount=_LOG_BACKUPS,
            encoding="utf-8",
            delay=True,
        )
    except OSError:
        return None
    handler.setFormatter(formatter)
    handler.addFilter(request_filter)
    return handler


def log_extra(request_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
    extra: dict[str, Any] = {"request_id": request_id or "-"}
    extra.update(kwargs)
    return extra
