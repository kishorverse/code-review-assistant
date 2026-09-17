"""Decide which chunks a model reviews, within a budget of calls.

Depth trades thoroughness for time and free-tier quota:

- ``static``: no model calls.
- ``quick``: bug and security review of chunks that static analysis or
  complexity flags as risky; only critical AI findings are cross-checked.
- ``standard``: bug, security and style review of every chunk; high and
  critical AI findings are cross-checked.
- ``deep``: as ``standard``, and medium AI findings are cross-checked too.

When a scan has more work than the budget allows, the riskiest chunks are
reviewed first and the plan records how many were left out.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.findings import Finding, Severity
from app.preprocess.models import Chunk, PreprocessedFile
from app.review.context import findings_in_chunk
from app.static.base import FileMetrics

HIGH_COMPLEXITY = 10
DEFAULT_MAX_REVIEW_CALLS = 60
DEFAULT_MIN_CONFIDENCE = 0.6
DEFAULT_CONCURRENCY = 6


class Depth(StrEnum):
    """How thoroughly models review a scan."""

    STATIC = "static"
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


_VERIFY_FROM = {
    Depth.STATIC: None,
    Depth.QUICK: Severity.CRITICAL,
    Depth.STANDARD: Severity.HIGH,
    Depth.DEEP: Severity.MEDIUM,
}


@dataclass(frozen=True)
class ReviewOptions:
    """How a scan uses models.

    Attributes:
        depth: How thoroughly to review.
        allow_external: Whether code may be sent to hosted providers. Without it
            only a local model is used.
        max_review_calls: Most review and style calls in one scan.
        min_confidence: AI-only findings below this are kept but not reported by default.
        concurrency: Most model calls in flight at once for this scan.
    """

    depth: Depth = Depth.STANDARD
    allow_external: bool = False
    max_review_calls: int = DEFAULT_MAX_REVIEW_CALLS
    min_confidence: float = DEFAULT_MIN_CONFIDENCE
    concurrency: int = DEFAULT_CONCURRENCY

    @property
    def verify_from(self) -> Severity | None:
        """The lowest severity of AI finding that a second model checks."""
        return _VERIFY_FROM[self.depth]


@dataclass(frozen=True)
class ReviewPlan:
    """The chunks to review.

    Attributes:
        review: Chunks for bug, security and performance review, riskiest first.
        style: Chunks for style review, riskiest first.
        skipped: Chunks that get no review at all.
    """

    review: list[Chunk]
    style: list[Chunk]
    skipped: int

    @property
    def calls(self) -> int:
        """Review and style calls planned, before any retries or verification."""
        return len(self.review) + len(self.style)


def plan_review(
    files: Sequence[PreprocessedFile],
    findings: Sequence[Finding],
    metrics: Sequence[FileMetrics],
    options: ReviewOptions,
) -> ReviewPlan:
    """Choose chunks for review according to depth, risk and budget."""
    chunks = [chunk for file in files for chunk in file.chunks]
    if options.depth is Depth.STATIC:
        return ReviewPlan(review=[], style=[], skipped=len(chunks))
    metrics_by_path = {entry.path: entry for entry in metrics}
    risk = {
        _key(chunk): risk_score(chunk, findings, metrics_by_path.get(chunk.file_path))
        for chunk in chunks
    }
    thorough = options.depth in (Depth.STANDARD, Depth.DEEP)
    candidates = chunks if thorough else [c for c in chunks if risk[_key(c)] > 0]
    ordered = sorted(candidates, key=lambda c: (-risk[_key(c)], c.file_path, c.index))
    review = ordered[: options.max_review_calls]
    style = ordered[: options.max_review_calls - len(review)] if thorough else []
    return ReviewPlan(review=review, style=style, skipped=len(chunks) - len(review))


def risk_score(chunk: Chunk, findings: Sequence[Finding], metrics: FileMetrics | None) -> int:
    """How much a chunk deserves review.

    Each static finding in the chunk counts by its severity, and each hard-to-follow
    function adds to the score in proportion to its complexity.
    """
    score = sum(finding.severity.rank + 1 for finding in findings_in_chunk(chunk, findings))
    if metrics is not None and metrics.path == chunk.file_path:
        score += sum(
            function.cyclomatic_complexity // 5
            for function in metrics.functions
            if function.cyclomatic_complexity >= HIGH_COMPLEXITY
            and function.start_line <= chunk.lines.end
            and chunk.lines.start <= function.end_line
        )
    return score


def _key(chunk: Chunk) -> tuple[str, int]:
    return chunk.file_path, chunk.index
