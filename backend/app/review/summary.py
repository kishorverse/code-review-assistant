"""Write the executive summary of a review.

The model receives counts and a list of finding titles with their files, never
code, and is told to use only those facts. If no provider can write a usable
summary, the review simply has none.
"""

from collections import Counter
from collections.abc import Sequence

from app.errors import AllProvidersUnavailableError, AnswerFormatError, InvalidResponseError
from app.findings import Finding, FindingStatus
from app.llm.models import LLMRequest, LLMResponse, Task
from app.llm.prompts import PromptLibrary
from app.llm.router import OnCall, Router
from app.preprocess.models import PreprocessedFile
from app.review.answers import ReviewSummary, parse_summary_answer
from app.review.context import describe_project
from app.review.merge import is_reported

SUMMARY_OUTPUT_TOKENS = 2048
MAX_LISTED_FINDINGS = 30


async def summarize(
    router: Router,
    prompts: PromptLibrary,
    files: Sequence[PreprocessedFile],
    findings: Sequence[Finding],
    *,
    min_confidence: float,
    allow_external: bool,
    on_call: OnCall | None = None,
) -> ReviewSummary | None:
    """Summarize a review, or return ``None`` if no provider could."""
    request = LLMRequest(
        task=Task.SUMMARIZE,
        system=prompts.render("system_summarizer"),
        user=prompts.render(
            "task_summarize",
            project=project_facts(files, findings, min_confidence),
            findings=finding_lines(findings, min_confidence),
        ),
        max_output_tokens=SUMMARY_OUTPUT_TOKENS,
        allow_external=allow_external,
    )
    try:
        response = await router.complete(request, on_call=on_call, validate=_validate)
    except AllProvidersUnavailableError:
        return None
    return parse_summary_answer(response.text)


def project_facts(
    files: Sequence[PreprocessedFile], findings: Sequence[Finding], min_confidence: float
) -> str:
    """Counts describing the project and its reported findings."""
    reported = [finding for finding in findings if is_reported(finding, min_confidence)]
    severities = Counter(finding.severity.value for finding in reported)
    categories = Counter(finding.category.value for finding in reported)
    dismissed = sum(finding.status is FindingStatus.DISMISSED_BY_AI for finding in findings)
    needs_review = sum(finding.status is FindingStatus.NEEDS_REVIEW for finding in findings)
    return "\n".join(
        [
            f"files: {describe_project(files)}",
            f"reported findings: {len(reported)} ({_counts(severities)})",
            f"by category: {_counts(categories)}",
            f"dismissed by AI review: {dismissed}; needing human review: {needs_review}",
        ]
    )


def finding_lines(findings: Sequence[Finding], min_confidence: float) -> str:
    """One line per reported finding, most severe first, without any code."""
    reported = sorted(
        (finding for finding in findings if is_reported(finding, min_confidence)),
        key=lambda f: (-f.severity.rank, f.file_path, f.start_line),
    )
    lines = [
        f"- [{f.severity.value}] {f.category.value}, {f.file_path}:{f.start_line}: {f.title}"
        f" (found by {', '.join(f.sources)})"
        for f in reported[:MAX_LISTED_FINDINGS]
    ]
    if len(reported) > MAX_LISTED_FINDINGS:
        lines.append(f"- and {len(reported) - MAX_LISTED_FINDINGS} more")
    return "\n".join(lines) or "none"


def _counts(counter: Counter[str]) -> str:
    return ", ".join(f"{name} {count}" for name, count in counter.most_common()) or "none"


def _validate(response: LLMResponse) -> None:
    try:
        parse_summary_answer(response.text)
    except AnswerFormatError as error:
        raise InvalidResponseError(response.provider, str(error)) from error
