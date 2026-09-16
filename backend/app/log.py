"""Structured logging setup.

Development uses a readable console renderer; production emits one JSON object
per line so logs can be filtered by ``scan_id``, ``stage`` or ``tool``.
"""

import logging

import structlog

from app.config import LogFormat, LogLevel


def configure_logging(level: LogLevel, log_format: LogFormat) -> None:
    """Configure structlog for the whole process.

    Args:
        level: Minimum level that is emitted.
        log_format: ``"json"`` for machine-readable output, ``"console"`` for humans.
    """
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level]),
        # Module-level loggers are created at import time; caching would pin them
        # to whatever configuration existed then.
        cache_logger_on_first_use=False,
    )
