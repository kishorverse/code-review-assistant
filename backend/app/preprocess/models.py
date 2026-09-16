"""Data shared by the preprocessing steps."""

from collections.abc import Iterable
from typing import Self

from pydantic import BaseModel, ConfigDict, PositiveInt, model_validator

from app.languages.base import SupportLevel


class LineRange(BaseModel):
    """An inclusive range of 1-based line numbers, as editors and findings show them."""

    model_config = ConfigDict(frozen=True)

    start: PositiveInt
    end: PositiveInt

    @model_validator(mode="after")
    def _end_not_before_start(self) -> Self:
        if self.end < self.start:
            raise ValueError(f"end ({self.end}) is before start ({self.start})")
        return self

    @property
    def length(self) -> int:
        """Number of lines in the range."""
        return self.end - self.start + 1

    def overlaps(self, other: "LineRange") -> bool:
        """Whether the two ranges share at least one line."""
        return self.start <= other.end and other.start <= self.end

    def intersection(self, other: "LineRange") -> "LineRange | None":
        """The lines both ranges share, if any."""
        if not self.overlaps(other):
            return None
        return LineRange(start=max(self.start, other.start), end=min(self.end, other.end))

    def without(self, other: "LineRange") -> list["LineRange"]:
        """The parts of this range that lie outside ``other``."""
        if not self.overlaps(other):
            return [self]
        parts: list[LineRange] = []
        if self.start < other.start:
            parts.append(LineRange(start=self.start, end=other.start - 1))
        if self.end > other.end:
            parts.append(LineRange(start=other.end + 1, end=self.end))
        return parts


def merge_ranges(ranges: Iterable[LineRange]) -> list[LineRange]:
    """Sort ranges and merge those that overlap or touch."""
    merged: list[LineRange] = []
    for current in sorted(ranges, key=lambda item: item.start):
        if merged and current.start <= merged[-1].end + 1:
            last = merged[-1]
            merged[-1] = LineRange(start=last.start, end=max(last.end, current.end))
        else:
            merged.append(current)
    return merged


class ChunkingConfig(BaseModel):
    """Size limits for review chunks.

    Attributes:
        target_lines: Small neighboring units are packed together up to this size,
            which saves LLM calls.
        max_lines: No chunk body is ever longer than this.
        max_context_lines: Most header and signature lines shown above a chunk.
    """

    model_config = ConfigDict(frozen=True)

    target_lines: PositiveInt = 250
    max_lines: PositiveInt = 500
    max_context_lines: PositiveInt = 40

    @model_validator(mode="after")
    def _target_within_max(self) -> Self:
        if self.target_lines > self.max_lines:
            raise ValueError("target_lines must not exceed max_lines")
        return self


class Chunk(BaseModel):
    """A self-contained piece of a file, ready to be reviewed.

    Attributes:
        file_path: POSIX path relative to the upload root.
        language: Adapter name.
        index: Position of the chunk within its file, starting at 0.
        lines: The lines under review.
        context: Lines shown above the body for orientation (imports, enclosing
            signatures). They are never part of ``lines``.
        partial_regions: Lines inside the body that failed to parse.
        numbered_code: Context and body, each line prefixed with its real line number.
    """

    model_config = ConfigDict(frozen=True)

    file_path: str
    language: str
    index: int
    lines: LineRange
    context: list[LineRange]
    partial_regions: list[LineRange]
    numbered_code: str


class PreprocessedFile(BaseModel):
    """One source file after detection, parsing and chunking."""

    model_config = ConfigDict(frozen=True)

    path: str
    language: str
    support: SupportLevel
    line_count: int
    partial_regions: list[LineRange]
    chunks: list[Chunk]
