import hashlib
import json

from app.findings import Category, FindingStatus, Severity
from app.llm.models import LLMRequest
from app.llm.prompts import default_prompts
from app.llm.providers.mock import MockProvider
from app.redaction import SecretIndex
from app.review.summary import MAX_LISTED_FINDINGS, finding_lines, project_facts, summarize
from tests.review.conftest import ProjectFactory, make_finding, mock_router

FINDINGS = [
    make_finding(severity=Severity.MEDIUM, sources=["bandit", "nvidia"]),
    make_finding(
        file_path="app/api.py", start_line=9, severity=Severity.CRITICAL, category=Category.BUG
    ),
    make_finding(start_line=30, status=FindingStatus.DISMISSED_BY_AI),
    make_finding(start_line=31, confidence=0.3, sources=["hf-small"]),
]


def test_facts_count_only_reported_findings(make_project: ProjectFactory) -> None:
    _, files = make_project({"app/db.py": "x = 1\n", "app/api.py": "y = 2\n"})

    facts = project_facts(files, FINDINGS, min_confidence=0.6)

    assert facts.splitlines() == [
        "files: 2 reviewable files (python 2)",
        "reported findings: 2 (medium 1, critical 1)",
        "by category: security 1, bug 1",
        "dismissed by AI review: 1; needing human review: 0",
    ]


def test_finding_lines_are_most_severe_first_and_capped() -> None:
    lines = finding_lines(FINDINGS, 0.6, SecretIndex()).splitlines()
    many = finding_lines(
        [make_finding(start_line=n + 1) for n in range(40)], 0.6, SecretIndex()
    ).splitlines()

    assert lines == [
        "- [critical] bug, app/api.py:9: SQL built with string concatenation (found by bandit)",
        "- [medium] security, app/db.py:4: SQL built with string concatenation"
        " (found by bandit, nvidia)",
    ]
    assert len(many) == MAX_LISTED_FINDINGS + 1
    assert many[-1] == "- and 10 more"
    assert finding_lines([], 0.6, SecretIndex()) == "none"


async def test_summarize_sends_facts_without_code(make_project: ProjectFactory) -> None:
    _, files = make_project({"app/db.py": "SECRET_CODE_MARKER = 1\n"})
    seen: list[LLMRequest] = []

    def respond(request: LLMRequest) -> str:
        seen.append(request)
        return json.dumps({"headline": "One critical bug needs fixing.", "strengths": ["Small"]})

    summary = await summarize(
        mock_router(MockProvider(respond=respond)),
        default_prompts(),
        files,
        FINDINGS,
        SecretIndex(),
        min_confidence=0.6,
        allow_external=False,
    )

    assert summary is not None
    assert summary.headline == "One critical bug needs fixing."
    assert "SECRET_CODE_MARKER" not in seen[0].user
    assert "app/api.py:9" in seen[0].user


async def test_no_summary_when_no_provider_answers(make_project: ProjectFactory) -> None:
    _, files = make_project({"app/db.py": "x = 1\n"})

    summary = await summarize(
        mock_router(MockProvider("gemini", external=True)),
        default_prompts(),
        files,
        FINDINGS,
        SecretIndex(),
        min_confidence=0.6,
        allow_external=False,
    )

    assert summary is None


async def test_a_prose_summary_falls_back_to_the_next_model(make_project: ProjectFactory) -> None:
    _, files = make_project({"app/db.py": "x = 1\n"})
    router = mock_router(
        MockProvider("gemini", respond=lambda request: "The code has issues."),
        MockProvider("local", respond=lambda request: '{"headline": "Two issues."}'),
    )

    summary = await summarize(
        router,
        default_prompts(),
        files,
        FINDINGS,
        SecretIndex(),
        min_confidence=0.6,
        allow_external=True,
    )

    assert summary is not None
    assert summary.headline == "Two issues."


def test_finding_titles_are_masked_for_detected_secrets() -> None:
    value = "placeholder-" + "credential"
    index = SecretIndex()
    index.add_hashes([hashlib.sha1(value.encode(), usedforsecurity=False).hexdigest()])
    quoting = make_finding(title=f"Magic value {value} used in comparison")

    lines = finding_lines([quoting], 0.6, index)

    assert value not in lines
    assert "Magic value <REDACTED_SECRET> used in comparison" in lines
