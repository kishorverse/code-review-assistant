import json

import pytest

from app.findings import Finding, FindingStatus, Severity
from app.llm.models import LLMRequest
from app.llm.prompts import default_prompts
from app.llm.providers.mock import MockProvider
from app.review.answers import VerificationAnswer
from app.review.context import SourceText
from app.review.verifier import (
    NOT_VERIFIED_NOTE,
    apply_verdict,
    needs_verification,
    verify_finding,
)
from tests.review.conftest import make_finding, mock_router

SOURCE = SourceText("app/db.py", "python", [f"line_{n} = {n}" for n in range(1, 41)])
AI_FINDING = make_finding(
    start_line=20,
    severity=Severity.HIGH,
    rule_id="ai/security",
    sources=["nvidia"],
    evidence="line_20 = 20",
    confidence=0.7,
)


@pytest.mark.parametrize(
    ("finding", "verify_from", "expected"),
    [
        (AI_FINDING, Severity.HIGH, True),
        (AI_FINDING, Severity.CRITICAL, False),
        (AI_FINDING, None, False),
        (make_finding(severity=Severity.HIGH, sources=["bandit"]), Severity.LOW, False),
        (AI_FINDING.model_copy(update={"status": FindingStatus.NEEDS_REVIEW}), Severity.LOW, False),
    ],
)
def test_only_open_ai_only_findings_at_the_threshold_are_cross_checked(
    finding: Finding, verify_from: Severity | None, expected: bool
) -> None:
    assert needs_verification(finding, verify_from) is expected


async def test_asks_a_different_model_with_the_code_around_the_finding() -> None:
    seen: list[LLMRequest] = []

    def verifier(request: LLMRequest) -> str:
        seen.append(request)
        return json.dumps({"verdict": "valid", "reason": "Confirmed.", "confidence": 0.9})

    reviewer = MockProvider("nvidia", respond=lambda request: '{"verdict": "valid"}')
    router = mock_router(reviewer, MockProvider("gemini", respond=verifier, external=True))

    verified = await verify_finding(
        router, default_prompts(), AI_FINDING, SOURCE, allow_external=True
    )

    assert verified.verified_by == ["gemini"]
    assert verified.confidence == 0.9
    [request] = seen
    assert request.exclude_providers == frozenset({"nvidia"})
    code = request.user.split("CODE:\n", 1)[1]
    assert code.splitlines()[0] == "10 | line_10 = 10"
    assert "30 | line_30 = 30" in code
    assert '"lines": "20-20"' in request.user


async def test_without_another_model_the_finding_is_noted_as_not_cross_checked() -> None:
    router = mock_router(MockProvider("nvidia"))

    result = await verify_finding(
        router, default_prompts(), AI_FINDING, SOURCE, allow_external=True
    )

    assert result.ai_note == NOT_VERIFIED_NOTE
    assert result.status is FindingStatus.OPEN


@pytest.mark.parametrize(
    ("answer", "status", "note", "severity"),
    [
        (
            {"verdict": "valid", "corrected_severity": "critical"},
            FindingStatus.OPEN,
            None,
            "critical",
        ),
        (
            {"verdict": "invalid", "reason": "Input is validated."},
            FindingStatus.NEEDS_REVIEW,
            "gemini disagreed: Input is validated.",
            "high",
        ),
        ({"verdict": "uncertain"}, FindingStatus.OPEN, "gemini could not confirm it.", "high"),
    ],
)
def test_apply_verdict(
    answer: dict[str, object], status: FindingStatus, note: str | None, severity: str
) -> None:
    result = apply_verdict(AI_FINDING, VerificationAnswer.model_validate(answer), "gemini")

    assert (result.status, result.ai_note, result.severity.value) == (status, note, severity)


async def test_a_prose_verdict_falls_back_to_the_next_model() -> None:
    router = mock_router(
        MockProvider("nvidia"),
        MockProvider("gemini", respond=lambda request: "Looks valid to me."),
        MockProvider("hf-large", respond=lambda request: '{"verdict": "valid"}'),
    )

    verified = await verify_finding(
        router, default_prompts(), AI_FINDING, SOURCE, allow_external=True
    )

    assert verified.verified_by == ["hf-large"]
