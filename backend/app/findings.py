"""The finding schema shared by static analyzers, LLM review, verification and reports.

Every analyzer and model output is normalized into :class:`Finding`, so later
stages never need to know which tool produced an issue.
"""

import uuid
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator

MAX_TITLE_LENGTH = 80

REDACTED_EVIDENCE = "[redacted: possible secret]"
"""Evidence placeholder for findings about secrets, so the secret itself is never shown."""


class Severity(StrEnum):
    """How urgently an issue needs attention, most severe first."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def rank(self) -> int:
        """Sort key where a larger number is more severe."""
        return _SEVERITY_RANK[self]


_SEVERITY_RANK = {
    Severity.CRITICAL: 4,
    Severity.HIGH: 3,
    Severity.MEDIUM: 2,
    Severity.LOW: 1,
    Severity.INFO: 0,
}


class Category(StrEnum):
    """What kind of issue a finding describes."""

    BUG = "bug"
    SECURITY = "security"
    STYLE = "style"
    PERFORMANCE = "performance"
    MAINTAINABILITY = "maintainability"
    TYPING = "typing"


class FindingStatus(StrEnum):
    """Where a finding stands in review."""

    OPEN = "open"
    DISMISSED_BY_AI = "dismissed_by_ai"
    NEEDS_REVIEW = "needs_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class Finding(BaseModel):
    """One issue at one location.

    Attributes:
        id: Unique id.
        file_path: POSIX path relative to the upload root.
        start_line: First affected line, 1-based.
        end_line: Last affected line, inclusive.
        start_column: 1-based column where the issue starts, when the tool reports it.
        end_column: 1-based column where the issue ends, when the tool reports it.
        category: Kind of issue.
        severity: How urgent it is.
        title: One-line summary of at most 80 characters.
        message: What is wrong.
        rationale: Why it matters; filled in by LLM review.
        evidence: The offending code. Never contains a detected secret.
        rule_id: The producing tool's rule identifier, such as ``F401`` or ``B602``.
        sources: Tools or models that reported this issue.
        confidence: 0 to 1; deterministic rules report 1.0.
        status: Review state.
        cwe: CWE identifier such as ``CWE-78``, when known.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    file_path: str
    start_line: PositiveInt
    end_line: PositiveInt
    start_column: PositiveInt | None = None
    end_column: PositiveInt | None = None
    category: Category
    severity: Severity
    title: str = Field(max_length=MAX_TITLE_LENGTH)
    message: str
    rationale: str | None = None
    evidence: str | None = None
    rule_id: str | None = None
    sources: list[str] = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: FindingStatus = FindingStatus.OPEN
    cwe: str | None = Field(default=None, pattern=r"^CWE-\d+$")

    @model_validator(mode="after")
    def _end_not_before_start(self) -> Self:
        if self.end_line < self.start_line:
            raise ValueError("end_line must not be before start_line")
        return self


def shorten_title(text: str) -> str:
    """Reduce a message to a single-line title of at most 80 characters."""
    first_line = " ".join(text.split())
    if len(first_line) <= MAX_TITLE_LENGTH:
        return first_line
    return first_line[: MAX_TITLE_LENGTH - 1].rstrip() + "…"
