"""Everything a model is shown to review one chunk, with secrets masked.

A context bundles the chunk's code, the static findings inside it (each with a
short id such as ``S1`` that the model's judgements refer back to), the
metrics of its functions and the regions that failed to parse. Code always
comes from a :class:`SourceText`, whose lines are masked for secrets, never
from the chunk's own unmasked rendering.
"""

import json
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from app.findings import Category, Finding
from app.preprocess.chunker import render_numbered, split_lines
from app.preprocess.models import Chunk, LineRange, PreprocessedFile
from app.redaction import SecretIndex, SecretMasker
from app.static.base import FileMetrics

MAX_STATIC_FINDINGS = 40
MAX_MESSAGE_CHARACTERS = 300

FORMATTING_RULE_PREFIXES = ("E1", "E2", "E3", "E5", "W", "I", "Q", "COM")
"""Ruff rules about layout alone. They are reported as they are and never sent to a model."""

STYLE_GUIDES = {
    "python": "PEP 8 and PEP 257",
    "javascript": "widely used JavaScript conventions such as the Airbnb and Google style guides",
    "typescript": "widely used TypeScript conventions such as the Google TypeScript style guide",
    "java": "the Google Java Style Guide",
    "go": "Effective Go and gofmt conventions",
}
DEFAULT_STYLE_GUIDE = "the language's widely used conventions"


@dataclass(frozen=True)
class SourceText:
    """One file's lines with secrets masked, exactly as a model may see them."""

    path: str
    language: str
    lines: list[str]

    def render(self, blocks: Sequence[LineRange]) -> str:
        """Numbered lines for ordered, non-overlapping blocks."""
        return render_numbered(self.lines, blocks)

    def excerpt(self, start: int, end: int, padding: int) -> str:
        """Numbered lines from ``start`` to ``end`` with ``padding`` lines around them."""
        first = max(1, start - padding)
        last = min(len(self.lines), end + padding)
        return self.render([LineRange(start=first, end=max(first, last))])


def load_source(root: Path, file: PreprocessedFile, secrets: SecretIndex) -> SourceText:
    """Read a file and mask its secrets. This is blocking I/O.

    Lines are split exactly as preprocessing split them, so chunk line numbers match.
    """
    raw = root.joinpath(*PurePosixPath(file.path).parts).read_bytes()
    lines = split_lines(raw.decode("utf-8-sig", errors="replace"))
    return SourceText(file.path, file.language, SecretMasker(file.path, secrets).mask_lines(lines))


def is_formatting_only(finding: Finding) -> bool:
    """Whether a finding is about layout alone, which a model has nothing to add to."""
    return "ruff" in finding.sources and (finding.rule_id or "").startswith(
        FORMATTING_RULE_PREFIXES
    )


def findings_in_chunk(chunk: Chunk, findings: Sequence[Finding]) -> list[Finding]:
    """Findings that start inside the chunk body and are worth showing to a model."""
    return [
        finding
        for finding in findings
        if finding.file_path == chunk.file_path
        and chunk.lines.start <= finding.start_line <= chunk.lines.end
        and not is_formatting_only(finding)
    ]


def describe_project(files: Sequence[PreprocessedFile]) -> str:
    """A one-line project description with names and counts only, never code."""
    languages = Counter(file.language for file in files)
    breakdown = ", ".join(f"{language} {count}" for language, count in languages.most_common())
    noun = "file" if len(files) == 1 else "files"
    return f"{len(files)} reviewable {noun} ({breakdown})" if files else "no reviewable files"


@dataclass(frozen=True)
class ReviewContext:
    """A chunk ready to review.

    Attributes:
        chunk: The chunk under review.
        source: The chunk's file with secrets masked.
        static_findings: Static findings shown to the model, by the id it was given.
        prompt_values: Values for the review and style prompt templates.
    """

    chunk: Chunk
    source: SourceText
    static_findings: dict[str, Finding]
    prompt_values: dict[str, str]


def build_context(
    chunk: Chunk,
    source: SourceText,
    findings: Sequence[Finding],
    metrics: FileMetrics | None,
    project_summary: str,
    include: Callable[[Finding], bool],
) -> ReviewContext:
    """Assemble what a model sees for one chunk.

    Args:
        chunk: The chunk to review.
        source: Its file, masked.
        findings: Static findings for the scan; those inside the chunk are shown.
        metrics: The file's metrics, if any tool measured it.
        project_summary: From :func:`describe_project`.
        include: Which of the chunk's static findings this task should see.
    """
    shown = [finding for finding in findings_in_chunk(chunk, findings) if include(finding)]
    shown.sort(key=lambda f: (-f.severity.rank, f.start_line))
    by_id = {f"S{number}": finding for number, finding in enumerate(shown[:MAX_STATIC_FINDINGS], 1)}
    values = {
        "project_summary": project_summary,
        "file_path": chunk.file_path,
        "language": chunk.language,
        "style_guide": STYLE_GUIDES.get(chunk.language, DEFAULT_STYLE_GUIDE),
        "metrics": _metrics_text(chunk, metrics),
        "static_findings": _findings_text(by_id),
        "partial_regions": _ranges_text(chunk.partial_regions),
        "code": source.render([*chunk.context, chunk.lines]),
    }
    return ReviewContext(chunk, source, by_id, values)


def for_review(finding: Finding) -> bool:
    """The review task judges everything except pure style findings."""
    return finding.category is not Category.STYLE


def for_style(finding: Finding) -> bool:
    """The style task sees style findings, so it does not report them again."""
    return finding.category in (Category.STYLE, Category.MAINTAINABILITY)


def _findings_text(by_id: dict[str, Finding]) -> str:
    if not by_id:
        return "none"
    return "\n".join(
        json.dumps(
            {
                "id": static_id,
                "tool": "+".join(finding.sources),
                "rule": finding.rule_id,
                "category": finding.category.value,
                "severity": finding.severity.value,
                "lines": _range_text(finding.start_line, finding.end_line),
                "message": finding.message[:MAX_MESSAGE_CHARACTERS],
            }
        )
        for static_id, finding in by_id.items()
    )


def _metrics_text(chunk: Chunk, metrics: FileMetrics | None) -> str:
    if metrics is None:
        return "none"
    functions = [
        json.dumps(
            {
                "function": function.name,
                "lines": _range_text(function.start_line, function.end_line),
                "cyclomatic_complexity": function.cyclomatic_complexity,
                "lines_of_code": function.lines_of_code,
                "parameters": function.parameters,
            }
        )
        for function in metrics.functions
        if function.start_line <= chunk.lines.end and chunk.lines.start <= function.end_line
    ]
    if metrics.maintainability_index is not None:
        functions.append(f"file maintainability index: {metrics.maintainability_index:.1f}")
    return "\n".join(functions) or "none"


def _ranges_text(ranges: Sequence[LineRange]) -> str:
    return ", ".join(_range_text(r.start, r.end) for r in ranges) or "none"


def _range_text(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}-{end}"
