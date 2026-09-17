"""Cross-check serious AI findings with a different model.

A finding reported only by models, at or above the depth's verification
severity, is shown to another provider along with the code around it. The
provider that reported it is excluded, so a model never grades its own work.
A confirmation records the verifier; a rejection marks the finding as needing
human review rather than deleting it, since the second model can be wrong too.
"""

import json

from app.errors import AllProvidersUnavailableError, AnswerFormatError, InvalidResponseError
from app.findings import Finding, FindingStatus, Severity
from app.llm.models import LLMRequest, LLMResponse, Task
from app.llm.prompts import PromptLibrary
from app.llm.router import OnCall, Router
from app.review.answers import VerificationAnswer, VerificationVerdict, parse_verification_answer
from app.review.context import SourceText
from app.review.merge import is_ai_only

VERIFY_OUTPUT_TOKENS = 1024
CONTEXT_LINES = 10
NOT_VERIFIED_NOTE = "Not cross-checked: no other model was available."


def needs_verification(finding: Finding, verify_from: Severity | None) -> bool:
    """Whether a finding should be cross-checked at this verification threshold."""
    return (
        verify_from is not None
        and is_ai_only(finding)
        and finding.status is FindingStatus.OPEN
        and finding.severity.rank >= verify_from.rank
    )


async def verify_finding(
    router: Router,
    prompts: PromptLibrary,
    finding: Finding,
    source: SourceText,
    *,
    allow_external: bool,
    on_call: OnCall | None = None,
) -> Finding:
    """Ask a model other than the reporters whether a finding is real."""
    issue = {
        "title": finding.title,
        "category": finding.category.value,
        "severity": finding.severity.value,
        "lines": f"{finding.start_line}-{finding.end_line}",
        "message": finding.message,
        "rationale": finding.rationale,
        "evidence": finding.evidence,
    }
    request = LLMRequest(
        task=Task.VERIFY,
        system=prompts.render("system_verifier"),
        user=prompts.render(
            "task_verify",
            file_path=finding.file_path,
            language=source.language,
            issue=json.dumps(issue),
            code=source.excerpt(finding.start_line, finding.end_line, CONTEXT_LINES),
        ),
        max_output_tokens=VERIFY_OUTPUT_TOKENS,
        allow_external=allow_external,
        exclude_providers=frozenset(finding.sources),
    )
    try:
        response = await router.complete(request, on_call=on_call, validate=_validate)
    except AllProvidersUnavailableError:
        return finding.model_copy(update={"ai_note": NOT_VERIFIED_NOTE})
    return apply_verdict(finding, parse_verification_answer(response.text), response.provider)


def apply_verdict(finding: Finding, answer: VerificationAnswer, provider: str) -> Finding:
    """Record what the verifying model concluded."""
    reason = f": {answer.reason}" if answer.reason else "."
    if answer.verdict is VerificationVerdict.VALID:
        return finding.model_copy(
            update={
                "verified_by": [*finding.verified_by, provider],
                "severity": answer.corrected_severity or finding.severity,
                "confidence": max(finding.confidence, answer.confidence),
            }
        )
    if answer.verdict is VerificationVerdict.INVALID:
        return finding.model_copy(
            update={
                "status": FindingStatus.NEEDS_REVIEW,
                "ai_note": f"{provider} disagreed{reason}",
            }
        )
    return finding.model_copy(update={"ai_note": f"{provider} could not confirm it{reason}"})


def _validate(response: LLMResponse) -> None:
    try:
        parse_verification_answer(response.text)
    except AnswerFormatError as error:
        raise InvalidResponseError(response.provider, str(error)) from error
