"""Command-line interface for batch scans of local projects and CI pipelines.

Examples::

    margin scan ./my-project
    margin scan project.zip --format json --output report.json
    margin scan src --fail-on high
"""

import asyncio
import json
import sys
import tempfile
from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import IO, Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from app import __version__
from app.config import get_settings
from app.errors import IngestError
from app.events import ScanEvent, StageEvent, ToolEvent
from app.findings import Severity
from app.ingest.storage import ScanStorage, new_scan_id
from app.log import configure_logging
from app.pipeline import ScanResult, ScanSettings, directory_ingest, run_scan, upload_ingest
from app.static.base import ToolStatus
from app.static.runner import default_analyzers

EXIT_FINDINGS_AT_THRESHOLD = 1
EXIT_REJECTED = 2

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
) -> None:
    """Scan a project with the static analyzers and print the findings."""
    configure_logging("WARNING", "console", stream=sys.stderr)
    progress = Console(stderr=True, quiet=quiet)
    settings = ScanSettings()
    with tempfile.TemporaryDirectory(prefix="margin-", ignore_cleanup_errors=True) as temp:
        workspace = ScanStorage(Path(temp)).create(new_scan_id())
        ingest = (
            directory_ingest(path, settings.limits)
            if path.is_dir()
            else upload_ingest(path, path.name, settings.limits)
        )
        analyzers = default_analyzers(get_settings().opengrep_path)
        try:
            result = asyncio.run(
                run_scan(
                    ingest,
                    workspace,
                    ProgressSink(progress),
                    settings=settings,
                    analyzers=analyzers,
                )
            )
        except IngestError as error:
            Console(stderr=True).print(f"[red]Rejected:[/red] {error.message}")
            raise typer.Exit(EXIT_REJECTED) from error

    if output is None:
        _render(result, output_format, Console())
    else:
        with output.open("w", encoding="utf-8") as handle:
            _render(result, output_format, Console(file=handle, width=160, no_color=True))

    if fail_on is not FailOn.NEVER and _has_finding_at_least(result, Severity(fail_on)):
        raise typer.Exit(EXIT_FINDINGS_AT_THRESHOLD)


class ProgressSink:
    """Prints stage and tool progress to standard error."""

    def __init__(self, console: Console) -> None:
        self._console = console

    async def emit(self, event: ScanEvent) -> None:
        """Print a one-line update for stage and completed tool events."""
        if isinstance(event, StageEvent):
            self._console.print(f"[bold]{event.stage.value.capitalize()}[/bold]")
        elif isinstance(event, ToolEvent) and event.state != "started":
            detail = (
                f"{event.finding_count} findings, {event.duration_ms} ms"
                if event.state == ToolStatus.OK
                else event.message or ""
            )
            self._console.print(f"  {event.tool:<15} {event.state:<10} {detail}")


def scan_report(result: ScanResult) -> dict[str, Any]:
    """The JSON document written by ``--format json``. It contains no server paths."""
    findings = result.static.findings
    return {
        "tool": {"name": "margin", "version": __version__},
        "summary": {
            "files_scanned": len(result.ingest.files),
            "files_reviewed": len(result.files),
            "findings": len(findings),
            "by_severity": {s.value: n for s, n in Counter(f.severity for f in findings).items()},
        },
        "skipped_files": [item.model_dump(mode="json") for item in result.ingest.skipped],
        "tool_runs": [run.model_dump(mode="json") for run in result.static.tool_runs],
        "findings": [finding.model_dump(mode="json") for finding in findings],
        "metrics": [metric.model_dump(mode="json") for metric in result.static.metrics],
    }


def _render(result: ScanResult, output_format: OutputFormat, console: Console) -> None:
    if output_format is OutputFormat.JSON:
        _write_raw(console.file, json.dumps(scan_report(result), indent=2) + "\n")
        return
    table = Table(title=f"Margin {__version__}: {len(result.static.findings)} findings")
    for column in ("Severity", "Location", "Rule", "Found by", "Title"):
        table.add_column(column, overflow="fold")
    for finding in result.static.findings:
        table.add_row(
            finding.severity.value,
            f"{finding.file_path}:{finding.start_line}",
            finding.rule_id or "",
            ", ".join(finding.sources),
            finding.title,
        )
    console.print(table)
    counts = Counter(f.severity for f in result.static.findings)
    summary = ", ".join(f"{counts[s]} {s.value}" for s in Severity if counts[s])
    console.print(f"{len(result.ingest.files)} files scanned. {summary or 'No findings.'}")


def _write_raw(stream: IO[str], text: str) -> None:
    stream.write(text)
    stream.flush()


def _has_finding_at_least(result: ScanResult, threshold: Severity) -> bool:
    return any(f.severity.rank >= threshold.rank for f in result.static.findings)
