import logging
import os
import sys
from typing import Any

try:
    import structlog
except ImportError:  # pragma: no cover - exercised only in minimal local envs
    structlog = None


def configure_logging() -> None:
    """Configure structured logs once for CLI scripts and the Telegram bot."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level, logging.INFO)
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
        level=level,
    )

    if structlog is None:
        return

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            level
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    if structlog is not None:
        return structlog.get_logger(name)
    return _FallbackStructuredLogger(logging.getLogger(name))


class _FallbackStructuredLogger:
    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def info(self, event: str, **kwargs: Any) -> None:
        self._logger.info(event, extra={"event": event, **kwargs})

    def warning(self, event: str, **kwargs: Any) -> None:
        self._logger.warning(event, extra={"event": event, **kwargs})

    def error(self, event: str, **kwargs: Any) -> None:
        self._logger.error(event, extra={"event": event, **kwargs})

    def exception(self, event: str, **kwargs: Any) -> None:
        self._logger.exception(event, extra={"event": event, **kwargs})
