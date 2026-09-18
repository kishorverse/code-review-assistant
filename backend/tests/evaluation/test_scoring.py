import pytest

from app.findings import Category, Severity
from evaluation.dataset import Detection, Label, LocatedLabel
from evaluation.scoring import Counts, Prediction, assess, matches, maximum_matching, score


def located(
    label_id: str,
    line: int,
    category: Category = Category.BUG,
    *,
    file: str = "a.py",
    detection: Detection = "semantic",
    cwe: str | None = None,
) -> LocatedLabel:
    return LocatedLabel(
        label=Label(
            id=label_id,
            file=file,
            anchor="x",
            category=category,
            cwe=cwe,
            severity=Severity.MEDIUM,
            detection=detection,
            description="d",
        ),
        start_line=line,
        end_line=line,
    )


def predicted(
    pred_id: str, line: int, category: Category = Category.BUG, *, file: str = "a.py"
) -> Prediction:
    return Prediction(
        id=pred_id,
        file=file,
        start_line=line,
        end_line=line,
        category=category,
        sources=("ruff",),
    )


@pytest.mark.parametrize(
    ("prediction", "expected"),
    [
        (predicted("p", 12), True),
        (predicted("p", 8), True),
        (predicted("p", 7), False),
        (predicted("p", 13), False),
        (predicted("p", 10, file="b.py"), False),
        (predicted("p", 10, Category.STYLE), False),
        (predicted("p", 10, Category.TYPING), True),
    ],
    ids=[
        "within-2-after",
        "within-2-before",
        "too-early",
        "too-late",
        "other-file",
        "other-category",
        "typing-counts-as-bug",
    ],
)
def test_matching_needs_the_file_nearby_lines_and_the_category(
    prediction: Prediction, expected: bool
) -> None:
    assert matches(prediction, located("l", 10)) is expected


def test_location_only_matching_ignores_the_category() -> None:
    assert matches(predicted("p", 10, Category.STYLE), located("l", 10), by_category=False)


def test_one_finding_cannot_stand_in_for_two_nearby_issues() -> None:
    labels = [located("first", 10), located("second", 11)]

    result = assess([predicted("p", 10)], labels)

    assert result.counts == Counts(correct_predictions=1, predictions=1, found_labels=1, labels=2)


def test_matching_finds_the_pairing_that_covers_the_most_labels() -> None:
    # Greedy pairing would give label 0 prediction 0 and leave label 1 unpaired.
    assert maximum_matching([[0, 1], [0]]) == {0: 1, 1: 0}


def test_duplicate_reports_of_one_issue_are_all_correct_but_found_once() -> None:
    result = assess([predicted("bandit", 10), predicted("opengrep", 10)], [located("l", 10)])

    assert result.counts == Counts(correct_predictions=2, predictions=2, found_labels=1, labels=1)


def test_undefined_metrics_are_none_rather_than_zero() -> None:
    empty = Counts(correct_predictions=0, predictions=0, found_labels=0, labels=3)

    assert (empty.precision, empty.recall, empty.f1) == (None, 0.0, None)
    assert Counts(0, 4, 0, 3).f1 == 0.0


def test_scorecard_splits_by_category_detection_cwe_and_clean_files() -> None:
    labels = [
        located("sqli", 5, Category.SECURITY, detection="static", cwe="CWE-89"),
        located("logic", 20),
    ]
    predictions = [
        predicted("bandit", 5, Category.SECURITY),
        predicted("noise", 40, Category.STYLE),
        predicted("clean", 3, file="clean.py"),
    ]

    card = score(predictions, labels, ["clean.py"])

    assert card.overall == Counts(1, 3, 1, 2)
    assert card.by_category["security"] == Counts(1, 1, 1, 1)
    assert card.by_category["style"].labels == 0
    assert card.macro_f1 == pytest.approx(0.5)
    assert card.recall_by_detection["static"].found_labels == 1
    assert card.recall_by_detection["semantic"].found_labels == 0
    assert card.recall_by_cwe["CWE-89"] == Counts(0, 0, 1, 1)
    assert card.clean_file_findings == 1
    assert card.found == frozenset({"sqli"})
