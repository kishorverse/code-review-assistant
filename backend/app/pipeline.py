"""The scan pipeline: ingest, preprocess, then static analysis.

The same pipeline serves the CLI (batch) and the web API (interactive); only
the ingest step and the event sink differ. LLM review and verification are
added as further stages.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from app.events import EventSink, ScanStage, StageEvent
from app.ingest.directory import ingest_directory
from app.ingest.models import IngestLimits, IngestResult
from app.ingest.storage import ScanWorkspace
from app.ingest.upload import ingest_upload
from app.languages.registry import LanguageRegistry, default_registry
from app.preprocess.models import ChunkingConfig, PreprocessedFile
from app.preprocess.source_file import preprocess_file
from app.static.base import AnalysisTarget, Analyzer
from app.static.runner import (
    DEFAULT_TIMEOUT_SECONDS,
    StaticAnalysisResult,
    default_analyzers,
    run_static_analysis,
)

PREPROCESS_CONCURRENCY = 4

Ingest = Callable[[Path], IngestResult]
"""Fills the given source directory and describes what was extracted."""


@dataclass(frozen=True)
class ScanSettings:
    """Tunable limits for one scan."""

    limits: IngestLimits = field(default_factory=IngestLimits)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    tool_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class ScanResult:
    """Everything a scan produced."""

    ingest: IngestResult
    files: list[PreprocessedFile]
    static: StaticAnalysisResult
    stage_durations_ms: dict[ScanStage, int]


async def run_scan(
    ingest: Ingest,
    workspace: ScanWorkspace,
    sink: EventSink,
    *,
    settings: ScanSettings | None = None,
    registry: LanguageRegistry | None = None,
    analyzers: list[Analyzer] | None = None,
) -> ScanResult:
    """Run every stage of a scan inside an existing workspace.

    Raises:
        IngestError: If the upload or directory is rejected.
    """
    settings = settings or ScanSettings()
    registry = registry or default_registry()
    analyzers = analyzers if analyzers is not None else default_analyzers()
    durations: dict[ScanStage, int] = {}

    async with _stage(ScanStage.INGESTING, sink, durations):
        ingested = await asyncio.to_thread(ingest, workspace.source_dir)
    async with _stage(ScanStage.PREPROCESSING, sink, durations):
        files = await _preprocess_all(ingested, registry, settings.chunking)
    async with _stage(ScanStage.ANALYZING, sink, durations):
        target = AnalysisTarget(
            root=ingested.root, files=tuple(ingested.files), scratch=workspace.scratch_dir
        )
        static = await run_static_analysis(target, analyzers, sink, settings.tool_timeout_seconds)
    await sink.emit(StageEvent(stage=ScanStage.DONE))
    return ScanResult(ingest=ingested, files=files, static=static, stage_durations_ms=durations)


def upload_ingest(upload: Path, filename: str, limits: IngestLimits) -> Ingest:
    """Ingest step for an uploaded file or ``.zip``."""
    return partial(ingest_upload, upload, filename, limits=limits)


def directory_ingest(project: Path, limits: IngestLimits) -> Ingest:
    """Ingest step for a local project directory."""
    return partial(ingest_directory, project, limits=limits)


async def _preprocess_all(
    ingested: IngestResult, registry: LanguageRegistry, chunking: ChunkingConfig
) -> list[PreprocessedFile]:
    semaphore = asyncio.Semaphore(PREPROCESS_CONCURRENCY)

    async def one(path: str) -> PreprocessedFile | None:
        async with semaphore:
            return await asyncio.to_thread(preprocess_file, ingested.root, path, registry, chunking)

    results = await asyncio.gather(*(one(path) for path in ingested.files))
    return [result for result in results if result is not None]


@asynccontextmanager
async def _stage(
    stage: ScanStage, sink: EventSink, durations: dict[ScanStage, int]
) -> AsyncIterator[None]:
    """Emit a stage event on entry and record the stage's duration on exit."""
    await sink.emit(StageEvent(stage=stage))
    started = time.perf_counter()
    try:
        yield
    finally:
        durations[stage] = round((time.perf_counter() - started) * 1000)
