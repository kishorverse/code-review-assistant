import json

import pytest

from app.findings import Category, FindingStatus, Severity
from app.llm.models import CallRecord, CallStatus, LLMRequest, Task
from app.llm.prompts import default_prompts
from app.llm.providers.mock import MockProvider
from app.redaction import SecretIndex
from app.review.answers import JudgementVerdict
from app.review.context import ReviewContext, build_context, for_review, load_source
from app.review.reviewer import review_chunk
from tests.review.conftest import DB_MODULE, ProjectFactory, make_finding, mock_router

INJECTION_ISSUE = {
    "start_line": 4,
    "end_line": 4,
    "category": "security",
    "severity": "critical",
    "title": "SQL injection through name",
    "message": "name is concatenated into the SQL query.",
    "rationale": "Anyone controlling name can read or modify the users table.",
    "evidence": '4 |     query = "SELECT * FROM users WHERE name = \'" + name + "\'"',
    "cwe": "CWE-89",
    "confidence": 0.95,
    "suggested_change": "Pass name as a query parameter.",
}


@pytest.fixture
def context(make_project: ProjectFactory) -> ReviewContext:
    root, [file] = make_project({"app/db.py": DB_MODULE})
    unused = make_finding(start_line=1, category=Category.MAINTAINABILITY, rule_id="F401")
    return build_context(
        file.chunks[0], load_source(root, file, SecretIndex()), [unused], None, "", for_review
    )


def answer(findings: list[object], judgements: list[object] | None = None) -> str:
    return json.dumps({"static_judgements": judgements or [], "findings": findings})


async def test_turns_grounded_issues_into_findings_and_resolves_judgements(
    context: ReviewContext,
) -> None:
    seen: list[LLMRequest] = []

    def respond(request: LLMRequest) -> str:
        seen.append(request)
        return answer(
            [INJECTION_ISSUE],
            [{"static_id": "S1", "verdict": "false_positive", "reason": "sqlite3 is used."}],
        )

    router = mock_router(MockProvider("nvidia", respond=respond, external=True))

    review = await review_chunk(
        router, default_prompts(), context, Task.REVIEW, allow_external=True
    )

    [finding] = review.findings
    assert (finding.severity, finding.category, finding.cwe) == (
        Severity.CRITICAL,
        Category.SECURITY,
        "CWE-89",
    )
    assert finding.sources == ["nvidia"]
    assert finding.rule_id == "ai/security"
    assert finding.evidence == 'query = "SELECT * FROM users WHERE name = \'" + name + "\'"'
    assert finding.suggestion == "Pass name as a query parameter."
    assert finding.status is FindingStatus.OPEN
    [judged] = review.judgements
    assert judged.finding is context.static_findings["S1"]
    assert (judged.provider, judged.judgement.verdict) == (
        "nvidia",
        JudgementVerdict.FALSE_POSITIVE,
    )
    assert review.failure is None
    [request] = seen
    assert request.allow_external
    assert request.max_output_tokens == 4096
    assert "1 | import sqlite3" in request.user
    assert "Rules:" in request.system


async def test_drops_ungrounded_off_task_and_unknown_items(context: ReviewContext) -> None:
    invented = INJECTION_ISSUE | {"evidence": "cursor.executemany(sql, rows)"}
    style = INJECTION_ISSUE | {"category": "style", "severity": "low"}
    unknown_static = {"static_id": "S9", "verdict": "confirmed"}
    router = mock_router(
        MockProvider(respond=lambda request: answer([invented, style, {"x": 1}], [unknown_static]))
    )

    review = await review_chunk(
        router, default_prompts(), context, Task.REVIEW, allow_external=False
    )

    assert review.findings == []
    assert review.judgements == []
    assert review.discarded == 3


async def test_an_unusable_answer_falls_back_to_the_next_provider(context: ReviewContext) -> None:
    router = mock_router(
        MockProvider("nvidia", respond=lambda request: "I found a SQL injection on line 4."),
        MockProvider("local", respond=lambda request: answer([INJECTION_ISSUE])),
    )
    records: list[CallRecord] = []

    review = await review_chunk(
        router,
        default_prompts(),
        context,
        Task.REVIEW,
        allow_external=False,
        on_call=records.append,
    )

    assert [(r.provider, r.status) for r in records] == [
        ("nvidia", CallStatus.REJECTED),
        ("local", CallStatus.OK),
    ]
    assert review.findings[0].sources == ["local"]


async def test_reports_a_failure_when_no_provider_can_review(context: ReviewContext) -> None:
    router = mock_router(MockProvider("gemini", external=True))

    review = await review_chunk(
        router, default_prompts(), context, Task.STYLE, allow_external=False
    )

    assert review.findings == []
    assert review.failure is not None
    assert "style" in review.failure


async def test_style_reviews_use_the_style_prompt_and_categories(context: ReviewContext) -> None:
    seen: list[LLMRequest] = []
    naming = INJECTION_ISSUE | {"category": "style", "severity": "low", "title": "Vague name"}

    def respond(request: LLMRequest) -> str:
        seen.append(request)
        return answer([naming, INJECTION_ISSUE])

    router = mock_router(MockProvider(respond=respond))

    review = await review_chunk(
        router, default_prompts(), context, Task.STYLE, allow_external=False
    )

    assert [finding.title for finding in review.findings] == ["Vague name"]
    assert review.discarded == 1
    assert "PEP 8 and PEP 257" in seen[0].user
    assert seen[0].max_output_tokens == 2048
