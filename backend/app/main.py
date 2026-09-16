"""FastAPI application factory.

Run the development server from ``backend/`` with::

    uv run uvicorn app.main:create_app --factory --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import health
from app.config import Settings, get_settings
from app.log import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Args:
        settings: Explicit settings, mainly for tests. Defaults to the
            environment-derived settings.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)

    app = FastAPI(title="Margin", version=__version__)
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )
    app.include_router(health.router, prefix="/api")
    return app
