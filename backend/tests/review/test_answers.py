import json

import pytest

from app.errors import AnswerFormatError
from app.findings import Category, Severity
from app.review.answers import (
    JudgementVerdict,
    VerificationVerdict,
    load_json_object,
    parse_review_answer,
    parse_summary_answer,
    parse_verification_answer,
)

ISSUE = {
    "start_line": 3,
    "end_line": 3,
    "category": "security",
    "severity": "high",
    "title": "SQL built from user input",
    "message": "name is concatenated into the query.",
    "rationale": "An attacker can read or change any table.",
    "evidence": 'query = "SELECT * FROM users WHERE name = \'" + name + "\'"',
    "cwe": "CWE-89",
    "confidence": 0.9,
    "suggested_change": "Use a parameterized query.",
}


@pytest.mark.parametrize(
    "text",
    [
        '{"findings": []}',
        '```json\n{"findings": []}\n```',
        'Here is my review:\n{"findings": []}\nThanks!',
        '<think>The user wants {a review}.</think>\n{"findings": []}',
    ],
)
def test_finds_the_json_object_in_common_answer_shapes(text: str) -> None:
    assert load_json_object(text) == {"findings": []}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("I could not review this code.", "no JSON object"),
        ('{"findings": [}', "not valid JSON"),
        ("[1, 2, 3]", "not a JSON object"),
    ],
)
def test_rejects_answers_without_a_json_object(text: str, message: str) -> None:
    with pytest.raises(AnswerFormatError, match=message):
        load_json_object(text)


def test_parses_issues_and_judgements() -> None:
    answer = parse_review_answer(
        json.dumps(
            {
                "static_judgements": [
                    {"static_id": "S1", "verdict": "false_positive", "reason": "Test fixture."}
                ],
                "findings": [ISSUE],
            }
        )
    )

    [issue] = answer.issues
    assert (issue.category, issue.severity, issue.cwe, issue.confidence) == (
        Category.SECURITY,
        Severity.HIGH,
        "CWE-89",
        0.9,
    )
    [judgement] = answer.judgements
    assert (judgement.static_id, judgement.verdict) == ("S1", JudgementVerdict.FALSE_POSITIVE)
    assert answer.discarded == 0


def test_normalizes_the_ways_models_vary_the_format() -> None:
    varied = ISSUE | {
        "category": " Security ",
        "severity": "HIGH",
        "cwe": "cwe 089",
        "confidence": "85%",
        "title": "A very long title " * 10,
    }
    judgement = {"static_id": "S2", "verdict": "False Positive", "adjusted_severity": "null"}

    answer = parse_review_answer(
        json.dumps({"static_judgements": [judgement], "findings": [varied]})
    )

    [issue] = answer.issues
    assert (issue.category, issue.severity, issue.cwe, issue.confidence) == (
        Category.SECURITY,
        Severity.HIGH,
        "CWE-89",
        0.85,
    )
    assert len(issue.title) <= 80
    assert answer.judgements[0].verdict is JudgementVerdict.FALSE_POSITIVE
    assert answer.judgements[0].adjusted_severity is None


def test_drops_only_the_malformed_items() -> None:
    broken = [
        ISSUE | {"category": "vibes"},
        ISSUE | {"start_line": 0},
        ISSUE | {"start_line": 9, "end_line": 4},
        ISSUE | {"evidence": "   "},
        {k: v for k, v in ISSUE.items() if k != "message"},
        "not an object",
    ]
    judgements = [{"static_id": "S1", "verdict": "maybe"}, {"verdict": "confirmed"}]

    answer = parse_review_answer(
        json.dumps({"static_judgements": judgements, "findings": [ISSUE, *broken]})
    )

    assert len(answer.issues) == 1
    assert answer.judgements == []
    assert answer.discarded == len(broken) + len(judgements)


def test_missing_confidence_is_treated_as_uncertain() -> None:
    issue = {k: v for k, v in ISSUE.items() if k != "confidence"}

    [parsed] = parse_review_answer(json.dumps({"findings": [issue]})).issues

    assert parsed.confidence == 0.5


def test_a_review_answer_needs_a_findings_list() -> None:
    with pytest.raises(AnswerFormatError, match="findings"):
        parse_review_answer('{"issues": []}')


def test_parses_verification_answers() -> None:
    answer = parse_verification_answer(
        '{"verdict": "Invalid", "reason": "name is validated above.", '
        '"corrected_severity": "None", "confidence": 90}'
    )

    assert answer.verdict is VerificationVerdict.INVALID
    assert (answer.corrected_severity, answer.confidence) == (None, 0.9)


def test_a_verification_answer_needs_a_verdict() -> None:
    with pytest.raises(AnswerFormatError, match="verdict"):
        parse_verification_answer('{"verdict": "probably", "reason": "?"}')


def test_parses_summaries_and_caps_their_lists() -> None:
    summary = parse_summary_answer(
        json.dumps(
            {
                "headline": "Two injection risks need fixing before release.",
                "strengths": ["a", "b", "c", "d"],
                "top_risks": [{"title": "SQL injection", "files": ["app/db.py"], "why": "x"}],
                "recommended_next_steps": [str(n) for n in range(9)],
            }
        )
    )

    assert summary.strengths == ["a", "b", "c"]
    assert summary.top_risks[0].files == ["app/db.py"]
    assert len(summary.recommended_next_steps) == 5


def test_a_summary_needs_a_headline() -> None:
    with pytest.raises(AnswerFormatError, match="headline"):
        parse_summary_answer('{"strengths": []}')
