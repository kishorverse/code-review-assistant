import pytest
from pydantic import ValidationError

from app.findings import (
    MAX_TITLE_LENGTH,
    Category,
    Finding,
    FindingStatus,
    Severity,
    shorten_title,
)


def make_finding(**overrides: object) -> Finding:
    values: dict[str, object] = {
        "file_path": "app/db.py",
        "start_line": 12,
        "end_line": 14,
        "category": Category.SECURITY,
        "severity": Severity.HIGH,
        "title": "SQL built with string formatting",
        "message": "User input is formatted into a SQL query.",
        "sources": ["bandit"],
    }
    values.update(overrides)
    return Finding.model_validate(values)


def test_defaults_are_open_fully_confident_and_uniquely_identified() -> None:
    first, second = make_finding(), make_finding()

    assert first.status is FindingStatus.OPEN
    assert first.confidence == 1.0
    assert first.id != second.id


def test_severity_rank_orders_most_severe_highest() -> None:
    ordered = sorted(Severity, key=lambda severity: severity.rank, reverse=True)

    assert ordered == [
        Severity.CRITICAL,
        Severity.HIGH,
        Severity.MEDIUM,
        Severity.LOW,
        Severity.INFO,
    ]


@pytest.mark.parametrize(
    "overrides",
    [
        {"end_line": 11},
        {"start_line": 0},
        {"confidence": 1.5},
        {"sources": []},
        {"cwe": "78"},
        {"title": "x" * (MAX_TITLE_LENGTH + 1)},
    ],
)
def test_rejects_invalid_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        make_finding(**overrides)


def test_shorten_title_collapses_whitespace_and_truncates() -> None:
    assert shorten_title("  unused\n import   'os' ") == "unused import 'os'"
    long_title = shorten_title("word " * 40)
    assert len(long_title) == MAX_TITLE_LENGTH
    assert long_title.endswith("…")
