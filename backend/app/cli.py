"""Command-line interface for batch scans of local projects and CI pipelines.

Examples::

    margin scan ./my-project
    margin scan project.zip --format json --output report.json
    margin scan src --fail-on high
    margin scan src --depth standard --allow-external
"""

import asyncio
import json
import sys
import tempfile
from collections import Counter
from dataclasses import asdict
from enum import StrEnum
from pathlib import Path
from typing import IO, Annotated, Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from app import __version__
from app.config import Settings, get_settings
from app.errors import ConfigError, IngestError
from app.events import CallEvent, ReviewPlanEvent, ScanEvent, StageEvent, ToolEvent
from app.findings import Finding, FindingStatus, Severity
from app.ingest.storage import ScanStorage, ScanWorkspace, new_scan_id
from app.llm.factory import build_router
from app.llm.models import CallStatus
from app.log import configure_logging
from app.pipeline import (
    Ingest,
    ReviewSetup,
    ScanResult,
    ScanSettings,
    directory_ingest,
    run_scan,
    upload_ingest,
)
from app.review.merge import is_reported
from app.review.planner import DEFAULT_MIN_CONFIDENCE, Depth, ReviewOptions
from app.review.session import ReviewResult
from app.static.base import Analyzer, ToolStatus
from app.static.runner import default_analyzers

EXIT_FINDINGS_AT_THRESHOLD = 1
EXIT_REJECTED = 2
EXIT_CONFIG_ERROR = 3
MAX_CALL_DETAIL = 120

app = typer.Typer(
    help="Margin: code review that shows its work.",
    no_args_is_help=True,
    add_completion=False,
)


class OutputFormat(StrEnum):
    """How scan results are printed."""

    TABLE = "table"
    JSON = "json"


class FailOn(StrEnum):
    """Lowest severity that makes the command exit with a failure code."""

    NEVER = "never"
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@app.callback()
def cli() -> None:
    """Margin: code review that shows its work."""


@app.command()
def scan(
    path: Annotated[
        Path,
        typer.Argument(exists=True, resolve_path=True, help="Project directory, .zip or file."),
    ],
    output_format: Annotated[
        OutputFormat, typer.Option("--format", "-f", help="Output format.")
    ] = OutputFormat.TABLE,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", dir_okay=False, help="Write results to a file."),
    ] = None,
    fail_on: Annotated[
        FailOn, typer.Option(help="Exit with code 1 if a finding is at least this severe.")
    ] = FailOn.NEVER,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Hide progress output.")] = False,
    depth: Annotated[
        Depth,
        typer.Option(help="How thoroughly models review: static (no AI), quick, standard or deep."),
    ] = Depth.STATIC,
    allow_external: Annotated[
        bool,
        typer.Option(
            "--allow-external",
            help="Allow sending code to hosted LLM providers. Detected secrets are masked first.",
        ),
    ] = False,
    min_confidence: Annotated[
        float,
        typer.Option(min=0.0, max=1.0, help="Leave out findings below this confidence."),
    ] = DEFAULT_MIN_CONFIDENCE,
) -> None:
    """Scan a project with the static analyzers, and optionally LLM review, then print findings."""
    configure_logging("WARNING", "console", stream=sys.stderr)
    progress = Console(stderr=True, quiet=quiet)
    errors = Console(stderr=True)
    settings = ScanSettings()
    options = ReviewOptions(
        depth=depth, allow_external=allow_external, min_confidence=min_confidence
    )
    with tempfile.TemporaryDirectory(prefix="margin-", ignore_cleanup_errors=True) as temp:
        workspace = ScanStorage(Path(temp)).create(new_scan_id())
        ingest = (
            directory_ingest(path, settings.limits)
            if path.is_dir()
            else upload_ingest(path, path.name, settings.limits)
        )
        app_settings = get_settings()
        analyzers = default_analyzers(app_settings.opengrep_path)
        try:
            result = asyncio.run(
                _run(ingest, workspace, progress, settings, analyzers, app_settings, options)
            )
        except IngestError as error:
            errors.print(f"[red]Rejected:[/red] {error.message}")
            raise typer.Exit(EXIT_REJECTED) from error
        except ConfigError as error:
            errors.print(f"[red]Configuration error:[/red] {error}")
            raise typer.Exit(EXIT_CONFIG_ERROR) from error

    if output is None:
        _render(result, output_format, Console(), min_confidence)
    else:
        with output.open("w", encoding="utf-8") as handle:
            console = Console(file=handle, width=160, no_color=True)
            _render(result, output_format, console, min_confidence)

    threshold = None if fail_on is FailOn.NEVER else Severity(fail_on)
    if threshold is not None and _has_finding_at_least(result, threshold, min_confidence):
        raise typer.Exit(EXIT_FINDINGS_AT_THRESHOLD)


