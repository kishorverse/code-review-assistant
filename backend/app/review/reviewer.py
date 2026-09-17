"""Ask a model to review one chunk, and keep only what holds up.

The answer is validated as it arrives: if a provider's answer has no usable
structure, the router rejects it and asks the next provider. Reported issues
outside the task's categories or not anchored in the code are dropped;
judgements are kept only for static findings the model was actually shown.
"""

from dataclasses import dataclass

import structlog

from app.errors import AllProvidersUnavailableError, AnswerFormatError, InvalidResponseError
from app.findings import Category, Finding
from app.llm.models import LLMRequest, LLMResponse, Task
from app.llm.prompts import PromptLibrary
from app.llm.router import OnCall, Router
from app.review.answers import ReportedIssue, StaticJudgement, parse_review_answer
from app.review.context import ReviewContext
from app.review.grounding import clean_evidence, ungrounded_reason

REVIEW_OUTPUT_TOKENS = 4096
STYLE_OUTPUT_TOKENS = 2048

TEMPLATES = {Task.REVIEW: "task_review", Task.STYLE: "task_style"}
OUTPUT_TOKENS = {Task.REVIEW: REVIEW_OUTPUT_TOKENS, Task.STYLE: STYLE_OUTPUT_TOKENS}
CATEGORIES = {
    Task.REVIEW: frozenset(
        {
            Category.BUG,
            Category.SECURITY,
            Category.PERFORMANCE,
            Category.MAINTAINABILITY,
            Category.TYPING,
        }
    ),
    Task.STYLE: frozenset({Category.STYLE, Category.MAINTAINABILITY}),
}

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class Judged:
    """A model's judgement of a static finding."""

    finding: Finding
    judgement: StaticJudgement
    provider: str


@dataclass(frozen=True)
class ChunkReview:
    """What one review call produced.

    Attributes:
        findings: New findings from the model, already anchored in the code.
        judgements: Judgements of static findings shown to the model.
        discarded: Reported items dropped as malformed, off-task or not anchored.
        failure: Why the chunk was not reviewed, when no provider answered usably.
    """

    task: Task
    file_path: str
    findings: list[Finding]
    judgements: list[Judged]
    discarded: int
    failure: str | None = None


async def review_chunk(
    router: Router,
    prompts: PromptLibrary,
    context: ReviewContext,
    task: Task,
    *,
    allow_external: bool,
    on_call: OnCall | None = None,
) -> ChunkReview:
    """Review one chunk for one task (``review`` or ``style``)."""
    chunk = context.chunk
    request = LLMRequest(
        task=task,
        system=prompts.render("system_reviewer"),
        user=prompts.render(TEMPLATES[task], **context.prompt_values),
        max_output_tokens=OUTPUT_TOKENS[task],
        allow_external=allow_external,
    )
    try:
        response = await router.complete(request, on_call=on_call, validate=_validate)
    except AllProvidersUnavailableError as error:
        return ChunkReview(task, chunk.file_path, [], [], discarded=0, failure=str(error))

    answer = parse_review_answer(response.text)
    findings: list[Finding] = []
    discarded = answer.discarded
    for issue in answer.issues:
        reason = (
            "is outside the task's categories"
            if issue.category not in CATEGORIES[task]
            else ungrounded_reason(issue, chunk, context.source)
        )
        if reason is None:
            findings.append(to_finding(issue, chunk.file_path, response.provider))
        else:
            discarded += 1
            log.debug("issue_discarded", file=chunk.file_path, line=issue.start_line, reason=reason)
    judgements = [
        Judged(context.static_findings[judgement.static_id], judgement, response.provider)
        for judgement in answer.judgements
        if judgement.static_id in context.static_findings
    ]
    log.info(
        "chunk_reviewed",
        file=chunk.file_path,
        chunk=chunk.index,
        task=task.value,
        provider=response.provider,
        findings=len(findings),
        judgements=len(judgements),
        discarded=discarded,
    )
    return ChunkReview(task, chunk.file_path, findings, judgements, discarded)


def to_finding(issue: ReportedIssue, file_path: str, provider: str) -> Finding:
    """A finding for an issue that passed grounding."""
    return Finding(
        file_path=file_path,
        start_line=issue.start_line,
        end_line=issue.end_line,
        category=issue.category,
        severity=issue.severity,
        title=issue.title,
        message=issue.message,
        rationale=issue.rationale,
        evidence=clean_evidence(issue.evidence),
        rule_id=f"ai/{issue.category.value}",
        sources=[provider],
        confidence=issue.confidence,
        cwe=issue.cwe,
        suggestion=issue.suggested_change,
    )


def _validate(response: LLMResponse) -> None:
    try:
        parse_review_answer(response.text)
    except AnswerFormatError as error:
        raise InvalidResponseError(response.provider, str(error)) from error
