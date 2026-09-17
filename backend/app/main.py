"""FastAPI application factory.

Run the development server from ``backend/`` with::

    uv run uvicorn app.main:create_app --factory --reload
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import timedelta
from functools import partial

import httpx
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import health, providers, scans
from app.api.upload_limit import UploadSizeLimit
from app.config import Settings, get_settings
from app.errors import (
    FileNotInScanError,
    IngestError,
    ScanNotFinishedError,
    ScanNotFoundError,
    ScanQueueFullError,
    UnknownFindingError,
    UploadTooLargeError,
)
from app.ingest.models import IngestLimits
from app.ingest.storage import ScanStorage
from app.llm.factory import build_router
from app.log import configure_logging
from app.scans.manager import AnalyzerFactory, ScanManager
from app.static.runner import default_analyzers

PURGE_INTERVAL_SECONDS = 15 * 60
RETRY_AFTER_SECONDS = 30
MULTIPART_OVERHEAD_BYTES = 64 * 1024
"""Room for multipart boundaries and form fields around an upload of the maximum size."""

log = structlog.get_logger(__name__)


def create_app(
    settings: Settings | None = None, *, analyzers: AnalyzerFactory | None = None
) -> FastAPI:
    """Build the application.

    Args:
        settings: Explicit settings, mainly for tests. Defaults to the
            environment-derived settings.
        analyzers: Builds the analyzers for each scan; tests pass fast fakes.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)
    analyzers = analyzers or partial(default_analyzers, settings.opengrep_path)

    app = FastAPI(title="Margin", version=__version__, lifespan=_lifespan(settings, analyzers))
    app.state.settings = settings
    app.add_middleware(
        UploadSizeLimit,
        path="/api/scans",
        max_bytes=IngestLimits().max_archive_bytes + MULTIPART_OVERHEAD_BYTES,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )
    for route_module in (health, providers, scans):
        app.include_router(route_module.router, prefix="/api")
    _add_error_handlers(app)
    return app


def _lifespan(
    settings: Settings, analyzers: AnalyzerFactory
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient() as client:
            llm_router = build_router(settings, client)
            manager = ScanManager(
                ScanStorage(settings.storage_dir),
                router=llm_router,
                analyzers=analyzers,
                retention=timedelta(hours=settings.retention_hours),
                max_concurrent=settings.max_concurrent_scans,
            )
            app.state.llm_router = llm_router
            app.state.scans = manager
            purger = asyncio.create_task(_purge_periodically(manager))
            try:
                yield
            finally:
                purger.cancel()
                await asyncio.gather(purger, return_exceptions=True)
                await manager.close()

    return lifespan


async def _purge_periodically(manager: ScanManager) -> None:
    while True:
        try:
            await manager.purge_expired()
        except Exception:
            # Boundary: a failed purge is retried on the next round rather than stopping it.
            log.exception("purge_failed")
        await asyncio.sleep(PURGE_INTERVAL_SECONDS)


def _add_error_handlers(app: FastAPI) -> None:
    def detail(status_code: int, message: str) -> JSONResponse:
        return JSONResponse({"detail": message}, status_code=status_code)

    async def not_found(request: Request, error: Exception) -> JSONResponse:
        return detail(404, "Scan not found" if isinstance(error, ScanNotFoundError) else str(error))

    async def not_finished(request: Request, error: Exception) -> JSONResponse:
        return detail(409, str(error))

    async def too_large(request: Request, error: Exception) -> JSONResponse:
        return detail(413, str(error))

    async def busy(request: Request, error: Exception) -> JSONResponse:
        response = detail(503, str(error))
        response.headers["Retry-After"] = str(RETRY_AFTER_SECONDS)
        return response

    async def rejected(request: Request, error: Exception) -> JSONResponse:
        if not isinstance(error, IngestError):
            return detail(400, str(error))
        return JSONResponse({"detail": error.message, "reason": error.reason.value}, 400)

    for error_type in (ScanNotFoundError, FileNotInScanError, UnknownFindingError):
        app.add_exception_handler(error_type, not_found)
    app.add_exception_handler(ScanNotFinishedError, not_finished)
    app.add_exception_handler(UploadTooLargeError, too_large)
    app.add_exception_handler(ScanQueueFullError, busy)
    app.add_exception_handler(IngestError, rejected)