async def _run(
    ingest: Ingest,
    workspace: ScanWorkspace,
    progress: Console,
    settings: ScanSettings,
    analyzers: list[Analyzer],
    app_settings: Settings,
    options: ReviewOptions,
) -> ScanResult:
    sink = ProgressSink(progress)
    if options.depth is Depth.STATIC:
        return await run_scan(ingest, workspace, sink, settings=settings, analyzers=analyzers)
    async with httpx.AsyncClient() as client:
        router = build_router(app_settings, client)
        _warn_about_providers([status.external for status in router.status()], options, progress)
        return await run_scan(
            ingest,
            workspace,
            sink,
            settings=settings,
            analyzers=analyzers,
            review=ReviewSetup(router, options),
        )


def _warn_about_providers(external: list[bool], options: ReviewOptions, console: Console) -> None:
    if not external:
        console.print(
            "[yellow]No LLM providers are configured.[/yellow] Set API keys and model ids in "
            "backend/.env, or LLM_MODE=mock to try review offline."
        )
    elif not options.allow_external and all(external):
        console.print(
            "[yellow]Only hosted LLM providers are configured.[/yellow] Pass --allow-external "
            "to use them, or set LOCAL_MODEL to review with a local model."
        )


class ProgressSink:
    """Prints stage and tool progress to standard error."""

    def __init__(self, console: Console) -> None:
        self._console = console

    async def emit(self, event: ScanEvent) -> None:
        """Print a one-line update for stages, finished tools, the review plan and failed calls.

        Successful model calls are not printed one by one; the report summarizes them.
        """
        if isinstance(event, StageEvent):
            self._console.print(f"[bold]{event.stage.value.capitalize()}[/bold]")
        elif isinstance(event, ToolEvent) and event.state != "started":
            detail = (
                f"{event.finding_count} findings, {event.duration_ms} ms"
                if event.state == ToolStatus.OK
                else event.message or ""
            )
            self._console.print(f"  {event.tool:<15} {event.state:<10} {detail}")
        elif isinstance(event, ReviewPlanEvent):
            self._console.print(
                f"  {event.review_chunks} chunks to review, {event.style_chunks} for style, "
                f"{event.skipped_chunks} skipped"
            )
        elif isinstance(event, CallEvent) and event.call.status not in _QUIET_CALLS:
            call = event.call
            detail = (call.detail or "")[:MAX_CALL_DETAIL]
            self._console.print(
                f"  {call.provider:<15} {call.status.value:<10} {detail}", markup=False
            )


_QUIET_CALLS = frozenset({CallStatus.OK, CallStatus.CACHED})


def scan_report(
    result: ScanResult, min_confidence: float = DEFAULT_MIN_CONFIDENCE
) -> dict[str, Any]:
    """The JSON document written by ``--format json``. It contains no server paths.

    Every finding is included with its status and confidence; the summary counts
    only the findings reported by default.
    """
    reported = [f for f in result.findings if is_reported(f, min_confidence)]
    return {
        "tool": {"name": "margin", "version": __version__},
        "summary": {
            "files_scanned": len(result.ingest.files),
            "files_reviewed": len(result.files),
            "findings": len(reported),
            "by_severity": {s.value: n for s, n in Counter(f.severity for f in reported).items()},
            "not_reported": _not_reported(result.findings, min_confidence),
        },
        "skipped_files": [item.model_dump(mode="json") for item in result.ingest.skipped],
        "tool_runs": [run.model_dump(mode="json") for run in result.static.tool_runs],
        "review": _review_report(result, min_confidence),
        "findings": [finding.model_dump(mode="json") for finding in result.findings],
        "metrics": [metric.model_dump(mode="json") for metric in result.static.metrics],
    }


