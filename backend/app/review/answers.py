"""Parse model answers into validated review data.

Models do not always follow the requested format exactly: they wrap JSON in
code fences, put reasoning or a sentence before it, write confidence as a
percentage or capitalise enum values. Parsing tolerates those differences.
Each reported issue and judgement is validated on its own, so one malformed
item does not discard the rest of a useful answer, while an answer without
the expected structure is rejected so another provider can be asked.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    ValidationError,
    field_validator,
    model_validator,
)

from app.errors import AnswerFormatError
from app.findings import Category, Severity, shorten_title

_FENCE = re.compile(r"^```[a-zA-Z]*\s*(.*?)\s*```$", re.DOTALL)
_THINKING = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_CWE = re.compile(r"CWE[-_ ]?(\d+)", re.IGNORECASE)
_NULL_WORDS = {"", "null", "none", "n/a"}

ModelT = TypeVar("ModelT", bound=BaseModel)

MAX_STRENGTHS = 3
MAX_RISKS = 5
MAX_NEXT_STEPS = 5


def load_json_object(text: str) -> dict[str, Any]:
    """The JSON object in a model's answer.

    Raises:
        AnswerFormatError: If the answer contains no JSON object.
    """
    candidate = _THINKING.sub("", text).strip()
    fenced = _FENCE.match(candidate)
    if fenced:
        candidate = fenced.group(1)
    try:
        value = json.loads(candidate)
    except ValueError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            raise AnswerFormatError("the answer contains no JSON object") from None
        try:
            value = json.loads(candidate[start : end + 1])
        except ValueError as error:
            raise AnswerFormatError("the answer is not valid JSON") from error
    if not isinstance(value, dict):
        raise AnswerFormatError("the answer is not a JSON object")
    return value


def _normalized_word(value: object) -> object:
    if isinstance(value, str):
        return value.strip().lower().replace(" ", "_").replace("-", "_")
    return value


def _optional_severity(value: object) -> object:
    if value is None or (isinstance(value, str) and value.strip().lower() in _NULL_WORDS):
        return None
    return _normalized_word(value)


def _fraction(value: object) -> object:
    """Accept 85 or "85%" as 0.85."""
    if isinstance(value, str):
        value = value.strip().removesuffix("%")
        try:
            value = float(value)
        except ValueError:
            return value
    if isinstance(value, int | float) and 1 < value <= 100:
        return value / 100
    return value


class ReportedIssue(BaseModel):
    """One issue as a model reported it, before it is checked against the code."""

    model_config = ConfigDict(extra="ignore", frozen=True, str_strip_whitespace=True)

    start_line: PositiveInt
    end_line: PositiveInt
    category: Category
    severity: Severity
    title: str = Field(min_length=1)
    message: str = Field(min_length=1)
    rationale: str | None = None
    evidence: str = Field(min_length=1)
    cwe: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    suggested_change: str | None = None

    _words = field_validator("category", "severity", mode="before")(_normalized_word)
    _confidence = field_validator("confidence", mode="before")(_fraction)

    @field_validator("title")
    @classmethod
    def _short_title(cls, value: str) -> str:
        return shorten_title(value)

    @field_validator("cwe", mode="before")
    @classmethod
    def _cwe_id(cls, value: object) -> str | None:
        match = _CWE.search(str(value)) if value is not None else None
        return f"CWE-{int(match.group(1))}" if match else None

    @model_validator(mode="after")
    def _ordered_lines(self) -> Self:
        if self.end_line < self.start_line:
            raise ValueError("end_line is before start_line")
        return self


class JudgementVerdict(StrEnum):
    """A model's view of a static finding."""

    CONFIRMED = "confirmed"
    FALSE_POSITIVE = "false_positive"
    UNCERTAIN = "uncertain"


class StaticJudgement(BaseModel):
    """A model's judgement of one static finding shown to it."""

    model_config = ConfigDict(extra="ignore", frozen=True, str_strip_whitespace=True)

    static_id: str
    verdict: JudgementVerdict
    reason: str = ""
    adjusted_severity: Severity | None = None

    _verdict = field_validator("verdict", mode="before")(_normalized_word)
    _severity = field_validator("adjusted_severity", mode="before")(_optional_severity)


