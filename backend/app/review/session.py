"""Run LLM review for one scan: review chunks, cross-check findings, summarize.

The pipeline runs each step as its own stage. Model calls for the scan run
concurrently up to the scan's limit while the router keeps every provider
within its own limits. Each attempt is emitted as an event as soon as its call
finishes and is kept for the report, and findings that review changed or
added are emitted once they are final.
"""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TypeVar

from app.events import CallEvent, EventSink, FindingEvent, ReviewPlanEvent
from app.findings import Finding, FindingStatus
from app.llm.models import CallRecord, Task
from app.llm.prompts import PromptLibrary, default_prompts
from app.llm.router import OnCall, Router
from app.preprocess.models import Chunk, PreprocessedFile
from app.redaction import SecretIndex
from app.review.answers import ReviewSummary
from app.review.context import (
    SourceText,
    build_context,
    describe_project,
    for_review,
    for_style,
    load_source,
)
from app.review.merge import apply_judgements, merge_ai_findings
from app.review.planner import Depth, ReviewOptions, plan_review
from app.review.reviewer import ChunkReview, review_chunk
from app.review.summary import summarize
from app.review.verifier import NOT_VERIFIED_NOTE, needs_verification, verify_finding
from app.static.runner import StaticAnalysisResult

PROMPTS_USED = (
    "system_reviewer",
    "task_review",
    "task_style",
    "system_verifier",
    "task_verify",
    "system_summarizer",
    "task_summarize",
)

ResultT = TypeVar("ResultT")


@dataclass(frozen=True)
class ReviewStats:
    """Counts describing what review did.

    Attributes:
        chunks_reviewed: Chunks that received at least one review or style call.
        chunks_skipped: Chunks left out by depth or budget.
        tasks_failed: Review or style tasks no provider could complete.
        ai_findings: Issues models reported that were anchored in the code.
        discarded: Reported items dropped as malformed, off-task or not anchored.
        judgements: Judgements of static findings that were applied.
        verified: AI findings a second model confirmed.
        disputed: AI findings a second model rejected.
        not_verified: AI findings that needed a cross-check no other model could do.
    """

    chunks_reviewed: int = 0
    chunks_skipped: int = 0
    tasks_failed: int = 0
    ai_findings: int = 0
    discarded: int = 0
    judgements: int = 0
    verified: int = 0
    disputed: int = 0
    not_verified: int = 0


@dataclass(frozen=True)
class ReviewResult:
    """Everything LLM review produced for a scan.

    Attributes:
        findings: All findings after review, most severe first.
        calls: Every model call attempt, in the order they finished.
        prompt_versions: The version of each prompt the review could use.
    """

    depth: Depth
    findings: list[Finding]
    calls: list[CallRecord]
    summary: ReviewSummary | None
    stats: ReviewStats
    prompt_versions: dict[str, str]