def _review_report(result: ScanResult, min_confidence: float) -> dict[str, Any] | None:
    review = result.review
    if review is None:
        return None
    return {
        "depth": review.depth.value,
        "min_confidence": min_confidence,
        "summary": review.summary.model_dump(mode="json") if review.summary else None,
        "stats": asdict(review.stats),
        "prompt_versions": review.prompt_versions,
        "calls": [call.model_dump(mode="json") for call in review.calls],
    }


def _not_reported(findings: list[Finding], min_confidence: float) -> dict[str, int]:
    dismissed = sum(f.status is FindingStatus.DISMISSED_BY_AI for f in findings)
    unconfident = sum(
        f.status is not FindingStatus.DISMISSED_BY_AI and f.confidence < min_confidence
        for f in findings
    )
    return {"dismissed_by_ai": dismissed, "below_min_confidence": unconfident}


def _render(
    result: ScanResult, output_format: OutputFormat, console: Console, min_confidence: float
) -> None:
    if output_format is OutputFormat.JSON:
        report = scan_report(result, min_confidence)
        _write_raw(console.file, json.dumps(report, indent=2) + "\n")
        return
    reported = [f for f in result.findings if is_reported(f, min_confidence)]
    table = Table(title=f"Margin {__version__}: {len(reported)} findings")
    for column in ("Severity", "Location", "Rule", "Found by", "Title"):
        table.add_column(column, overflow="fold")
    for finding in reported:
        found_by = ", ".join(finding.sources)
        if finding.verified_by:
            found_by += f"; verified by {', '.join(finding.verified_by)}"
        title = finding.title
        if finding.status is FindingStatus.NEEDS_REVIEW:
            title += " (needs review)"
        table.add_row(
            finding.severity.value,
            f"{finding.file_path}:{finding.start_line}",
            finding.rule_id or "",
            found_by,
            title,
        )
    console.print(table)
    counts = Counter(f.severity for f in reported)
    summary = ", ".join(f"{counts[s]} {s.value}" for s in Severity if counts[s])
    console.print(f"{len(result.ingest.files)} files scanned. {summary or 'No findings.'}")
    hidden = _not_reported(result.findings, min_confidence)
    if any(hidden.values()):
        console.print(
            f"Not shown: {hidden['dismissed_by_ai']} dismissed by AI review, "
            f"{hidden['below_min_confidence']} below confidence {min_confidence:g}."
        )
    if result.review is not None:
        _render_review(result.review, console)


def _render_review(review: ReviewResult, console: Console) -> None:
    providers = Counter(call.provider for call in review.calls if call.status is CallStatus.OK)
    used = ", ".join(f"{name} {count}" for name, count in providers.most_common()) or "none"
    stats = review.stats
    console.print(
        f"AI review ({review.depth.value}): {stats.chunks_reviewed} chunks reviewed, "
        f"{stats.ai_findings} AI findings, {stats.verified} cross-checked, "
        f"{stats.tasks_failed} tasks without an answer. Calls answered by: {used}.",
        markup=False,
    )
    if review.summary is not None:
        console.print(f"Summary: {review.summary.headline}", markup=False)


def _write_raw(stream: IO[str], text: str) -> None:
    stream.write(text)
    stream.flush()


def _has_finding_at_least(result: ScanResult, threshold: Severity, min_confidence: float) -> bool:
    return any(
        f.severity.rank >= threshold.rank for f in result.findings if is_reported(f, min_confidence)
    )
