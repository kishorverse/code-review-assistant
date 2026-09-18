"""Service settings read from environment variables."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Validated settings for one service instance."""

    port: int
    workers: int
    log_level: str


LOG_LEVELS = ("debug", "info", "warning", "error")


def from_environment(environ: dict[str, str] | None = None) -> Settings:
    """Read settings, rejecting values that would misconfigure the service."""
    env = os.environ if environ is None else environ
    port = int(env.get("PORT", "8080"))
    workers = int(env.get("WORKERS", "2"))
    log_level = env.get("LOG_LEVEL", "info").lower()
    if not 1 <= port <= 65535:
        raise ValueError(f"PORT must be between 1 and 65535, not {port}")
    if workers < 1:
        raise ValueError("WORKERS must be at least 1")
    if log_level not in LOG_LEVELS:
        raise ValueError(f"LOG_LEVEL must be one of {', '.join(LOG_LEVELS)}")
    return Settings(port=port, workers=workers, log_level=log_level)