class ReviewSession:
    """The LLM review of one scan, run step by step by the pipeline."""

    def __init__(
        self,
        router: Router,
        options: ReviewOptions,
        sink: EventSink,
        prompts: PromptLibrary | None = None,
    ) -> None:
        self._router = router
        self._options = options
        self._sink = sink
        self._prompts = prompts or default_prompts()
        self._semaphore = asyncio.Semaphore(options.concurrency)
        self._calls: list[CallRecord] = []
        self._sources: dict[str, SourceText] = {}
        self._secrets = SecretIndex()
        self._stats = ReviewStats()

    async def review(
        self, files: Sequence[PreprocessedFile], static: StaticAnalysisResult, root: Path
    ) -> list[Finding]:
        """Review planned chunks and fold the results into the static findings."""
        plan = plan_review(files, static.findings, static.metrics, self._options)
        await self._sink.emit(
            ReviewPlanEvent(
                review_chunks=len(plan.review),
                style_chunks=len(plan.style),
                skipped_chunks=plan.skipped,
            )
        )
        by_path = {file.path: file for file in files}
        paths = sorted({chunk.file_path for chunk in [*plan.review, *plan.style]})
        await self.load_sources([by_path[path] for path in paths], static, root)
        project = describe_project(files)
        metrics = {entry.path: entry for entry in static.metrics}

        async def one(chunk: Chunk, task: Task) -> ChunkReview:
            include = for_review if task is Task.REVIEW else for_style
            context = build_context(
                chunk,
                self._sources[chunk.file_path],
                static.findings,
                metrics.get(chunk.file_path),
                project,
                include,
            )
            return await self._limited(
                chunk.file_path,
                lambda on_call: review_chunk(
                    self._router,
                    self._prompts,
                    context,
                    task,
                    allow_external=self._options.allow_external,
                    on_call=on_call,
                ),
            )

        reviews = await asyncio.gather(
            *(one(chunk, Task.REVIEW) for chunk in plan.review),
            *(one(chunk, Task.STYLE) for chunk in plan.style),
        )
        judged = [entry for review in reviews for entry in review.judgements]
        findings = apply_judgements(static.findings, judged)
        findings = merge_ai_findings(findings, [f for review in reviews for f in review.findings])
        self._stats = replace(
            self._stats,
            chunks_reviewed=len({(c.file_path, c.index) for c in [*plan.review, *plan.style]}),
            chunks_skipped=plan.skipped,
            tasks_failed=sum(review.failure is not None for review in reviews),
            ai_findings=sum(len(review.findings) for review in reviews),
            discarded=sum(review.discarded for review in reviews),
            judgements=len(judged),
        )
        await self._emit_changed(static.findings, findings)
        return findings

    async def load_sources(
        self, files: Sequence[PreprocessedFile], static: StaticAnalysisResult, root: Path
    ) -> None:
        """Read ``files`` with detected secrets masked, as review and verification send them.

        :meth:`review` calls this for the files it reviews; call it directly to verify
        findings without reviewing first.
        """
        self._secrets = static.secrets
        self._sources = await asyncio.to_thread(_load_sources, root, files, static.secrets)

    async def verify(self, findings: Sequence[Finding]) -> list[Finding]:
        """Cross-check serious AI findings with a second model."""
        verify_from = self._options.verify_from
        targets = [
            index
            for index, finding in enumerate(findings)
            if needs_verification(finding, verify_from) and finding.file_path in self._sources
        ]

        async def one(finding: Finding) -> Finding:
            return await self._limited(
                finding.file_path,
                lambda on_call: verify_finding(
                    self._router,
                    self._prompts,
                    finding,
                    self._sources[finding.file_path],
                    allow_external=self._options.allow_external,
                    on_call=on_call,
                ),
            )

        results = await asyncio.gather(*(one(findings[index]) for index in targets))
        updated = list(findings)
        for index, result in zip(targets, results, strict=True):
            updated[index] = result
            await self._sink.emit(FindingEvent(finding=result))
        self._stats = replace(
            self._stats,
            verified=sum(bool(result.verified_by) for result in results),
            disputed=sum(result.status is FindingStatus.NEEDS_REVIEW for result in results),
            not_verified=sum(result.ai_note == NOT_VERIFIED_NOTE for result in results),
        )
        return updated

    async def summarize(
        self, files: Sequence[PreprocessedFile], findings: Sequence[Finding]
    ) -> ReviewSummary | None:
        """Write the executive summary, if a provider can."""
        return await self._limited(
            None,
            lambda on_call: summarize(
                self._router,
                self._prompts,
                files,
                findings,
                self._secrets,
                min_confidence=self._options.min_confidence,
                allow_external=self._options.allow_external,
                on_call=on_call,
            ),
        )

    def result(self, findings: Sequence[Finding], summary: ReviewSummary | None) -> ReviewResult:
        """The review's outcome, with findings ordered most severe first."""
        ordered = sorted(
            findings, key=lambda f: (-f.severity.rank, f.file_path, f.start_line, f.rule_id or "")
        )
        return ReviewResult(
            depth=self._options.depth,
            findings=ordered,
            calls=list(self._calls),
            summary=summary,
            stats=self._stats,
            prompt_versions={name: self._prompts.version(name) for name in PROMPTS_USED},
        )

    async def _limited(
        self, file_path: str | None, run: Callable[[OnCall], Awaitable[ResultT]]
    ) -> ResultT:
        records: list[CallRecord] = []

        def keep(call: CallRecord) -> None:
            records.append(call.model_copy(update={"file_path": file_path}))

        async with self._semaphore:
            result = await run(keep)
        self._calls.extend(records)
        for record in records:
            await self._sink.emit(CallEvent(call=record))
        return result

    async def _emit_changed(self, before: Sequence[Finding], after: Sequence[Finding]) -> None:
        previous = {finding.id: finding for finding in before}
        for finding in after:
            if previous.get(finding.id) != finding:
                await self._sink.emit(FindingEvent(finding=finding))


def _load_sources(
    root: Path, files: Sequence[PreprocessedFile], secrets: SecretIndex
) -> dict[str, SourceText]:
    return {file.path: load_source(root, file, secrets) for file in files}
