import hashlib
import json

from app.events import CallEvent, CollectingSink, FindingEvent, ReviewPlanEvent
from app.findings import Category, FindingStatus, Severity
from app.llm.models import CallStatus, LLMRequest, Task
from app.llm.providers.mock import MockProvider
from app.redaction import SecretIndex
from app.review.planner import Depth, ReviewOptions
from app.review.session import ReviewSession
from app.static.runner import StaticAnalysisResult
from tests.review.conftest import DB_MODULE, ProjectFactory, make_finding, mock_router

INJECTION = make_finding(severity=Severity.MEDIUM)
UNUSED_IMPORT = make_finding(
    start_line=1,
    category=Category.MAINTAINABILITY,
    severity=Severity.LOW,
    rule_id="F401",
    sources=["ruff"],
    title="sqlite3 imported but unused",
)
FETCH_ALL = {
    "start_line": 5,
    "end_line": 5,
    "category": "performance",
    "severity": "high",
    "title": "Loads every matching row into memory",
    "message": "fetchall() materializes the whole result set.",
    "evidence": "return db.execute(query).fetchall()",
    "confidence": 0.8,
}
EMPTY = json.dumps({"static_judgements": [], "findings": []})


def static_result(secrets: SecretIndex | None = None) -> StaticAnalysisResult:
    return StaticAnalysisResult(
        findings=[INJECTION, UNUSED_IMPORT],
        tool_runs=[],
        metrics=[],
        secrets=secrets or SecretIndex(),
    )


def reviewer(request: LLMRequest) -> str:
    if request.task is Task.REVIEW:
        return json.dumps(
            {
                "static_judgements": [
                    {
                        "static_id": "S1",
                        "verdict": "confirmed",
                        "reason": "name reaches the query.",
                    },
                    {"static_id": "S2", "verdict": "false_positive", "reason": "Used elsewhere."},
                ],
                "findings": [FETCH_ALL],
            }
        )
    if request.task is Task.SUMMARIZE:
        return json.dumps({"headline": "One injection and one memory risk."})
    return EMPTY


def verifier(request: LLMRequest) -> str:
    return json.dumps({"verdict": "valid", "reason": "No limit is applied.", "confidence": 0.9})


async def test_reviews_verifies_and_summarizes_a_scan(make_project: ProjectFactory) -> None:
    root, files = make_project({"app/db.py": DB_MODULE})
    router = mock_router(
        MockProvider("nvidia", respond=reviewer, external=True),
        MockProvider("gemini", respond=verifier, external=True),
    )
    sink = CollectingSink()
    session = ReviewSession(router, ReviewOptions(depth=Depth.STANDARD, allow_external=True), sink)

    findings = await session.review(files, static_result(), root)
    findings = await session.verify(findings)
    result = session.result(findings, await session.summarize(files, findings))

    fetch_all, injection, unused = result.findings
    assert (fetch_all.severity, fetch_all.sources, fetch_all.verified_by) == (
        Severity.HIGH,
        ["nvidia"],
        ["gemini"],
    )
    assert injection.id == INJECTION.id
    assert injection.sources == ["bandit", "nvidia"]
    assert unused.status is FindingStatus.DISMISSED_BY_AI
    assert result.summary is not None
    assert result.summary.headline == "One injection and one memory risk."
    assert (result.stats.chunks_reviewed, result.stats.ai_findings, result.stats.judgements) == (
        1,
        1,
        2,
    )
    assert (result.stats.verified, result.stats.tasks_failed) == (1, 0)
    assert sorted((c.task, c.provider, c.status) for c in result.calls) == sorted(
        [
            (Task.REVIEW, "nvidia", CallStatus.OK),
            (Task.STYLE, "nvidia", CallStatus.OK),
            (Task.VERIFY, "gemini", CallStatus.OK),
            (Task.SUMMARIZE, "nvidia", CallStatus.OK),
        ]
    )
    assert {(c.task, c.file_path) for c in result.calls} == {
        (Task.REVIEW, "app/db.py"),
        (Task.STYLE, "app/db.py"),
        (Task.VERIFY, "app/db.py"),
        (Task.SUMMARIZE, None),
    }
    assert result.prompt_versions["task_review"] == "1"
    events = sink.events
    assert events[0] == ReviewPlanEvent(review_chunks=1, style_chunks=1, skipped_chunks=0)
    assert sum(isinstance(event, CallEvent) for event in events) == 4
    changed = [event.finding.title for event in events if isinstance(event, FindingEvent)]
    assert sorted(changed) == sorted(
        [INJECTION.title, UNUSED_IMPORT.title, FETCH_ALL["title"], FETCH_ALL["title"]]
    )


async def test_without_consent_hosted_models_get_nothing_and_findings_stay_static(
    make_project: ProjectFactory,
) -> None:
    root, files = make_project({"app/db.py": DB_MODULE})
    hosted = MockProvider("nvidia", respond=reviewer, external=True)
    session = ReviewSession(mock_router(hosted), ReviewOptions(), CollectingSink())

    findings = await session.review(files, static_result(), root)
    findings = await session.verify(findings)
    result = session.result(findings, await session.summarize(files, findings))

    assert result.findings == [INJECTION, UNUSED_IMPORT]
    assert result.summary is None
    assert result.calls == []
    assert result.stats.tasks_failed == 2


async def test_models_never_see_detected_secrets(make_project: ProjectFactory) -> None:
    value = "placeholder-" + "api-credential"
    root, files = make_project({"app/client.py": f'API_KEY = "{value}"\n\ndef call():\n    pass\n'})
    secrets = SecretIndex()
    secrets.add_hashes([hashlib.sha1(value.encode(), usedforsecurity=False).hexdigest()])
    prompts: list[str] = []

    def capture(request: LLMRequest) -> str:
        prompts.append(request.user)
        return EMPTY if request.task is not Task.SUMMARIZE else '{"headline": "Fine."}'

    session = ReviewSession(
        mock_router(MockProvider("local", respond=capture)), ReviewOptions(), CollectingSink()
    )
    static = StaticAnalysisResult(findings=[], tool_runs=[], metrics=[], secrets=secrets)

    await session.review(files, static, root)

    assert prompts
    assert all(value not in prompt for prompt in prompts)
    assert any('API_KEY = "<REDACTED_SECRET_1>"' in prompt for prompt in prompts)
