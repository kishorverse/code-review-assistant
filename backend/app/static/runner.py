"""Run every applicable analyzer concurrently and combine their results.

One tool failing, timing out or not being installed never fails the scan: its
outcome is recorded as a tool run and the other tools' results are kept.
"""

import asyncio
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import structlog

from app.errors import AnalyzerError, ToolUnavailableError
from app.events import EventSink, FindingEvent, ToolEvent
from app.findings import Finding
from app.static.analyzers.bandit import BanditAnalyzer
from app.static.analyzers.detect_secrets import DetectSecretsAnalyzer
from app.static.analyzers.lizard import LizardAnalyzer
from app.static.analyzers.mypy import MypyAnalyzer
from app.static.analyzers.radon import RadonAnalyzer
from app.static.analyzers.ruff import RuffAnalyzer
from app.static.analyzers.vulture import VultureAnalyzer
from app.static.base import (
    AnalysisTarget,
    Analyzer,
    AnalyzerResult,
    FileMetrics,
    ToolRun,
    ToolStatus,
)
from app.static.dedupe import deduplicate
from app.static.evidence import attach_evidence

DEFAULT_TIMEOUT_SECONDS = 120.0

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class StaticAnalysisResult:
    """Combined outcome of all analyzers."""

    findings: list[Finding]
    tool_runs: list[ToolRun]
    metrics: list[FileMetrics]


def default_analyzers() -> list[Analyzer]:
    """The analyzers Margin runs by default."""
    return [
        RuffAnalyzer(),
        BanditAnalyzer(),
        MypyAnalyzer(),
        RadonAnalyzer(),
        VultureAnalyzer(),
        LizardAnalyzer(),
        DetectSecretsAnalyzer(),
    ]


async def run_static_analysis(
    target: AnalysisTarget,
    analyzers: Sequence[Analyzer],
    sink: EventSink,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> StaticAnalysisResult:
    """Run analyzers in parallel, then merge, enrich and order their findings.

    Findings are sorted most severe first, then by file and line, and emitted
    as events once they are final.
    """
    outcomes = await asyncio.gather(
        *(_run_analyzer(analyzer, target, sink, timeout_seconds) for analyzer in analyzers)
    )
    merged = deduplicate(finding for _, result in outcomes for finding in result.findings)
    findings = await asyncio.to_thread(attach_evidence, merged, target.root)
    findings.sort(key=lambda f: (-f.severity.rank, f.file_path, f.start_line, f.rule_id or ""))
    for finding in findings:
        await sink.emit(FindingEvent(finding=finding))
    return StaticAnalysisResult(
        findings=findings,
        tool_runs=[run for run, _ in outcomes],
        metrics=merge_metrics(metric for _, result in outcomes for metric in result.metrics),
    )


def merge_metrics(metrics: Iterable[FileMetrics]) -> list[FileMetrics]:
    """Combine partial metrics for the same file from different tools, sorted by path."""
    combined: dict[str, FileMetrics] = {}
    for metric in metrics:
        existing = combined.get(metric.path)
        if existing is None:
            combined[metric.path] = metric
            continue
        updates = {
            field: value
            for field, value in metric.model_dump(exclude={"path", "functions"}).items()
            if value is not None
        }
        combined[metric.path] = existing.model_copy(
            update={**updates, "functions": [*existing.functions, *metric.functions]}
        )
    return [combined[path] for path in sorted(combined)]


async def _run_analyzer(
    analyzer: Analyzer, target: AnalysisTarget, sink: EventSink, timeout_seconds: float
) -> tuple[ToolRun, AnalyzerResult]:
    if not analyzer.applies_to(target):
        run = ToolRun(
            tool=analyzer.name, status=ToolStatus.SKIPPED, duration_ms=0, message="No files"
        )
        await sink.emit(ToolEvent(tool=run.tool, state=run.status, message=run.message))
        return run, AnalyzerResult()

    await sink.emit(ToolEvent(tool=analyzer.name, state="started"))
    started = time.perf_counter()
    result = AnalyzerResult()
    status, message = ToolStatus.OK, None
    try:
        async with asyncio.timeout(timeout_seconds):
            result = await analyzer.analyze(target)
    except TimeoutError:
        status, message = ToolStatus.TIMED_OUT, f"Stopped after {timeout_seconds:g} seconds"
    except ToolUnavailableError as error:
        status, message = ToolStatus.SKIPPED, str(error)
    except AnalyzerError as error:
        status, message = ToolStatus.FAILED, str(error)
    except Exception:
        # Boundary: an analyzer bug must not take the whole scan down.
        log.exception("analyzer_crashed", tool=analyzer.name)
        status, message = ToolStatus.FAILED, "Unexpected error; see server logs"

    run = ToolRun(
        tool=analyzer.name,
        status=status,
        duration_ms=round((time.perf_counter() - started) * 1000),
        finding_count=len(result.findings),
        message=message,
    )
    await sink.emit(
        ToolEvent(
            tool=run.tool,
            state=run.status,
            finding_count=run.finding_count,
            duration_ms=run.duration_ms,
            message=run.message,
        )
    )
    log.info("analyzer_finished", tool=run.tool, status=run.status, ms=run.duration_ms)
    return run, result
