"""The scan pipeline: ingest, preprocess, static analysis, then optional LLM review.

The same pipeline serves the CLI (batch) and the web API (interactive); only
the ingest step and the event sink differ. LLM review runs as three further
stages (reviewing, verifying, summarizing) when the scan is given models to
review with and a depth other than static.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from app.events import EventSink, ScanStage, StageEvent
from app.findings import Finding
from app.ingest.directory import ingest_directory
from app.ingest.models import IngestLimits, IngestResult
from app.ingest.storage import ScanWorkspace
from app.ingest.upload import ingest_upload
from app.languages.registry import LanguageRegistry, default_registry
from app.llm.router import Router
from app.preprocess.models import ChunkingConfig, PreprocessedFile
from app.preprocess.source_file import preprocess_file
from app.review.planner import Depth, ReviewOptions
from app.review.session import ReviewResult, ReviewSession
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
class ReviewSetup:
    """The models a scan reviews with, and how."""

    router: Router
    options: ReviewOptions


@dataclass(frozen=True)
class ScanResult:
    """Everything a scan produced.

    Attributes:
        findings: The final findings: static findings, updated by LLM review when it ran.
        review: What LLM review did, when it ran.
    """

    ingest: IngestResult
    files: list[PreprocessedFile]
    static: StaticAnalysisResult
    stage_durations_ms: dict[ScanStage, int]
    findings: list[Finding]
    review: ReviewResult | None = None


async def run_scan(
    ingest: Ingest,
    workspace: ScanWorkspace,
    sink: EventSink,
    *,
    settings: ScanSettings | None = None,
    registry: LanguageRegistry | None = None,
    analyzers: list[Analyzer] | None = None,
    review: ReviewSetup | None = None,
) -> ScanResult:
    """Run every stage of a scan inside an existing workspace.

    Model calls failing never fail the scan: review then keeps the static findings.

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
    reviewed = None
    if review is not None and review.options.depth is not Depth.STATIC:
        reviewed = await _review(review, sink, durations, files, static, ingested.root)
    await sink.emit(StageEvent(stage=ScanStage.DONE))
    return ScanResult(
        ingest=ingested,
        files=files,
        static=static,
        stage_durations_ms=durations,
        findings=reviewed.findings if reviewed else static.findings,
        review=reviewed,
    )


def upload_ingest(upload: Path, filename: str, limits: IngestLimits) -> Ingest:
    """Ingest step for an uploaded file or ``.zip``."""
    return partial(ingest_upload, upload, filename, limits=limits)


def directory_ingest(project: Path, limits: IngestLimits, exclude: Sequence[str] = ()) -> Ingest:
    """Ingest step for a local project directory, leaving out paths matching ``exclude``."""
    return partial(ingest_directory, project, limits=limits, exclude=tuple(exclude))


async def _review(
    setup: ReviewSetup,
    sink: EventSink,
    durations: dict[ScanStage, int],
    files: list[PreprocessedFile],
    static: StaticAnalysisResult,
    root: Path,
) -> ReviewResult:
    session = ReviewSession(setup.router, setup.options, sink)
    async with _stage(ScanStage.REVIEWING, sink, durations):
        findings = await session.review(files, static, root)
    async with _stage(ScanStage.VERIFYING, sink, durations):
        findings = await session.verify(findings)
    async with _stage(ScanStage.SUMMARIZING, sink, durations):
        summary = await session.summarize(files, findings)
    return session.result(findings, summary)


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