@dataclass(frozen=True)
class ReviewAnswer:
    """A parsed review or style answer.

    Attributes:
        judgements: Valid judgements of static findings.
        issues: Valid reported issues, not yet checked against the code.
        discarded: Items dropped because they did not match the expected format.
    """

    judgements: list[StaticJudgement]
    issues: list[ReportedIssue]
    discarded: int


def parse_review_answer(text: str) -> ReviewAnswer:
    """Parse a review or style answer.

    Raises:
        AnswerFormatError: If the answer has no ``findings`` list.
    """
    data = load_json_object(text)
    raw_issues = data.get("findings")
    if not isinstance(raw_issues, list):
        raise AnswerFormatError('the answer has no "findings" list')
    raw_judgements = data.get("static_judgements")
    issues, bad_issues = _validate_each(ReportedIssue, raw_issues)
    judgements, bad_judgements = _validate_each(
        StaticJudgement, raw_judgements if isinstance(raw_judgements, list) else []
    )
    return ReviewAnswer(judgements, issues, discarded=bad_issues + bad_judgements)


class VerificationVerdict(StrEnum):
    """A second model's view of a reported issue."""

    VALID = "valid"
    INVALID = "invalid"
    UNCERTAIN = "uncertain"


class VerificationAnswer(BaseModel):
    """A parsed verification answer."""

    model_config = ConfigDict(extra="ignore", frozen=True, str_strip_whitespace=True)

    verdict: VerificationVerdict
    reason: str = ""
    corrected_severity: Severity | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    _verdict = field_validator("verdict", mode="before")(_normalized_word)
    _severity = field_validator("corrected_severity", mode="before")(_optional_severity)
    _confidence = field_validator("confidence", mode="before")(_fraction)


def parse_verification_answer(text: str) -> VerificationAnswer:
    """Parse a verification answer.

    Raises:
        AnswerFormatError: If the answer has no valid verdict.
    """
    return _validate_whole(VerificationAnswer, load_json_object(text))


class TopRisk(BaseModel):
    """One of the most important problems named in a summary."""

    model_config = ConfigDict(
        extra="ignore",
        frozen=True,
        str_strip_whitespace=True,
        json_schema_serialization_defaults_required=True,
    )

    title: str = Field(min_length=1)
    files: list[str] = []
    why: str = ""


class ReviewSummary(BaseModel):
    """The executive summary of a review."""

    model_config = ConfigDict(
        extra="ignore",
        frozen=True,
        str_strip_whitespace=True,
        json_schema_serialization_defaults_required=True,
    )

    headline: str = Field(min_length=1)
    strengths: list[str] = []
    top_risks: list[TopRisk] = []
    recommended_next_steps: list[str] = []

    @field_validator("strengths")
    @classmethod
    def _few_strengths(cls, value: list[str]) -> list[str]:
        return value[:MAX_STRENGTHS]

    @field_validator("top_risks")
    @classmethod
    def _few_risks(cls, value: list[TopRisk]) -> list[TopRisk]:
        return value[:MAX_RISKS]

    @field_validator("recommended_next_steps")
    @classmethod
    def _few_steps(cls, value: list[str]) -> list[str]:
        return value[:MAX_NEXT_STEPS]


def parse_summary_answer(text: str) -> ReviewSummary:
    """Parse a summary answer.

    Raises:
        AnswerFormatError: If the answer has no headline.
    """
    return _validate_whole(ReviewSummary, load_json_object(text))


def _validate_each(model: type[ModelT], items: Sequence[object]) -> tuple[list[ModelT], int]:
    valid: list[ModelT] = []
    for item in items:
        try:
            valid.append(model.model_validate(item))
        except ValidationError:
            continue
    return valid, len(items) - len(valid)


def _validate_whole(model: type[ModelT], data: dict[str, Any]) -> ModelT:
    try:
        return model.model_validate(data)
    except ValidationError as error:
        fields = ", ".join(sorted({str(e["loc"][0]) for e in error.errors() if e["loc"]}))
        raise AnswerFormatError(f"the answer has invalid fields: {fields or 'unknown'}") from error
