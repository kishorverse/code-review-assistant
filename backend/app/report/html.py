"""A standalone HTML report: one file with inline styles and no external requests.

The template only lays things out; everything it shows is prepared here. All
values are HTML-escaped, since findings carry code and model output.
"""

import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.findings import Finding, FindingStatus, Severity
from app.llm.models import CallRecord, CallStatus
from app.report.document import Report
from app.review.merge import is_unconfident

TEMPLATES_DIR = Path(__file__).parent / "templates"
SENT_STATUSES = frozenset(
    {CallStatus.OK, CallStatus.REJECTED, CallStatus.UNAVAILABLE, CallStatus.RATE_LIMITED}
)
"""Attempts in which code was sent to the provider, whatever the outcome."""


@dataclass(frozen=True)
class FileSection:
    """Reported findings in one file, most severe first."""

    path: str
    findings: list[Finding]


@dataclass(frozen=True)
class HiddenFinding:
    """A finding kept out of the counts, with why."""

    finding: Finding
    reason: str


@dataclass(frozen=True)
class ProviderUsage:
    """How one provider was used during review."""

    provider: str
    models: list[str]
    answered: int
    failed: int
    p50_ms: int
    p95_ms: int
    files: list[str]


@dataclass(frozen=True)
class MetricsRow:
    """Size and complexity of one file."""

    path: str
    lines: int | None
    source_lines: int | None
    maintainability_index: float | None
    max_complexity: int | None


def render_html(report: Report) -> str:
    """The report as a standalone HTML page."""
    environment = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR, encoding="utf-8"),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return environment.get_template("report.html.j2").render(
        report=report,
        severities=[severity.value for severity in Severity],
        sections=file_sections(report.reported_findings()),
        top_files=top_files(report.reported_findings()),
        hidden=hidden_findings(report),
        usage=provider_usage(report.review.calls if report.review else []),
        metrics=metrics_rows(report),
    )


def file_sections(findings: Sequence[Finding]) -> list[FileSection]:
    """Findings grouped by file, files in path order, findings most severe first."""
    by_file: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        by_file[finding.file_path].append(finding)
    return [
        FileSection(path, sorted(items, key=lambda f: (-f.severity.rank, f.start_line)))
        for path, items in sorted(by_file.items())
    ]


def top_files(findings: Sequence[Finding], limit: int = 5) -> list[tuple[str, int]]:
    """The files with the most reported findings."""
    return Counter(finding.file_path for finding in findings).most_common(limit)


def hidden_findings(report: Report) -> list[HiddenFinding]:
    """Findings left out of the counts, with the reason for each."""
    hidden = []
    for finding in report.findings:
        if finding.status is FindingStatus.DISMISSED_BY_AI:
            hidden.append(HiddenFinding(finding, finding.ai_note or "Dismissed by AI review."))
        elif finding.status is FindingStatus.REJECTED:
            hidden.append(HiddenFinding(finding, "Rejected by a reviewer."))
        elif is_unconfident(finding, report.min_confidence):
            reason = f"AI confidence {finding.confidence:.2f} is below {report.min_confidence:g}."
            hidden.append(HiddenFinding(finding, reason))
    return hidden


def provider_usage(calls: Sequence[CallRecord]) -> list[ProviderUsage]:
    """Per provider: answers, failures, latency and the files whose code it received."""
    by_provider: dict[str, list[CallRecord]] = defaultdict(list)
    for call in calls:
        if call.status is not CallStatus.SKIPPED and call.status is not CallStatus.CACHED:
            by_provider[call.provider].append(call)
    usage = []
    for provider, records in sorted(by_provider.items()):
        latencies = sorted(r.latency_ms for r in records if r.status is CallStatus.OK)
        usage.append(
            ProviderUsage(
                provider=provider,
                models=sorted({r.model for r in records}),
                answered=sum(r.status is CallStatus.OK for r in records),
                failed=sum(r.status is not CallStatus.OK for r in records),
                p50_ms=percentile(latencies, 50),
                p95_ms=percentile(latencies, 95),
                files=sorted(
                    {r.file_path for r in records if r.file_path and r.status in SENT_STATUSES}
                ),
            )
        )
    return usage


def percentile(values: Sequence[int], percent: int) -> int:
    """Nearest-rank percentile of sorted values, or 0 when there are none."""
    if not values:
        return 0
    rank = max(1, math.ceil(percent / 100 * len(values)))
    return values[rank - 1]


def metrics_rows(report: Report) -> list[MetricsRow]:
    """One row per reviewed file."""
    measured = {entry.path: entry for entry in report.metrics}
    rows = []
    for file in report.files:
        entry = measured.get(file.path)
        complexities = [f.cyclomatic_complexity for f in entry.functions] if entry else []
        rows.append(
            MetricsRow(
                path=file.path,
                lines=entry.lines if entry and entry.lines is not None else file.lines,
                source_lines=entry.source_lines if entry else None,
                maintainability_index=entry.maintainability_index if entry else None,
                max_complexity=max(complexities, default=None),
            )
        )
    return rows
