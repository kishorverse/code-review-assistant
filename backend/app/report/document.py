"""The report of one scan: the single document behind CLI output, the API and every export.

It holds what a reader needs (counts, the quality score, findings with their
evidence, metrics and model-call provenance) and nothing else: no server paths
and no file contents beyond each finding's evidence. Counts and the score are
always derived from the findings, so a reviewer's decision on a finding updates
them consistently.
"""

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt

from app import __version__
from app.errors import UnknownFindingError
from app.findings import Finding, FindingStatus
from app.ingest.models import SkippedFile
from app.llm.models import CallRecord
from app.pipeline import ScanResult
from app.report.score import QualityScore, quality_score
from app.review.answers import ReviewSummary
from app.review.merge import REPORTED_STATUSES, is_reported, is_unconfident
from app.review.planner import Depth
from app.static.base import FileMetrics, ToolRun

REVIEWER_STATUSES = frozenset({FindingStatus.OPEN, FindingStatus.ACCEPTED, FindingStatus.REJECTED})
"""Statuses a person may set on a finding. ``open`` restores a dismissed or rejected finding."""


class ToolInfo(BaseModel):
    """What produced the report."""

    model_config = ConfigDict(frozen=True)

    name: str = "margin"
    version: str = __version__


class ReviewedFile(BaseModel):
    """A file that was parsed and could be reviewed."""

    model_config = ConfigDict(frozen=True)

    path: str
    language: str
    lines: NonNegativeInt


class NotReported(BaseModel):
    """Findings kept in the report but left out of its counts, by reason."""

    model_config = ConfigDict(frozen=True, json_schema_serialization_defaults_required=True)

    dismissed_by_ai: NonNegativeInt = 0
    rejected: NonNegativeInt = 0
    below_min_confidence: NonNegativeInt = 0


class ReportCounts(BaseModel):
    """Headline numbers. ``findings`` and the breakdowns count reported findings only."""

    model_config = ConfigDict(frozen=True, json_schema_serialization_defaults_required=True)

    files_scanned: NonNegativeInt
    files_reviewed: NonNegativeInt
    findings: NonNegativeInt
    by_severity: dict[str, int]
    by_category: dict[str, int]
    not_reported: NotReported


class ReviewSection(BaseModel):
    """What LLM review did, when it ran."""

    model_config = ConfigDict(frozen=True)

    depth: Depth
    summary: ReviewSummary | None
    stats: dict[str, int]
    prompt_versions: dict[str, str]
    calls: list[CallRecord]


class Report(BaseModel):
    """Everything a scan found, ready to render or export."""

    model_config = ConfigDict(frozen=True)

    tool: ToolInfo = Field(default_factory=ToolInfo)
    source: str
    generated_at: datetime
    min_confidence: float = Field(ge=0.0, le=1.0)
    summary: ReportCounts
    score: QualityScore
    scanned_files: list[str]
    files: list[ReviewedFile]
    skipped_files: list[SkippedFile]
    tool_runs: list[ToolRun]
    review: ReviewSection | None
    findings: list[Finding]
    metrics: list[FileMetrics]

    def reported_findings(self) -> list[Finding]:
        """Findings in the default report, in report order."""
        return [f for f in self.findings if is_reported(f, self.min_confidence)]


def build_report(
    result: ScanResult, *, source: str, min_confidence: float, generated_at: datetime
) -> Report:
    """Assemble the report of a finished scan.

    Args:
        result: The scan's result.
        source: What was scanned, as the user named it: a directory or file name.
        min_confidence: AI-only findings below this are kept but not reported.
        generated_at: When the report was made, timezone-aware.
    """
    files = [
        ReviewedFile(path=file.path, language=file.language, lines=file.line_count)
        for file in result.files
    ]
    review = None
    if result.review is not None:
        review = ReviewSection(
            depth=result.review.depth,
            summary=result.review.summary,
            stats=asdict(result.review.stats),
            prompt_versions=result.review.prompt_versions,
            calls=result.review.calls,
        )
    return Report(
        source=source,
        generated_at=generated_at,
        min_confidence=min_confidence,
        summary=count_findings(
            result.findings, len(result.ingest.files), len(files), min_confidence
        ),
        score=score_findings(result.findings, files, result.static.metrics, min_confidence),
        scanned_files=result.ingest.files,
        files=files,
        skipped_files=result.ingest.skipped,
        tool_runs=result.static.tool_runs,
        review=review,
        findings=result.findings,
        metrics=result.static.metrics,
    )


def set_finding_status(report: Report, finding_id: str, status: FindingStatus) -> Report:
    """Record a reviewer's decision on a finding and update the counts and score.

    Raises:
        UnknownFindingError: If the report has no such finding.
        ValueError: If ``status`` is not one a reviewer may set.
    """
    if status not in REVIEWER_STATUSES:
        raise ValueError(f"a reviewer cannot set status {status.value!r}")
    if not any(finding.id == finding_id for finding in report.findings):
        raise UnknownFindingError(f"No finding {finding_id[:40]!r} in this report")
    findings = [
        finding.model_copy(update={"status": status}) if finding.id == finding_id else finding
        for finding in report.findings
    ]
    counts = report.summary
    return report.model_copy(
        update={
            "findings": findings,
            "summary": count_findings(
                findings, counts.files_scanned, counts.files_reviewed, report.min_confidence
            ),
            "score": score_findings(findings, report.files, report.metrics, report.min_confidence),
        }
    )


def count_findings(
    findings: Sequence[Finding], files_scanned: int, files_reviewed: int, min_confidence: float
) -> ReportCounts:
    """Headline counts for a set of findings."""
    reported = [finding for finding in findings if is_reported(finding, min_confidence)]
    return ReportCounts(
        files_scanned=files_scanned,
        files_reviewed=files_reviewed,
        findings=len(reported),
        by_severity=_counts(finding.severity.value for finding in reported),
        by_category=_counts(finding.category.value for finding in reported),
        not_reported=NotReported(
            dismissed_by_ai=sum(f.status is FindingStatus.DISMISSED_BY_AI for f in findings),
            rejected=sum(f.status is FindingStatus.REJECTED for f in findings),
            below_min_confidence=sum(
                f.status in REPORTED_STATUSES and is_unconfident(f, min_confidence)
                for f in findings
            ),
        ),
    )


def score_findings(
    findings: Sequence[Finding],
    files: Sequence[ReviewedFile],
    metrics: Sequence[FileMetrics],
    min_confidence: float,
) -> QualityScore:
    """The quality score of the reported findings.

    Lines of code come from measured source lines where a tool measured them, and
    from the file's line count otherwise.
    """
    reported = [finding for finding in findings if is_reported(finding, min_confidence)]
    measured = {entry.path: entry.source_lines for entry in metrics}
    source_lines = sum(measured.get(file.path) or file.lines for file in files)
    return quality_score(reported, source_lines, metrics)


def _counts(values: Iterable[str]) -> dict[str, int]:
    return dict(Counter(values).most_common())
