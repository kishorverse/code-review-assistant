"""A transparent project quality score from 0 to 100, with a letter grade.

::

    finding_penalty    = sum of severity weights of reported findings / max(1, KLOC)
    complexity_penalty = 20 x share of functions with cyclomatic complexity >= 21
    score              = clamp(100 - finding_penalty - complexity_penalty, 0, 100)

Severity weights are critical 25, high 10, medium 4, low 1 and info 0. A complexity
of 21 is where Radon's grade D begins. Grades are A from 90, B from 75, C from 60,
D from 40, and E below. Only findings in the default report count, so findings
dismissed by AI review, rejected by a reviewer or below the confidence threshold
do not lower the score. The formula is included in every report, because a
number nobody can check is not worth showing.
"""

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, NonNegativeFloat, NonNegativeInt

from app.findings import Finding, Severity
from app.static.base import FileMetrics

SEVERITY_WEIGHTS = {
    Severity.CRITICAL: 25,
    Severity.HIGH: 10,
    Severity.MEDIUM: 4,
    Severity.LOW: 1,
    Severity.INFO: 0,
}
COMPLEX_FUNCTION_THRESHOLD = 21
COMPLEXITY_WEIGHT = 20.0
GRADE_THRESHOLDS: tuple[tuple[int, Literal["A", "B", "C", "D"]], ...] = (
    (90, "A"),
    (75, "B"),
    (60, "C"),
    (40, "D"),
)
FORMULA = (
    "100 - (25 x critical + 10 x high + 4 x medium + 1 x low) / max(1, KLOC)"
    " - 20 x share of functions with cyclomatic complexity >= 21"
)

Grade = Literal["A", "B", "C", "D", "E"]


class QualityScore(BaseModel):
    """The score, its grade and every input needed to recompute it."""

    model_config = ConfigDict(frozen=True, json_schema_serialization_defaults_required=True)

    score: int = Field(ge=0, le=100)
    grade: Grade
    kloc: NonNegativeFloat
    finding_penalty: NonNegativeFloat
    complexity_penalty: NonNegativeFloat
    functions: NonNegativeInt
    complex_functions: NonNegativeInt
    formula: str = FORMULA


def quality_score(
    reported: Sequence[Finding], source_lines: int, metrics: Sequence[FileMetrics]
) -> QualityScore:
    """Score a project.

    Args:
        reported: The findings in the default report.
        source_lines: Lines of code in the reviewed files.
        metrics: Per-file metrics. A function measured by several tools counts once,
            with its highest complexity.
    """
    kloc = source_lines / 1000
    finding_penalty = sum(SEVERITY_WEIGHTS[finding.severity] for finding in reported) / max(
        1.0, kloc
    )
    # Radon and Lizard both measure functions and may name them differently.
    complexities: dict[tuple[str, int], int] = {}
    for entry in metrics:
        for function in entry.functions:
            key = (entry.path, function.start_line)
            complexities[key] = max(complexities.get(key, 0), function.cyclomatic_complexity)
    complex_functions = sum(value >= COMPLEX_FUNCTION_THRESHOLD for value in complexities.values())
    complexity_penalty = (
        COMPLEXITY_WEIGHT * complex_functions / len(complexities) if complexities else 0.0
    )
    score = round(min(100.0, max(0.0, 100.0 - finding_penalty - complexity_penalty)))
    return QualityScore(
        score=score,
        grade=grade(score),
        kloc=round(kloc, 3),
        finding_penalty=round(finding_penalty, 1),
        complexity_penalty=round(complexity_penalty, 1),
        functions=len(complexities),
        complex_functions=complex_functions,
    )


def grade(score: int) -> Grade:
    """The letter grade for a score."""
    return next((letter for threshold, letter in GRADE_THRESHOLDS if score >= threshold), "E")
