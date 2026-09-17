import pytest

from app.findings import Severity
from app.report.score import grade, quality_score
from app.static.base import FileMetrics, FunctionMetrics
from tests.report.conftest import finding


def function(start: int, complexity: int, name: str = "f") -> FunctionMetrics:
    return FunctionMetrics(
        name=name,
        start_line=start,
        end_line=start + 5,
        cyclomatic_complexity=complexity,
        lines_of_code=5,
        parameters=1,
    )


def test_a_clean_project_scores_100() -> None:
    score = quality_score([], source_lines=800, metrics=[])

    assert (score.score, score.grade, score.finding_penalty, score.complexity_penalty) == (
        100,
        "A",
        0.0,
        0.0,
    )


def test_finding_penalty_is_weighted_by_severity_per_thousand_lines() -> None:
    findings = [finding(severity=Severity.CRITICAL), finding(severity=Severity.MEDIUM)]

    small = quality_score(findings, source_lines=400, metrics=[])
    large = quality_score(findings, source_lines=4000, metrics=[])

    assert (small.finding_penalty, small.score) == (29.0, 71)
    assert (large.kloc, large.finding_penalty, large.score) == (4.0, 7.2, 93)


def test_complexity_penalty_uses_the_share_of_very_complex_functions() -> None:
    metrics = [
        FileMetrics(path="a.py", functions=[function(1, 25), function(10, 3)]),
        FileMetrics(path="b.py", functions=[function(1, 21), function(9, 20)]),
    ]

    score = quality_score([], source_lines=100, metrics=metrics)

    assert (score.functions, score.complex_functions, score.complexity_penalty) == (4, 2, 10.0)
    assert score.score == 90


def test_a_function_measured_by_two_tools_counts_once_with_its_highest_complexity() -> None:
    radon = FileMetrics(path="a.py", functions=[function(1, 19, name="Parser.parse")])
    lizard = FileMetrics(path="a.py", functions=[function(1, 22, name="Parser::parse")])

    score = quality_score([], source_lines=100, metrics=[radon, lizard])

    assert (score.functions, score.complex_functions) == (1, 1)


def test_score_never_drops_below_zero() -> None:
    findings = [finding(severity=Severity.CRITICAL)] * 10

    assert quality_score(findings, source_lines=50, metrics=[]).score == 0


@pytest.mark.parametrize(
    ("value", "letter"),
    [(100, "A"), (90, "A"), (89, "B"), (75, "B"), (60, "C"), (40, "D"), (39, "E")],
)
def test_grades(value: int, letter: str) -> None:
    assert grade(value) == letter
