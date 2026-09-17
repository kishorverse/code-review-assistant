import pytest

from app.findings import Severity
from app.languages.base import SupportLevel
from app.preprocess.models import Chunk, LineRange, PreprocessedFile
from app.review.planner import Depth, ReviewOptions, plan_review, risk_score
from app.static.base import FileMetrics, FunctionMetrics
from tests.review.conftest import make_finding


def chunk(path: str, index: int, start: int, end: int) -> Chunk:
    return Chunk(
        file_path=path,
        language="python",
        index=index,
        lines=LineRange(start=start, end=end),
        context=[],
        partial_regions=[],
        numbered_code="",
    )


FILES = [
    PreprocessedFile(
        path="app/db.py",
        language="python",
        support=SupportLevel.FULL,
        line_count=90,
        partial_regions=[],
        chunks=[chunk("app/db.py", 0, 1, 30), chunk("app/db.py", 1, 31, 60)],
    ),
    PreprocessedFile(
        path="app/util.py",
        language="python",
        support=SupportLevel.FULL,
        line_count=40,
        partial_regions=[],
        chunks=[chunk("app/util.py", 0, 1, 40)],
    ),
]
INJECTION = make_finding(file_path="app/db.py", start_line=45, severity=Severity.HIGH)
COMPLEX = FileMetrics(
    path="app/util.py",
    functions=[
        FunctionMetrics(
            name="parse",
            start_line=2,
            end_line=38,
            cyclomatic_complexity=17,
            lines_of_code=36,
            parameters=4,
        )
    ],
)


def names(chunks: list[Chunk]) -> list[str]:
    return [f"{c.file_path}#{c.index}" for c in chunks]


def test_static_depth_plans_no_calls() -> None:
    plan = plan_review(FILES, [INJECTION], [COMPLEX], ReviewOptions(depth=Depth.STATIC))

    assert (plan.calls, plan.skipped) == (0, 3)


def test_quick_depth_reviews_only_risky_chunks_riskiest_first() -> None:
    plan = plan_review(FILES, [INJECTION], [COMPLEX], ReviewOptions(depth=Depth.QUICK))

    assert names(plan.review) == ["app/db.py#1", "app/util.py#0"]
    assert plan.style == []
    assert plan.skipped == 1


def test_standard_depth_reviews_everything_and_styles_within_budget() -> None:
    options = ReviewOptions(depth=Depth.STANDARD, max_review_calls=5)

    plan = plan_review(FILES, [INJECTION], [COMPLEX], options)

    assert names(plan.review) == ["app/db.py#1", "app/util.py#0", "app/db.py#0"]
    assert names(plan.style) == ["app/db.py#1", "app/util.py#0"]
    assert (plan.calls, plan.skipped) == (5, 0)


def test_a_small_budget_reviews_the_riskiest_chunks_and_counts_the_rest() -> None:
    plan = plan_review(FILES, [INJECTION], [COMPLEX], ReviewOptions(max_review_calls=1))

    assert names(plan.review) == ["app/db.py#1"]
    assert (plan.style, plan.skipped) == ([], 2)


def test_risk_counts_findings_by_severity_and_complex_functions() -> None:
    db_second, util = FILES[0].chunks[1], FILES[1].chunks[0]
    formatting = make_finding(
        file_path="app/db.py", start_line=50, rule_id="E501", sources=["ruff"]
    )

    assert risk_score(db_second, [INJECTION, formatting], None) == Severity.HIGH.rank + 1
    assert risk_score(util, [], COMPLEX) == 17 // 5
    assert risk_score(FILES[0].chunks[0], [INJECTION], COMPLEX) == 0


@pytest.mark.parametrize(
    ("depth", "verify_from"),
    [
        (Depth.STATIC, None),
        (Depth.QUICK, Severity.CRITICAL),
        (Depth.STANDARD, Severity.HIGH),
        (Depth.DEEP, Severity.MEDIUM),
    ],
)
def test_depth_sets_which_ai_findings_are_cross_checked(
    depth: Depth, verify_from: Severity | None
) -> None:
    assert ReviewOptions(depth=depth).verify_from is verify_from
