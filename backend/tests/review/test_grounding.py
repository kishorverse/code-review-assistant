import pytest

from app.preprocess.models import Chunk, LineRange
from app.review.context import SourceText
from app.review.grounding import clean_evidence, ungrounded_reason
from tests.review.conftest import make_issue

LINES = [
    "import sqlite3",
    "",
    "def find_user(db, name):",
    '    query = "SELECT * FROM users WHERE name = \'" + name + "\'"',
    "    return db.execute(query).fetchall()",
    *[f"value_{n} = {n}" for n in range(6, 31)],
]
SOURCE = SourceText("app/db.py", "python", LINES)
CHUNK = Chunk(
    file_path="app/db.py",
    language="python",
    index=0,
    lines=LineRange(start=3, end=12),
    context=[LineRange(start=1, end=1)],
    partial_regions=[],
    numbered_code="",
)


@pytest.mark.parametrize(
    "overrides",
    [
        {"start_line": 4, "end_line": 4},
        {"start_line": 4, "evidence": '4 |     query = "SELECT * FROM users WHERE name = \'"'},
        {"start_line": 5, "end_line": 5},
        {"start_line": 3, "end_line": 5, "evidence": 'def find_user(db, name):\n  query = "SELECT'},
        {"start_line": 1, "end_line": 1, "evidence": "import sqlite3", "category": "bug"},
    ],
)
def test_accepts_issues_quoting_code_at_or_near_the_cited_lines(
    overrides: dict[str, object],
) -> None:
    assert ungrounded_reason(make_issue(**overrides), CHUNK, SOURCE) is None


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"start_line": 40, "end_line": 41}, "past the end of the file"),
        ({"start_line": 2, "end_line": 2}, "not shown"),
        ({"start_line": 11, "end_line": 14}, "not shown"),
        ({"start_line": 10, "end_line": 10}, "not at the cited lines"),
        ({"start_line": 4, "evidence": "cursor.execute(sql)"}, "not at the cited lines"),
        ({"start_line": 4, "evidence": "4 | ("}, "no meaningful evidence"),
    ],
)
def test_rejects_issues_not_anchored_in_the_code(overrides: dict[str, object], reason: str) -> None:
    result = ungrounded_reason(make_issue(**overrides), CHUNK, SOURCE)

    assert result is not None
    assert reason in result


def test_clean_evidence_drops_line_numbers_and_keeps_at_most_five_lines() -> None:
    evidence = "\n".join(f"{n:>3} | line {n}" for n in range(1, 9))

    assert clean_evidence(evidence) == "line 1\nline 2\nline 3\nline 4\nline 5"
